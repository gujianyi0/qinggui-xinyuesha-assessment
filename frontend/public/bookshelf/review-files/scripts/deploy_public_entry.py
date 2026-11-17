"""Publish the static client and relay, uploading no provider credential."""
import json
import os
import shutil
import subprocess

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
    command([npm, "run", "build"], ROOT / "frontend", environment={**os.environ, "VITE_PUBLIC_MODE": "1"})
    assets = local / "assets"
    assets.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "frontend/dist", assets, dirs_exist_ok=True)
    # These authenticate relay transport/control only. MODEL_API_KEY is never read.
    command([npx, "wrangler", "secret", "bulk"], ROOT / "public-entry",
            data=json.dumps({"CONTROL_TOKEN": config["control_token"]}).encode())
    command([npx, "wrangler", "deploy"], ROOT / "public-entry")
    print(config["public_url"])


if __name__ == "__main__":
    main()
