"""Prepare local relay credentials for the outbound HTTPS relay."""
import json
import secrets

from backend.app.config import ROOT


def main():
    folder = ROOT / ".local/public-entry"
    folder.mkdir(parents=True, exist_ok=True)
    live = ROOT / ".env.docker-live"
    if not live.is_file():
        raise SystemExit("Prepare and migrate the authoritative live Docker deployment first")
    state = json.loads((ROOT / ".local/deployment.json").read_text(encoding="utf-8"))
    if state.get("primary") != "docker" or state.get("project") != str(ROOT):
        raise SystemExit("The migrated primary deployment must be Docker")
    path = folder / "config.json"
    if not path.exists():
        path.write_text(json.dumps({**{key: secrets.token_urlsafe(48) for key in
                                      ("edge_token", "service_token", "signing_key", "control_token")},
                                    "origin": "http://127.0.0.1:18081",
                                    "public_url": "https://qinggui-assessment.c2115259095.workers.dev"}, indent=2), encoding="utf-8")
    config = json.loads(path.read_text(encoding="utf-8"))
    # Preserve all existing model, database and budget values verbatim.
    lines = [line for line in live.read_text(encoding="utf-8").splitlines() if not line.startswith("PUBLIC_SERVICE_TOKEN=")]
    lines.append("PUBLIC_SERVICE_TOKEN=" + config["service_token"])
    live.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Local relay configured; all credentials remain under ignored local paths.")


if __name__ == "__main__":
    main()
