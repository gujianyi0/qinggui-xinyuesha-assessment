"""Local single-writer handoff state; never contains database or model secrets."""
import json
from pathlib import Path

from .config import ROOT
from .status_file import atomic_write_json

OWNER = "qinggui-assessment-deployment"


def read_deployment(root: Path = ROOT) -> dict:
    path = root / ".local/deployment.json"
    if not path.exists():
        return {}
    state = json.loads(path.read_text(encoding="utf-8-sig"))
    if state.get("owner") != OWNER or state.get("project") != str(root):
        raise RuntimeError("部署主库标记不属于本项目，保留并停止启动")
    return state


def require_native_primary(root: Path = ROOT):
    state = read_deployment(root)
    if state and (state.get("primary") != "native" or state.get("phase") != "active"):
        raise RuntimeError("原生库已冻结或已迁到Docker。请使用Docker入口；回切前必须迁回最新会话和费用账本，不能启动旧库。")


def write_deployment(state: dict, root: Path = ROOT):
    record = {**state, "owner": OWNER, "project": str(root)}
    (root / ".local").mkdir(exist_ok=True)
    if not atomic_write_json(root / ".local/deployment.json", record):
        raise OSError("无法持久化主库标记；停止切换")

