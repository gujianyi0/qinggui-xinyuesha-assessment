# 轻归 · 新月杀资料与反馈助手

## 1. 使用者与问题

面向普通新月杀玩家，解决规则和技能资料难查、复杂结算缺少前提、问题反馈缺少复现信息的问题。玩家可以查询资料、核对固定裁定记录，并整理和确认反馈；开发者可以追溯来源、工具调用及后台导入结果。

## 2. 完成范围

已实现React网页、FastAPI/Agno问答、PostgreSQL/pgvector检索、多轮流式与原请求恢复、三类受控工具、反馈草稿及明确确认、身份隔离，以及Kafka＋独立Worker的资料导入、查询、重试和取消。

资料固定为新月杀外层standard、standard_cards、maneuvering三包，快照`freekill-local-b9dc701220bc`；包含198条资料，索引分为659块。SC01–SC08及选定对照有Lua规则引擎离线执行记录，不表示任意对局都已验证。

当前本地版本为`2.0.1-local.1`；15180运行v2内测前端，15174与公网仍为1.13前端，共用API已应用2.0.1缺陷修复。v2未上传GitHub。材料位置、验证记录与分项进度见[文档导航QA](docs/文档导航QA/文档导航QA.md)。

## 3. 启动及测试命令

需要Docker Compose；本地构建与测试另需Python 3.13、uv和符合`frontend/package.json`要求的Node.js。以下命令从项目根目录执行。

**当前电脑：使用已有主库和私有配置启动内测。**

```powershell
pwsh -File scripts/start_docker_live.ps1
pwsh -File scripts/start_v2_local.ps1
# 已有匹配当前VERSION的构建时，可加 -SkipBuild
# 停止v2网页，保留API和数据库：
pwsh -File scripts/stop_v2_local.ps1
```

