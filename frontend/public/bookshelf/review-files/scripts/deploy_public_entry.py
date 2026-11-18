"""Publish the static client and relay, uploading no provider credential."""
import datetime as dt
import hashlib
import json
import os
import subprocess

from dotenv import dotenv_values

from backend.app.config import ROOT


def command(arguments, cwd, *, environment=None, data=None):
    result = subprocess.run(arguments, cwd=cwd, env=environment, input=data, capture_output=True, timeout=180)
    if result.returncode:
        # Wrangler diagnostics can mention private request details. Keep local.
        path = ROOT / ".local/public-entry/deploy-error.log"
        path.write_bytes(result.stdout + result.stderr)
        raise SystemExit(f"Deployment command failed; inspect {path}")
    return result


def main():
    local = ROOT / ".local/public-entry"
    config = json.loads((local / "config.json").read_text(encoding="utf-8"))
    npm = "npm.cmd" if os.name == "nt" else "npm"
    npx = "npx.cmd" if os.name == "nt" else "npx"
    staging = local / 'assets-next'
    assert staging.resolve().is_relative_to(local.resolve())
    command([npm, "run", "build", '--', '--outDir', str(staging), '--emptyOutDir'], ROOT / "frontend",
            environment={**os.environ, "VITE_PUBLIC_MODE": "1", 'VITE_API_BASE': '/api'})
    private = dotenv_values(ROOT / '.env.docker-live', interpolate=False)
    secret_values = [private.get(key) for key in ('MODEL_API_KEY', 'POSTGRES_PASSWORD', 'BOOKSHELF_OWNER_KEY', 'PUBLIC_SERVICE_TOKEN')]
    secret_values.extend(config.get(key) for key in ('control_token', 'edge_token', 'service_token', 'signing_key'))
    files = sorted(file for file in staging.rglob('*') if file.is_file())
    for file in files:
        assert not any(value and value.encode() in file.read_bytes() for value in secret_values), file.relative_to(staging)
    repository = ROOT if (ROOT / '.git').exists() else ROOT / 'git'
    revision = command(['git', 'rev-parse', 'HEAD'], repository).stdout.decode().strip()
    manifest = {'version': (ROOT / 'VERSION').read_text().strip(), 'mode': 'public', 'sourceCommit': revision,
                'builtAt': dt.datetime.now(dt.UTC).isoformat(), 'providerCredentialsPublished': False,
                'artifacts': {file.relative_to(staging).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest() for file in files}}
    (staging / 'public-build.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    assets = local / "assets"
    backup = local / ('assets-backup-' + dt.datetime.now(dt.UTC).strftime('%Y%m%d-%H%M%S-%f'))
    assert assets.resolve().is_relative_to(local.resolve()) and backup.resolve().is_relative_to(local.resolve())
    if assets.exists():
        assets.rename(backup)
    staging.rename(assets)
    # Only transport control is uploaded. Provider/owner keys are checked locally.
    command([npx, "wrangler", "secret", "bulk"], ROOT / "public-entry",
            data=json.dumps({"CONTROL_TOKEN": config["control_token"]}).encode())
    deployed = command([npx, "wrangler", "deploy"], ROOT / "public-entry")
    (local / 'last-deploy.log').write_bytes(deployed.stdout + deployed.stderr)
    (local / 'last-build.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(config["public_url"])


if __name__ == "__main__":
    main()
