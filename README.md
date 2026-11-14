# 轻归 · 新月杀资料与反馈助手

面向普通新月杀玩家，提供规则与实体查询、固定场景裁定核对、多轮问答和问题反馈整理，并通过 Kafka 后台导入、解析和索引资料。

**代码版本：1.13；更新日期：2026-11-14。** 本文分别说明原有基础、第三方组件、本次考核开发与版本变更。1.10将回答正文与详细引用分开：正文简洁展示，末尾来源按钮展开原始证据；另记录本机浏览器无响应的内存排查。1.11修复来源按钮展开后位移及阅读时强制滚动，见[1.11报告](docs/1.11-来源按钮跳动修复-20261114.md)。1.10回归范围见[1.10报告](docs/1.10-回答展示与浏览器排查-20261114.md)，1.9全量真实回归按原日期保留。 1.12优化参考来源的段落、标题、列表、表格与代码排版，见[1.12报告](docs/1.12-参考来源阅读排版-20261114.md)。 1.13取消来源区的纵向滚动陷阱，并补真实滚轮边界验证，见[1.13报告](docs/1.13-参考来源滚动修复-20261114.md)。

[公开仓库](https://github.com/gujianyi0/qinggui-xinyuesha-assessment) · [1.9测试与修复报告](docs/1.9-裁定约束断线恢复与完整回归-20261113.md) · [验收矩阵](docs/验收矩阵.md) · [架构与接口](docs/架构与接口说明.md)

## 1. 原有基础：哪些内容来自已有项目

| 来源 | 原有内容 | 本项目实际复用的范围 |
| --- | --- | --- |
| 原轻归项目 | 已有AI对话能力和模型服务配置 | 经授权沿用模型服务地址、模型ID及本机凭据；由本项目通过Agno直接调用供应商，不依赖原轻归的回复进程、网页或运行数据库 |
| 用户指定的新月杀修改版 | 武将、卡牌、技能说明、规则文字和Lua业务实现 | 冻结外层standard、standard_cards、maneuvering三包作为资料与规则依据；游戏内容和原Lua逻辑归来源项目，不算本次新编写的游戏功能 |
| FreeKill运行时及测试后端 | 原有规则执行环境、测试接口、fake_backend等支撑 | 用于隔离执行固定Lua场景；引擎和测试后端为复用依赖，场景脚本、断言与本次执行记录另行编写和保存 |

资料快照为 `freekill-local-b9dc701220bc`，提交为 `b9dc701220bc04afe70cfbb40d729626fd33c147`，客户端标记0.5.25。冻结资料包含25个武将、43个牌定义、44个玩家技能和198条资料记录。来源路径、哈希及原许可文件见[资料清单](data/manifest.json)和[data/sources](data/sources/)；运行器来源与哈希见[引擎清单](rulings/engine-manifest.json)。

本项目没有导入原轻归的私人记忆、历史用户偏好和聊天库。当前入口是本项目独立的React网页与FastAPI服务；日常问答无需开启原轻归网页、QQ进程或原游戏客户端。历史OneBot适配器保留在[integrations/onebot](integrations/onebot/README.md)，QQ已移出当前交付范围。

## 2. 第三方组件：提供什么，本项目负责什么

| 第三方组件或服务 | 使用的现成能力 | 本项目编写的接入及业务逻辑 |
| --- | --- | --- |
| FastAPI、Uvicorn、Pydantic | HTTP服务、异步接口、请求与数据校验 | 身份和归属校验、会话/反馈/任务接口、错误处理、SSE事件约定 |
| Agno、OpenAI兼容客户端、deepseek-flash模型服务 | 模型调用、模型与工具循环、异步流式事件；模型生成能力来自外部服务 | 工具实现、应用层裁定约束、提示词、反馈缺项处理、超时/取消、运行审计与费用控制；兼容OpenAI协议不等于使用OpenAI模型 |
| PostgreSQL、pgvector、SQLAlchemy、Alembic | 事务、持久化、向量检索、数据库访问及迁移 | 业务表、唯一约束、来源关联、会话隔离、任务代次、索引原子发布、费用账本及迁移脚本 |
| BAAI/bge-small-zh-v1.5、Sentence Transformers、PyTorch | 已训练中文向量模型及CPU推理 | 锁定模型revision、下载校验、资料分块、召回组合、来源追溯及向量进程释放；未自行训练模型 |
| Apache Kafka、Confluent Python客户端 | 消息传输、生产/消费、位点管理接口 | 事务Outbox、投递与消费循环、幂等领取、有限重试、租约恢复、取消与终态保护 |
| Redis及客户端 | 公共检索结果缓存 | 缓存键与索引代次绑定、300秒TTL、失效和断连回源；不作为业务状态权威 |
| React、TypeScript、Vite、lucide-react | 前端框架、类型检查、构建工具、图标 | 本项目的问答、资料库、反馈及后台任务页面，以及引用展示、流式/轮询和原请求恢复交互 |
| react-markdown 10.1.0、remark-gfm 4.0.1 | Markdown结构与GFM表格等解析 | 来源类型判断、段落阅读样式、元数据分组、原文核对、交互与回归测试 |
| Docker Compose、Nginx | 服务编排、容器与网页/API代理 | 组合配置、启动/迁移脚本、持久卷方案、当前主库切换保护和备份恢复工具 |
| Cloudflare Workers、Durable Objects | 公网静态入口和连接协调 | 访客身份网关、出站HTTPS拉取/回复、本机API转发、纯客户端接入；模型密钥仍保留本机 |
| pytest、Vitest、Testing Library、Playwright、GitHub Actions | 测试执行、组件/浏览器自动化、CI平台 | 本项目的测试用例、故障场景、固定评测、引用审计、修正记录和检查流程；Playwright用于可选浏览器验证 |

Python依赖见[pyproject.toml](pyproject.toml)与[uv.lock](uv.lock)，网页依赖见[frontend/package.json](frontend/package.json)及其锁文件，公网入口依赖见[public-entry/package.json](public-entry/package.json)。第三方框架、权重、游戏原文与引擎均不作为本项目原创成果。

## 3. 本次考核项目开发了什么

以下是本项目基于上述组件编写的业务实现，区别于原轻归及游戏已有能力。其中多数主流程在1.0–1.8阶段已经建立，不能全部记成1.9新增。

| 本项目业务功能 | 实现内容及位置 |
| --- | --- |
| 资料处理与RAG | Lua静态提取、实体/别名、来源片段、快照与哈希、198条资料分成659块；[data](data/)、[catalog.py](backend/app/catalog.py)、[chunking.py](backend/app/chunking.py) |
| 三类受控工具 | 资料检索search_knowledge、实体查询query_game_data、已验证裁定get_verified_ruling；[runtime.py](backend/app/runtime.py) |
| 会话与问答 | 身份隔离、多轮历史、流式输出、工具回执、引用、运行结果及用量持久化；[main.py](backend/app/main.py)、[models.py](backend/app/models.py)、[frontend/src](frontend/src/) |
| 固定裁定 | SC01–SC08场景、必要前提、脚本选择、断言和执行轨迹，SC04另有对照；[rulings](rulings/) |
| 反馈流程 | 文字草稿与缺项追问、网页草稿编辑、修订号校验、明确确认和重复确认去重；正式反馈写本项目数据库 |
| 后台导入 | HTTP受理、事务Outbox、Kafka、独立Worker、分块向量化、暂存/发布、查询/取消/恢复；[jobs.py](backend/app/jobs.py)、[worker.py](backend/app/worker.py) |
| 共享真实问答 | 由提供者电脑托管后端、保管密钥和承担费用；公网网页及下载客户端连接同一后端与账本；[public_gateway.py](backend/public_gateway.py)、[public-entry](public-entry/)、[compose.client.yaml](compose.client.yaml) |
| 验证与交付 | 32条固定样例、真实模型前后记录、自动化与故障测试、修正过程、依赖配置和恢复工具；[tests](tests/)、[evaluations](evaluations/)、[scripts](scripts/)、[docs](docs/) |

### 最近1.9版本相比1.8新增或修正

| 变更 | 解决的问题 | 实现或证据 |
| --- | --- | --- |
| 裁定应用层约束 | 未调用工具也给结论、模型自填玩家前提、改变条件后沿用旧裁定 | [ruling_policy.py](backend/app/ruling_policy.py)、[FIX37](docs/1.9-裁定约束断线恢复与完整回归-20261113.md) |
| 原请求恢复与取消标记 | 回执丢失后无法找回、重发产生新请求、离页误取消、取消先到但迟到请求仍执行 | 持久request_id、原Run查询/回放、载荷校验、取消标记；[api.ts](frontend/src/api.ts)、[公网复测](docs/evidence/v19-browser-recovery-05/summary.json) |
| 版本和弃牌问题预查来源 | V02缺工具/引用；弃牌答案错误要求体力上限相等，受伤变体缺来源 | [版本范围说明](data/knowledge-boundaries.md)、catalog/runtime接入及真实回归 |
| 反馈与引用表述修正 | 用户未提供预期却被代填，正文跨文件行号指代错误 | I01/I02/M03、D04真实复测和[问题修正记录](docs/问题修正记录.md) |
| 评测费用预留与前置校验 | 隔离真实评测可能形成另一份未受控账本；用例缺字段在付费后才失败 | [budget_grants.py](backend/app/budget_grants.py)、[evaluations/run.py](evaluations/run.py) |
| 当前Docker主库备份恢复 | 原有原生迁移归档不能代表最新会话与账本 | [备份与恢复手册](docs/Docker主库备份与恢复.md)、19表恢复与历史读取证据 |
| 测试和文档补齐 | 完整32条真实回归、失败与复测留档、验收入口统一 | [32条逐条核对](docs/完整32条真实回归-1.9-20261113.md)、[验收矩阵](docs/验收矩阵.md) |

## 4. Kafka是否跑通：任务状态、去重和恢复

**已跑通。耗时任务是“批量导入、解析并索引指定资料快照”，聊天问答本身不通过Kafka排队。** 真实Linux容器验证完成过659块向量索引发布，并验证重复投递、消费中断、位点未提交、重试及依赖故障；详见[1.4容器验证](docs/1.4-Compose集成与故障恢复验证-20261111.md)、[17组原始证据](docs/evidence/compose-linux-20261111-04/summary.json)和[1.6逐条验收反馈](docs/项目实战测试反馈-20261112.md)。这些是历史实际执行证据，不代表本次README整理又运行了一次故障测试。

调用链：`HTTP → PostgreSQL中的Job与Outbox同事务提交 → Worker投递Kafka → Worker消费并领取任务 → 解析/BGE向量化 → PostgreSQL原子发布索引和完成状态`。投递、消费与租约恢复循环运行在同一个独立Worker进程内，API负责受理和查询。

### 任务处于什么状态

业务状态以PostgreSQL的Job记录为准，Kafka消息或Redis缓存不是进度记录。通过本机网页“后台任务”、`GET /jobs`或`GET /jobs/{id}`查询状态、进度、尝试次数、失败原因和执行记录；只能查询本人任务，公网访客入口不开放后台任务操作。

| 状态值 | 含义 |
| --- | --- |
| queued | 已受理、等待投递或领取；Kafka暂不可用时任务和未投递Outbox仍保留 |
| running | 已领取并执行，带当前generation与租约，按分块更新进度 |
| retry_wait | 临时失败，已保存原因和下次重试时间；到期重新排队 |
| cancel_requested | 运行中收到取消，等待在分块/发布前的检查点结束 |
| succeeded | 当前代次的完整索引已发布，进度100%；终态 |
| failed | 不可重试输入或尝试次数耗尽，保留失败原因；终态 |
| cancelled | 已取消，未完成的暂存索引不发布；终态 |

2026-11-14只读抽查：本机API返回200；alice可见21个历史任务中14个succeeded、7个cancelled，排队/运行/等待重试/取消中均为0。最新任务进度100%、执行1次。该统计仅对应当次查询的alice范围，实时结果以接口为准。

### 重复来了怎么办

- **HTTP重复提交**：同一用户、同一idempotency_key返回原任务；数据库唯一约束和并发冲突处理兜底。同键换快照拒绝，不同键视为新任务。
- **Kafka重复投递或并发消费**：领取时原子校验queued状态与expected_generation；只有符合状态和代次的一次领取能够执行。重复消息、旧代次消息、已完成或已取消任务不重复生成最终结果。
- **发出消息但Outbox未标记就崩溃**：恢复后允许再次投递，由消费端幂等处理。生产者幂等只是附加保障，跨进程恢复仍依赖应用校验。
- **数据库已完成、Kafka位点未提交就崩溃**：重放时发现任务已处于终态，跳过执行并确认消息。业务结果或可恢复重试安排持久化后才手动提交位点。

这里采用至少一次投递配合应用幂等，不宣称Kafka为整个业务提供了端到端exactly-once；计算可能重做，但同一任务不会重复发布最终业务结果。

### 失败后怎样恢复

| 情况 | 实际处理 |
| --- | --- |
| 已领取任务执行时的临时错误 | 保存原因，进入retry_wait；最多执行3次，含首次，后两次按10秒/30秒退避；重试安排落库后释放当前消息 |
| 坏业务输入或重试耗尽 | 进入failed并保留原因，不无限重试；业务问题处理并确认后，需要重新执行时使用新幂等键 |
| Worker异常退出/内存异常 | 启动脚本或容器重启策略负责进程重启；进程恢复后扫描过期租约。默认租约60秒、心跳10秒，未达上限则以新代次重新排队；次数耗尽则failed |
| 旧Worker恢复后迟到回写 | 每次写入和最终发布核对状态与generation，旧代次不能覆盖新代次或终态 |
| Kafka暂不可用 | HTTP事务中的Job/Outbox仍保留；投递失败不标记已送达，依赖恢复后继续投递 |
| PostgreSQL暂不可用 | API返回明确错误；若提交回执不确定，调用方用原幂等键查询/重试确认是否已受理。消费处理未持久化则不确认位点，并回退本地消费位置等待恢复 |
| Redis过期或不可用 | 检索回源PostgreSQL，任务状态仍由PostgreSQL保存 |
| 取消 | queued/retry_wait可直接取消；running先记cancel_requested，检查点及发布事务再次核对；终态不被重试覆盖 |

恢复会以新代次重新处理导入，**不是从上次分块继续**。旧代次的暂存块可能保留，但不作为已发布索引；只有完整代次成功时才原子切换发布指针。取消不能撤销已经发生的模型费用等副作用。业务执行最多3次；Kafka投递等待不计作任务执行次数，租约时长和进程重启策略分别由配置控制。重启策略耗尽或服务未启动时仍需要人工排查并恢复服务。

## 5. 如何使用与启动

### 共享真实问答：由提供者承担模型费用

打开[真实问答网页](https://qinggui-assessment.c2115259095.workers.dev/)，点击“进入工作区”。也可只下载并运行客户端：

```powershell
git clone https://github.com/gujianyi0/qinggui-xinyuesha-assessment.git
cd qinggui-xinyuesha-assessment
docker compose -f compose.client.yaml up -d --build
```

打开 <http://127.0.0.1:15176/>。该命令只启动网页，连接提供者本机的真实后端；不需要复制模型密钥或.env。提供者电脑必须开机、联网并保持服务运行。当前没有按人/按天问答配额，保留已约定的200元项目总预算及身份隔离。

### 当前提供者电脑：启动已有Docker主库

```powershell
pwsh -File scripts/start_docker_live.ps1
pwsh -File scripts/start_public_service.ps1
```

本机完整网页为 <http://127.0.0.1:15174/>，账号alice或bob，密码以本机私有配置为准。API文档为 <http://127.0.0.1:18081/docs>。私有配置.env.docker-live、部署标记、凭据、业务归档、运行卷和模型缓存均不提交Git；日常启动不需要原轻归进程。

停止共享入口和本机服务：

```powershell
pwsh -File scripts/stop_public_service.ps1
pwsh -File scripts/stop_docker_live.ps1
```

停止保留数据卷。当前PostgreSQL由原生库迁移而来，会话和费用账本延续保存；旧原生副本受启动保护，不得直接拿旧账本覆盖当前主库。详见[迁移与运行手册](docs/Docker主库迁移与运行手册.md)和[当前主库备份恢复](docs/Docker主库备份与恢复.md)。

### 全新自托管：默认使用模型替身

在新目录、没有已有业务主库时执行：

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose build
docker compose run --rm --no-deps api python scripts/prepare_embedding.py --download
docker compose up -d --wait
```

打开 <http://127.0.0.1:15175/>，API为 <http://127.0.0.1:18082/>，测试身份alice/bob的密码由.env中的DEMO_PASSWORD决定。到“后台任务”导入固定快照，完成后health中的index_published为true。BGE revision锁定为`7999e1d3359715c523056ef9478215996d62a620`，CPU执行。

完整Compose默认MODEL_MODE=mock；真实对话需要自行配置MODEL_MODE=live、模型ID、服务地址、密钥和输入/输出人民币单价。共享客户端命令与完整自托管命令用途不同。本机已有真实主库时使用上一节专用启动脚本，避免另开空库重新计算付费额度。

本地开发或不调用模型的流程演示见[执行计划与材料](docs/执行计划书.md)及[故障演示手册](docs/演示与故障恢复手册.md)。正式部署限定一个API进程和一个Worker，当前不提供多API高可用恢复。

## 6. 验证结果、证据与边界

以下为2026-11-13的1.9交付记录，不是本次文档整理重新运行的测试：

| 检查 | 已有结果 | 证据 |
| --- | --- | --- |
| 自动化 | 209项Python、17项前端行为测试及构建通过 | [后端XML](docs/evidence/v19-release-final-209.xml)、[1.9报告](docs/1.9-裁定约束断线恢复与完整回归-20261113.md) |
| 真实模型 | 四组原32条留档；最终整组V01超时后同版本定向复测，采用32条/35回合选定断言通过 | [逐条核对](docs/完整32条真实回归-1.9-20261113.md)、[评测目录](evaluations/results/) |
| 引用与裁定 | 最终采用109处引用完整性问题0；SC01–08及对照的执行证据可查 | [审查JSON](evaluations/results/v19-final-review.json)、[裁定目录](rulings/catalog.json) |
| 公网恢复 | 丢失提交回执、刷新、找回原回答、打开保存会话通过，仅一次模型提交 | [浏览器记录](docs/evidence/v19-browser-recovery-05/summary.json) |
| 备份恢复 | 19表完整指纹与账本一致；恢复库可列351个会话并抽查8条消息，0次模型调用 | [恢复比对](docs/evidence/v19-final-primary-restore.json)、[历史读取](docs/evidence/v19-final-primary-api-restore.json) |
| 远端交付 | main/1.9两组CI通过，匿名拉取与无私有配置客户端构建通过 | [main检查](https://github.com/gujianyi0/qinggui-xinyuesha-assessment/actions/runs/43358424593)、[1.9检查](https://github.com/gujianyi0/qinggui-xinyuesha-assessment/actions/runs/43358424675) |

开发环境可运行：

```powershell
uv sync --frozen --extra dev
uv run pytest -q
cd frontend
npm ci
npm test
npm run build
```

真实评测和故障测试的前提、独立环境及费用说明见[evaluations/README.md](evaluations/README.md)与[演示手册](docs/演示与故障恢复手册.md)。主真实服务不打开故障注入；不得把模型替身测试当真实模型准确率，或为评测另建不受原预算约束的付费账本。

验证边界：固定裁定只覆盖所列快照与前提，Lua/fake_backend证据不等于完整客户端或线上房间验证；引用哈希正确不等于所有召回都相关；本轮README整理没有重跑一小时稳定性。QQ和真人试用按用户决定移除，原要求中的真人试用不记为通过。备份仍需人工执行，未做异地复制或正式灾难主库切换；公司验收人、期限和演示安排以实际确认为准。

[问题修正全过程](docs/问题修正记录.md) · [当前版本进度](docs/进度同步-20261113.md) · [版本记录](docs/版本记录.md) · [问答与决策](docs/问答与决策记录.md)
