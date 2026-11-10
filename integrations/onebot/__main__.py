"""No connection or send occurs without --live and an explicit trial configuration."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .bridge import run_live
from .config import BridgeConfig
from .events import normalize_event


def main() -> None:
    parser = argparse.ArgumentParser(description="轻归考核 OneBot 入口（默认无网络 dry-run）")
    parser.add_argument("--live", action="store_true", help="连接已配置的 OneBot，只处理白名单会话")
    parser.add_argument("--event-file", type=Path, help="仅离线检查一个事件 JSON，不发送也不调用后端")
    args = parser.parse_args()
    config = BridgeConfig.from_env()
    if args.event_file:
        event = json.loads(args.event_file.read_text(encoding="utf-8"))
        accepted = isinstance(event, dict) and normalize_event(event, config) is not None
        print(json.dumps({"mode": "dry-run", "accepted": accepted, "network_calls": 0}, ensure_ascii=False))
        return
    if not args.live:
        print(json.dumps({"mode": "dry-run", "network_calls": 0,
                          "private_allowlist_size": len(config.allowed_private_users),
                          "group_allowlist_size": len(config.allowed_groups),
                          "next_step": "配置试用白名单并暂停原回复进程后，显式使用 --live"}, ensure_ascii=False))
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run_live(config))
    except KeyboardInterrupt:
        pass
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
