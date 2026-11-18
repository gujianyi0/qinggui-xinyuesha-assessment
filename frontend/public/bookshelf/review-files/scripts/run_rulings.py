"""Prepare and run isolated FreeKill Lua rule tests, never in the source folder."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local" / "engine"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(path: Path, parent: Path) -> Path:
    result = path.resolve()
    if not result.is_relative_to(parent.resolve()):
        raise ValueError("Engine output must stay inside the assessment workspace")
    return result


def prepare(source: Path, archive: Path, sevenzip: Path) -> dict:
    """Extract only public runtime dependencies and tests from the PC release."""
    engine = inside(LOCAL, ROOT)
    engine.mkdir(parents=True, exist_ok=True)
    listing = subprocess.check_output([str(sevenzip), "l", "-slt", "-sccUTF-8", str(archive)], encoding="utf-8")
    paths = []
    for line in listing.splitlines():
        if not line.startswith("Path = "):
            continue
        raw = line[7:]
        normalized = raw.replace("\\", "/")
        if "/FreeKill-release/" not in normalized:
            continue
        rel = normalized.split("/FreeKill-release/", 1)[1]
        if "/" not in rel and (rel.endswith(".dll") or rel in {"FreeKill.exe", "qt.conf"}):
            paths.append(raw)
        elif rel.startswith("test/lua/") and rel.endswith(".lua"):
            paths.append(raw)
    if not any(p.endswith("FreeKill.exe") for p in paths):
        raise ValueError("No FreeKill executable found in approved PC archive")
    selected = engine / "archive-selection.txt"
    selected.write_text("\n".join(paths), encoding="utf-8")
    unpack = engine / "release-dependencies"
    unpack.mkdir(exist_ok=True)
    subprocess.run([str(sevenzip), "x", "-y", "-scsUTF-8", "-sccUTF-8", str(archive),
                    f"-o{unpack}", f"@{selected}"], check=True, capture_output=True)
    exe = next(unpack.rglob("FreeKill.exe"))
    release = exe.parent
    for item in release.iterdir():
        if item.is_file():
            shutil.copy2(item, engine / item.name)
    shutil.copytree(release / "test/lua", engine / "test/lua", dirs_exist_ok=True)
    runtime = source / "runtime"
    copied = []
    for relative in ("lua", "ltk", "packages/standard", "packages/standard_cards", "packages/maneuvering", "packages/test"):
        for item in sorted((runtime / relative).rglob("*.lua")):
            if item.is_symlink():
                raise ValueError("Symlink runtime is not allowed")
            rel = item.relative_to(runtime)
            dest = engine / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied.append({"path": rel.as_posix(), "sha256": sha256(dest)})
    for relative in ("packages/init.sql", "fk_ver"):
        item = runtime / relative
        if item.is_file():
            dest = engine / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
    if (engine / "packages/freekill-core").exists():
        raise ValueError("Isolation requires absence of the alternative freekill-core mirror")
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    manifest = {"prepared_at": datetime.now(timezone.utc).isoformat(), "source_commit": commit,
                "archive_sha256": sha256(archive), "binary_sha256": sha256(engine / "FreeKill.exe"),
                "rule_files": copied, "harness_files": [{"path": p.relative_to(engine).as_posix(), "sha256": sha256(p)} for p in sorted((engine / "test/lua").rglob("*.lua"))],
                "scope": "fixed-snapshot Lua rules with fake_backend; not full-client or online-match validation"}
    (engine / "engine-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def run_test(label: str, arguments: list[str], timeout: int = 90, output_dir: Path | None = None) -> dict:
    engine = inside(LOCAL, ROOT)
    exe = engine / "FreeKill.exe"
    if not exe.is_file():
        raise ValueError("First prepare the isolated runtime")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PATH"] = str(engine) + os.pathsep + env.get("PATH", "")
    trace_file = inside(engine / f"assessment_trace_{label}.json", engine)
    if trace_file.exists():
        trace_file.unlink()
    try:
        proc = subprocess.run([str(exe), *arguments], cwd=engine, env=env, timeout=timeout, capture_output=True)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        result = {"exit_code": proc.returncode, "stdout": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired as exc:
        result = {"exit_code": None, "stdout": (exc.stdout or b"").decode("utf-8", errors="replace"),
                  "stderr": (exc.stderr or b"").decode("utf-8", errors="replace"), "error": "timeout"}
    log = engine / "freekill.server.log"
    result.update({"label": label, "arguments": arguments, "cwd": ".local/engine",
                   "executed_at": datetime.now(timezone.utc).isoformat(),
                   "binary_sha256": sha256(exe), "server_log": log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""})
    run_summary = re.search(r"Ran (\d+) tests? in .*?, (\d+) success(?:es)?, (\d+) failures?", result["stdout"])
    result["tests_run"] = int(run_summary[1]) if run_summary else 0
    result["successes"] = int(run_summary[2]) if run_summary else 0
    result["failures"] = int(run_summary[3]) if run_summary else None
    result["passed"] = (result["exit_code"] == 0 and result["tests_run"] > 0 and result["failures"] == 0)
    if trace_file.is_file():
        result["trace"] = json.loads(trace_file.read_text(encoding="utf-8"))
    if label.startswith("SC"):
        result["passed"] = result["passed"] and result.get("trace", {}).get("passed", False)
        scene = ROOT / "rulings/scenes" / f"{label}.lua"
        result["scenario_sha256"] = sha256(scene)
        result["common_sha256"] = sha256(scene.parent / "common.lua")
    # A process exit of zero by itself is deliberately not a verified ruling.
    out = inside(output_dir or ROOT / "rulings/evidence", ROOT) / f"{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--sevenzip", type=Path, default=Path("F:/Apps/7-Zip/7z.exe"))
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--output-dir", type=Path, help="Write a new evidence run without replacing catalog evidence")
    parser.add_argument("--scene", choices=[f"SC{i:02}" for i in range(1, 9)] + ["SC04V"])
    args = parser.parse_args()
    if args.prepare:
        if not args.source or not args.archive:
            parser.error("--prepare requires --source and --archive")
        manifest = prepare(args.source.resolve(), args.archive.resolve(), args.sevenzip)
        print(json.dumps({"prepared": True, "rule_files": len(manifest["rule_files"]), "binary_sha256": manifest["binary_sha256"]}))
    if args.baseline:
        result = run_test("baseline", ["--testskills", "jianxiong,#eight_diagram_skill"], output_dir=args.output_dir)
        print(json.dumps({"label": "baseline", "exit_code": result["exit_code"], "passed": result["passed"], "tests_run": result["tests_run"]}))
        return 0 if result["passed"] else 1
    if args.scene:
        source_file = ROOT / "rulings/scenes" / f"{args.scene}.lua"
        if not source_file.is_file():
            parser.error("Scene implementation not available; catalog remains unverified")
        dest = LOCAL / "assessment_scenes" / source_file.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        for script in source_file.parent.glob("*.lua"):
            shutil.copy2(script, dest.parent / script.name)
        result = run_test(args.scene, ["--testfile", dest.relative_to(LOCAL).as_posix()], output_dir=args.output_dir)
        print(json.dumps({"label": args.scene, "exit_code": result["exit_code"], "passed": result["passed"], "tests_run": result["tests_run"], "tail": result["stdout"][-2500:] if not result["passed"] else ""}))
        return 0 if result["passed"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
