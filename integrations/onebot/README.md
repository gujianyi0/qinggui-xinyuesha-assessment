# 轻归考核 QQ 入口

这是本项目自己的 OneBot 11 文本适配器，连接同一 FastAPI。它不导入原轻归工程、运行数据库、私人记忆或历史偏好。模块默认 dry-run，默认不连接网络。

## 离线检查

在项目根目录执行：

```powershell
uv run python -m integrations.onebot
```

输出 `mode=dry-run, network_calls=0`。也可用 `--event-file 本地事件.json` 检查一个自造事件；该选项不发送消息、不调用模型。

## 实际试用配置

OneBot 服务沿用现有 QQ 账号。试用前暂停原轻归回复监听进程，保留原账号、配置和数据；完成后停止本入口，再恢复原轻归。

请在当前终端或本项目的私有环境配置以下字段，示例值均为占位符：

```dotenv
ONEBOT_WS_URL=ws://127.0.0.1:3001
ONEBOT_ACCESS_TOKEN=<OneBot连接凭据>
QQ_BOT_ID=<机器人QQ号>
QQ_ALLOWED_SESSIONS=private:<试用者QQ号>,group:<专用测试群号>
BRIDGE_API_URL=http://127.0.0.1:8000
BRIDGE_TOKEN=<与后端一致的桥接凭据>
QQ_ORIGINAL_LISTENER_PAUSED=true
```

后端也检查 `QQ_BOT_ID` 和 `QQ_ALLOWED_SESSIONS`。两处名单必须一致。当前终端需显式加载这些环境变量；模块不会读取旧轻归的 `.env`。

准备完成后执行：

```powershell
uv run python -m integrations.onebot --live
```

`--live` 会连接 `/event` 与 `/api`，且仅处理明确白名单。群消息还需要 @机器人或以 `/新月杀` 开头。首版仅接受文字；图片、语音及匿名消息不会丢弃媒体后冒充完整问题。

## 身份、确认与送达

- 使用 OneBot 的 `self_id/user_id/group_id/message_id`，不按昵称或正文判断身份。
- 群会话按机器人、群、发送者隔离；网页与 QQ 身份分别管理。
- QQ 收到完整回答和引用后统一发送，不逐 token 刷屏。
- 按后端返回草稿编号执行“确认 ABC123 v2”；普通“好的”不确认任意草稿。
- 入站由后端持久去重；出站由本地 `.local/bridge/deliveries.sqlite3` 形成发送围栏。
- 发送前持久记录 `sending`。明确 API 拒绝记 `failed`；等待回执超时、断线或发送中进程退出记 `unknown`，不自动重发。
- OneBot 返回消息 ID 只证明接口接受。真人端显示需要试用者核对；日志不把接口回执称为真人送达验证。
- 网络恢复时核对后端 pending 队列；已有本地终态只补报回执，不重复发消息。

## 测试范围

`tests/test_bridge.py` 使用自造事件、假的 WebSocket 和 HTTP transport，检查路由、去重、失败回执、回执丢失及重启边界。自动测试不连接 QQ，也不使用真人消息。

协议依据：[正向 WebSocket](https://github.com/botuniverse/onebot-11/blob/master/communication/ws.md)、[消息事件](https://github.com/botuniverse/onebot-11/blob/master/event/message.md)、[发送消息 API](https://github.com/botuniverse/onebot-11/blob/master/api/public.md)。