内测地址：[127.0.0.1:15180](http://127.0.0.1:15180/)。账号`alice`或`bob`，当前本机演示密码为`123`。主库启动依赖本机已有的`.env.docker-live`和部署标记；无需开启原轻归或QQ。

**全新独立环境：仅在没有既有业务主库的新目录使用。**

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose build
docker compose run --rm --no-deps api python scripts/prepare_embedding.py --download
docker compose up -d --wait
```

默认网页为`http://127.0.0.1:15175/`、API为`http://127.0.0.1:18082/`，模型为替身；账号密码以该环境的`DEMO_PASSWORD`为准。进入后台任务导入快照后才有发布的向量索引。真实模型需另配服务地址、模型ID、密钥和单价。已有主库的本机使用上一组专用脚本，避免另开空库和独立费用账本。

只使用提供者已有真实问答服务、无需模型密钥的网页客户端：

```powershell
docker compose -f compose.client.yaml up -d --build
```

客户端地址为`http://127.0.0.1:15176/`，依赖提供者电脑和共享服务在线，不是独立后端。

**自动化测试与构建：**

```powershell
uv sync --frozen --extra dev
uv run ruff check backend tests
uv run pytest -q
npm --prefix frontend ci
npm --prefix frontend run check
```

`check`包含Lint、架构边界、类型、Knip、前端测试和生产构建。固定样例及需计费、隔离环境的真实评测另见[验证导航](docs/文档导航QA/02-验证测试修正与试用反馈.md)，不作为上述命令的自动步骤。

## 4. 主要调用链路

- 问答：网页登录 → FastAPI校验身份与会话 → 保存用户输入及运行编号 → Agno调用模型和受控工具 → 汇集引用并执行裁定约束 → 保存答案、工具审计与用量 → SSE或轮询返回。回答期间可编辑下一条草稿，完成后再发送。
- 反馈：聊天整理信息 → 网页保存草稿 → 用户核对指定修订 → 确认接口校验归属和revision → 幂等保存正式反馈；聊天中的“确认”不会直接提交。
- 导入：HTTP将Job和Outbox同事务入库 → 独立Worker投递Kafka并消费 → 领取执行代次 → 解析、分块、BGE向量化 → 暂存完成后在PostgreSQL原子发布 → 网页查询状态。聊天问答本身不通过Kafka排队。

实现入口：[main.py](backend/app/main.py)、[runtime.py](backend/app/runtime.py)、[jobs.py](backend/app/jobs.py)、[worker.py](backend/app/worker.py)、[前端功能模块](frontend/src/features/)。

## 5. 工具边界

| 工具 | 允许的操作 | 边界 |
| --- | --- | --- |
| `search_knowledge` | 查询固定快照的规则与技能资料，返回来源 | 未召回不等于资料不存在；不访问任意网页或私人记录 |
| `query_game_data` | 按名称、类型等有限条件查询武将、技能、卡牌 | 不接受任意SQL或文件路径 |
| `get_verified_ruling` | 查询选定场景、核对必要前提、查看固定执行记录 | 仅在本轮需要裁定时提供；普通问题不继承旧SC场景。条件未匹配不能发布确定结论，模型自填条件不算玩家确认 |

Agno负责模型和工具编排；权限、确认、任务状态与审计由应用控制。游戏原文、FreeKill引擎、BGE权重和各第三方框架为复用组件；本项目实现其接入与业务规则，来源说明见[交付材料导航](docs/文档导航QA/01-源码依赖迁移配置与资料.md)。

## 6. 数据设计

| 数据 | 保存位置与约束 |
| --- | --- |
| 身份、会话、消息、Run、工具审计 | PostgreSQL；接口校验归属，原请求编号用于找回运行并检查载荷，换身份不复用前端缓存 |
| 反馈草稿与正式反馈 | PostgreSQL；草稿有revision，明确确认后正式保存，重复确认返回原记录 |
| 任务、尝试、Outbox和索引 | PostgreSQL/pgvector；用户＋幂等键唯一，状态、租约和generation约束回写，完整索引原子发布 |
| 用量与费用预留 | PostgreSQL统一账本；调用前预留、结束后结算，保留200元项目总预算，不按用户新增问答配额 |
| 公共检索缓存 | Redis；默认300秒TTL，键含快照/索引代次等；失效或中断回源，不保存权威业务状态 |
| 冻结资料与裁定证据 | `data/`、`rulings/`；记录快照、路径、行号、来源哈希及证据范围 |

表定义见[models.py](backend/app/models.py)，结构变更见[Alembic迁移](migrations/versions/)。密钥、实际数据库、私有备份、模型缓存和运行依赖不提交Git。

## 7. 失败处理

| 情况 | 处理方式 |
| --- | --- |
| 非法字段、越权、过期修订 | 明确拒绝；不放宽Schema或归属检查迁就调用方 |
| 模型/工具失败、超时、空正文 | 保存失败原因和可重试状态，不伪造成功或引用；无自动无限付费重试，用量不明时按预留保守结算 |
| 回执丢失、断线或刷新 | 用原请求编号查询/恢复；离页分离观察，显式停止才取消，不重新创建同一付费请求 |
| 重复提交或重复Kafka消息 | 数据库唯一约束、状态及执行代次保证幂等；结果或可恢复重试安排落库后才提交位点 |
| Worker退出或临时故障 | 进程恢复后扫描过期租约；默认60秒租约、10秒心跳，最多3次业务尝试，后两次按10/30秒退避；旧代次不能覆盖新结果 |
| Kafka/数据库/Redis中断 | Outbox保留待投递消息；未持久化的消费不确认位点；数据库异常返回可恢复错误；Redis不可用回源 |
| 取消 | 排队任务直接取消，运行任务在分块与发布前检查；终态不回退，不撤销已发生费用，取消的暂存索引不发布 |

任务恢复以新代次重新处理，不是从上次分块继续。备份与恢复步骤见[Docker主库备份与恢复](docs/Docker主库备份与恢复.md)。

## 8. 已知限制

- 只覆盖固定快照和选定场景。引用完整性、替身测试或一次真实回答正确，均不能证明任意模型输出、完整客户端或线上对局正确。
- 正式部署限定单API进程与单Worker；无多API高可用、异地备份或正式灾难切换。共享服务依赖提供者电脑持续运行。
- 2.0.1已有230项后端、49项前端及定向真实/浏览器记录；完整32条真实回归和一小时稳定性属于各自历史版本，本次文档整理没有重跑。
- Storybook、Lighthouse、v2完整隔离浏览器写入流程和另一台物理电脑的全新部署仍未完成；整浏览器无响应的具体根因也没有被完全确证。
- QQ与真人试用已按用户决定移出；没有独立试用反馈，不能记为原考核试用要求已通过。公司验收、范围认可、截止日期与演示安排仍需确认。
