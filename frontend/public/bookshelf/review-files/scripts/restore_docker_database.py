"""Restore a checked native archive into an empty, dedicated Docker database."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

from backend.app.config import ROOT
from backend.app.database_transfer import assert_same_database
from backend.app.deployment import read_deployment, write_deployment
from scripts.docker_live import PROJECT, docker_command, docker_environment, run_compose


def main(label):
    if not re.fullmatch(r"[a-z0-9-]{1,70}", label):
        raise ValueError("invalid backup label")
    marker = read_deployment()
    if marker.get("phase") != "source_frozen" or marker.get("label") != label:
        raise ValueError("Source is not the checked frozen primary")
    private = ROOT / ".local/migrations" / label
    source = json.loads((private / "fingerprint.json").read_text(encoding="utf-8"))
    archive = private / "source.dump"
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != marker["archive_sha256"]:
            raise ValueError("Private archive hash mismatch")
    evidence = ROOT / "docs/evidence" / (label + "-restore")
    evidence.mkdir(parents=True, exist_ok=False)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "project": PROJECT,
              "archive_sha256": marker["archive_sha256"], "checks": [],
              "scope": "Restore own private backup into empty dedicated Docker DB, no clean/drop of existing data"}

    def command(*args, stdin=None, timeout=180):
        result = run_compose(*args, timeout=timeout, stdin=stdin)
        number = len(report["checks"]) + 1
        (evidence / f"command-{number:02d}.log").write_bytes(result.stdout + result.stderr)
        report["checks"].append({"operation": args[0], "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(f"Docker transfer command {number} failed; inspect evidence")
        return result.stdout.decode("utf-8").strip()

    try:
        command("config", "--quiet")
        command("up", "-d", "--no-build", "--wait", "--wait-timeout", "90", "postgres")
        current = int(command("exec", "-T", "postgres", "psql", "-U", "assessment", "-d", "assessment", "-At", "-c", "SELECT count(*) FROM pg_tables WHERE schemaname='public'"))
        if current:
            raise ValueError("Target contains tables; preserved, no overwrite permitted")
        report["empty_target_verified"] = True
        with archive.open("rb") as stream:
            command("exec", "-T", "postgres", "pg_restore", "-U", "assessment", "-d", "assessment",
                    "--no-owner", "--no-privileges", "--exit-on-error", "--single-transaction", stdin=stream, timeout=240)
        target = json.loads(command("run", "--rm", "--no-deps", "api", "python", "scripts/fingerprint_database.py", timeout=180))
        assert_same_database(source, target)
        report["restored"] = target
        command("run", "--rm", "--no-deps", "migrate")
        target_after_migrate = json.loads(command("run", "--rm", "--no-deps", "api", "python", "scripts/fingerprint_database.py", timeout=180))
        assert_same_database(source, target_after_migrate)
        report["alembic_preserved_all_rows"] = True

        # Reuse only verified public BGE assets; all business data came from the archive.
        helper = """import hashlib,json,shutil
from pathlib import Path
a=Path('/from'); b=Path('/to')
assets=[p for p in a.rglob('*') if p.is_file()]
assert assets and any(p.name=='model.safetensors' for p in assets)
shutil.copytree(a,b,dirs_exist_ok=True)
hashes={str(p.relative_to(a)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in assets}
assert all(hashlib.file_digest((b/name).open('rb'),'sha256').hexdigest()==value for name,value in hashes.items())
print(json.dumps({'files':len(hashes),'sha256':hashes,'passed':True}))
"""
        copied = subprocess.run([docker_command(), "run", "--rm", "--network", "none",
                                 "--mount", "type=volume,source=qinggui-assessment-verify-14-fixed_models,target=/from,readonly",
                                 "--mount", f"type=volume,source={PROJECT}_models,target=/to",
                                 "--entrypoint", "python", "qinggui-assessment-api:latest", "-c", helper],
                                cwd=ROOT, env=docker_environment(), capture_output=True, timeout=60)
        if copied.returncode:
            raise RuntimeError("Verified model volume preparation failed; DB preserved")
        report["public_model_assets"] = json.loads(copied.stdout)
        write_deployment({"primary": "docker", "phase": "restored", "label": label,
                          "compose_project": PROJECT, "source_spent_cny": source["budget"]["spent"],
                          "archive_sha256": marker["archive_sha256"]})
        report["passed"] = True
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (evidence / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "tables_matched": len(source["tables"]), "budget": target["budget"], "phase": "restored"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    main(parser.parse_args().label)
