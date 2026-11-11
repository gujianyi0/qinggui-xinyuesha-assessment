"""Shared private-config Docker commands for the migrated primary deployment."""
import os
import shutil
import subprocess
from pathlib import Path

from backend.app.config import ROOT

PROJECT = "qinggui-assessment-live"


def docker_command():
    executable = shutil.which("docker")
    if not executable and os.name == "nt":
        executable = str(Path(os.environ["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin/docker.exe")
    return executable or "docker"


def docker_environment():
    executable = docker_command()
    return {**os.environ, "PATH": str(Path(executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "ASSESSMENT_ENV_FILE": ".env.docker-live"}


def compose_arguments():
    return [docker_command(), "compose", "--env-file", ".env.docker-live", "-p", PROJECT,
            "-f", "compose.yaml", "-f", "compose.live.yaml"]


def run_compose(*arguments, timeout=180, stdin=None):
    if not (ROOT / ".env.docker-live").is_file():
        raise ValueError("Private Docker live config is missing")
    return subprocess.run([*compose_arguments(), *arguments], cwd=ROOT, env=docker_environment(),
                          stdin=stdin, capture_output=True, timeout=timeout)

