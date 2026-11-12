"""Copy a reviewed release into the user's local Git repository, without pushing."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from dotenv import dotenv_values

from backend.app.config import ROOT, Settings

EXCLUDED = {"git", ".git", ".venv", ".local", ".wrangler", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache", "coverage", "htmlcov"}


def next_version(tags):
    releases = sorted(int(tag.split(".")[1]) for tag in tags if tag.startswith("1.") and tag[2:].isdigit())
    return f"1.{releases[-1]+1}" if releases else "1.0"


def release_files(root):
    for folder, directories, filenames in root.walk():
        directories[:] = [name for name in directories if name not in EXCLUDED and not name.endswith((".egg-info", ".dist-info"))]
        for name in filenames:
            path = folder / name
            if path.is_symlink() or (name.startswith(".env") and name != ".env.example"):
                continue
            if any(name.endswith(suffix) for suffix in (".pyc", ".pyo", ".tmp", ".key", ".pem")) or ".sqlite3" in name:
                continue
            if name.endswith(".log") and not path.relative_to(root).as_posix().startswith("docs/evidence/"):
                continue
            yield path


def release_target(version, tags, *, complete_current=False):
    expected = next_version(tags)
    version = version or expected
    if complete_current:
        if version not in tags or expected != f"1.{int(version.split('.')[1])+1}":
            raise ValueError("Only the existing latest 1.x release can be completed")
        target = version + "-verified"
        if target in tags:
            raise ValueError("Verified release tag already exists; tags are never rewritten")
        return version, target
    if version != expected:
        raise ValueError(f"Next release must be {expected}; existing tags are never rewritten")
    return version, version


def snapshot(version=None, *, complete_current=False):
    if (ROOT / ".git").exists():
        raise ValueError("Run the snapshot command from the source workspace, not from inside its published Git copy")
    repository = ROOT / "git"
    if repository.is_symlink():
        raise ValueError("Repository must not be a symlink")
    repository.mkdir(exist_ok=True)

    def git(*arguments, binary=False, **kwargs):
        return subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True,
                              text=not binary, encoding=None if binary else "utf-8", **kwargs).stdout.strip()

    if not (repository/".git").exists():
        if any(repository.iterdir()):
            raise ValueError("Local target contains non-repository files; preserved")
        git("init", "-b", "main")
        git("config", "core.quotepath", "false")
    if git("status", "--porcelain"):
        raise ValueError("Local repository has uncommitted changes; preserved")
    version, tag = release_target(version, git("tag", "--list").splitlines(), complete_current=complete_current)
    if (ROOT/"VERSION").read_text(encoding="utf-8").strip() != version:
        raise ValueError("Update VERSION and release notes before taking a snapshot")
    selected = list(release_files(ROOT))
    # Compare the actual local model credential without printing its value.
    secrets = [Settings().model_api_key]
    live_config = ROOT / ".env.docker-live"
    if live_config.is_file():
        private = dotenv_values(live_config, interpolate=False)
        secrets.extend(private.get(key) or "" for key in ("MODEL_API_KEY", "POSTGRES_PASSWORD", "PUBLIC_SERVICE_TOKEN"))
    gateway_config = ROOT / ".local/public-entry/config.json"
    if gateway_config.is_file():
        gateway_private = json.loads(gateway_config.read_text(encoding="utf-8"))
        secrets.extend(gateway_private.get(key) or "" for key in ("edge_token", "service_token", "signing_key", "control_token"))
    for path in selected:
        if any(secret and secret.encode() in path.read_bytes() for secret in secrets):
            raise ValueError(f"Credential found in {path.relative_to(ROOT)}; release stopped")
    relative = {path.relative_to(ROOT).as_posix() for path in selected}
    tracked = git("ls-files", "-z").split("\0")
    for name in tracked:
        if name and name not in relative:
            target = (repository/name).resolve()
            if not target.is_relative_to(repository.resolve()) or ".git" in Path(name).parts:
                raise ValueError("Invalid tracked path; preserved")
            target.unlink(missing_ok=True)
    for path in selected:
        target = repository/path.relative_to(ROOT)
        if target.is_symlink() or not target.resolve().is_relative_to(repository.resolve()):
            raise ValueError("Snapshot target must stay inside repository")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    # A local automation identity only when Git has no configured identity.
    for key, value in (("user.name", "Codex Local"), ("user.email", "codex@local.invalid")):
        result = subprocess.run(["git", "-C", str(repository), "config", "--get", key], capture_output=True)
        if result.returncode:
            git("config", key, value)
    git("add", "--all")
    # Existing indexes may still contain blobs normalized before .gitattributes
    # was introduced. Re-apply attributes, then verify the actual committed bytes.
    git("add", "--renormalize", ".")
    algorithm = git("rev-parse", "--show-object-format")
    for entry in git("ls-files", "--stage", "-z").split("\0"):
        if not entry:
            continue
        header, name = entry.split("\t", 1)
        raw = (ROOT / name).read_bytes()
        expected_oid = hashlib.new(algorithm, b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if header.split()[1] != expected_oid:
            raise ValueError(f"Git index changed source bytes: {name}; no commit or tag created")
    git("commit", "-m", f"Release {version}: verified onboarding assistant")
    git("tag", "-a", tag, "-m", f"Local release {version}: validation complete" if complete_current else f"Local release {version}")
    if git("status", "--porcelain"):
        raise ValueError("Snapshot committed but working tree is not clean")
    print(json.dumps({"version": version, "repository": str(repository), "commit": git("rev-parse", "HEAD"),
                      "tag": git("describe", "--exact-match", "--tags"), "files": len(selected), "pushed": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    parser.add_argument("--complete-current", action="store_true", help="Complete the latest existing release with a new -verified tag, preserving all existing tags")
    arguments = parser.parse_args()
    snapshot(arguments.version, complete_current=arguments.complete_current)
