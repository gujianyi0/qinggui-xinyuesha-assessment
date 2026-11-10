"""Copy a reviewed release into the user's local Git repository, without pushing."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

from backend.app.config import ROOT, Settings

EXCLUDED = {"git", ".git", ".venv", ".local", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache", "coverage", "htmlcov"}


def next_version(tags):
    releases = sorted(int(tag.split(".")[1]) for tag in tags if tag.startswith("1.") and tag[2:].isdigit())
    return f"1.{releases[-1]+1}" if releases else "1.0"


def release_files(root):
    for folder, directories, filenames in root.walk():
        directories[:] = [name for name in directories if name not in EXCLUDED]
        for name in filenames:
            path = folder / name
            if path.is_symlink() or (name.startswith(".env") and name != ".env.example"):
                continue
            if any(name.endswith(suffix) for suffix in (".pyc", ".pyo", ".tmp", ".key", ".pem")) or ".sqlite3" in name:
                continue
            if name.endswith(".log") and not path.relative_to(root).as_posix().startswith("docs/evidence/"):
                continue
            yield path


def snapshot(version=None):
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
    expected = next_version(git("tag", "--list").splitlines())
    version = version or expected
    if version != expected:
        raise ValueError(f"Next release must be {expected}; existing tags are never rewritten")
    if (ROOT/"VERSION").read_text(encoding="utf-8").strip() != version:
        raise ValueError("Update VERSION and release notes before taking a snapshot")
    selected = list(release_files(ROOT))
    # Compare the actual local model credential without printing its value.
    secret = Settings().model_api_key.encode()
    for path in selected:
        if secret and secret in path.read_bytes():
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
    git("commit", "-m", f"Release {version}: verified onboarding assistant")
    git("tag", "-a", version, "-m", f"Local release {version}")
    if git("status", "--porcelain"):
        raise ValueError("Snapshot committed but working tree is not clean")
    print(json.dumps({"version": version, "repository": str(repository), "commit": git("rev-parse", "HEAD"),
                      "tag": git("describe", "--exact-match", "--tags"), "files": len(selected), "pushed": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    snapshot(parser.parse_args().version)
