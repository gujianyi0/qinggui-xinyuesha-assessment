# 轻归 · 新月杀资料与反馈助手

面向普通新月杀玩家：查武将、卡牌和技能资料，核对有明确前提的复杂结算，整理并确认问题反馈。所有实现均位于本目录，未修改原轻归或原游戏工程。

**当前状态：本机预览可运行，原生PostgreSQL/pgvector/BGE与Kafka故障验证已通过；完整考核尚未验收。** 已有32条固定样例和SC01–SC08离线规则证据。真实聊天模型已接通并保存同组32条前后记录；语义审查、Redis实际TTL/停机、Compose构建运行、QQ送达、真人试用和仓库提交仍待完成。详见[真实依赖验证](docs/真实依赖验证记录.md)及[验收差距](docs/验证与差距.md)。

## 快速运行（不需要模型密钥或Docker）

### 已接通真实基础设施的本机预览

本机已准备便携依赖时执行：

```powershell
pwsh -File F:\Work\Biteagle\入职考核\scripts\start_native.ps1
```

打开 http://127.0.0.1:15174 ，账号 `alice` 或 `bob`，演示密码 `local-demo-change-me`。这个预览实际连接 PostgreSQL、pgvector、Kafka、独立 Worker 和本地 BGE；聊天模式读取本项目 `.env`，当前已按用户授权接通轻归的 `deepseek-flash`。Redis 当前不可用并回源。首次问答会加载 CPU 模型，可能需要更长等待。网页可以实际导入、取消和确认反馈。

停止时执行 `pwsh -File scripts/stop_native.ps1`，只停止此预览拥有的进程并保留数据库。状态位于 `.local/native-demo/status.json`。本轮[集成网页证据](docs/evidence/browser-native-20261110-resume-03/summary.json)包含 7 项通过流程，另有[真实导入结果](docs/evidence/browser-native-20261110-resume-03/published-job.json)。

### 轻量替身预览

本机已安装依赖时，使用独立后台启动脚本，关闭启动终端后仍可访问：

```powershell
pwsh -File F:\Work\Biteagle\入职考核\scripts\start_local.ps1
```

打开 http://127.0.0.1:15173 。脚本同时启动API并检查网页到API的代理连接；运行日志保存在`.local/preview-*.log`。电脑重启后重新执行脚本即可。以下是首次安装和前台启动方式。

需要Python 3.13、uv、Node.js ≥22.12。在本目录执行：

```powershell
uv sync --frozen --extra dev
uv run python scripts/local_demo.py
```

另一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

打开 http://127.0.0.1:5173 ，使用alice或bob，密码为示例配置的`local-demo-change-me`；已有本项目`.env`时以`DEMO_PASSWORD`为准。API文档：http://127.0.0.1:8000/docs 。

这个启动方式明确使用SQLite、测试向量和模型替身，仅用于本机流程验证。资料查询在未建索引时显示`lexical_unindexed`；真正RAG验收必须使用下述PostgreSQL、锁定的BGE模型与后台导入。没有启动Worker时后台任务会保持排队，可查询或取消。

## 完整技术栈（Compose）

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

复制配置只在`.env`尚不存在时执行。修改本项目`.env`中的演示密码、数据库密码、模型配置；不需要修改系统代理或其他账号配置。Compose内数据库、Redis、Kafka使用内部服务地址，网页和API仅绑定本机。初始模型模式为mock。需要真实语义索引时：

```powershell
docker compose run --rm --no-deps api python scripts/prepare_embedding.py --download
```

将输出的`EMBEDDING_REVISION`写入本项目`.env`，确认`EMBEDDING_MODE=local`，再`docker compose up -d api worker`。网页“后台任务”选择固定快照并导入，成功后`/health`的`index_published=true`。下载缓存位于专用models卷，不写入仓库。网络暂时不可用时按错误处理，不切换代理或出口。

服务：PostgreSQL 17＋pgvector、Kafka KRaft单节点、Redis 7、Alembic迁移、一个API进程、独立Worker、Nginx＋React。API启动依赖迁移成功；单机验收限定**一个API进程**，启动会清理上个API进程中断的运行。不要使用`--workers`扩展API；多实例运行恢复需要另行实现租约。

```powershell
docker compose logs --tail 100 api worker
docker compose stop
```

`stop`保留数据卷。升级先备份本项目数据库，再运行`docker compose run --rm migrate`。此处不提供清空数据操作。当前机器未检测到Docker，Compose文件尚未实际构建启动。

## 原生验证与模型配置

### 已完成的本机真实依赖验证

本机没有Docker，补充使用项目`.local`中的临时原生依赖验证，未注册Windows服务。PostgreSQL 17.11、pgvector 0.8.7、Kafka 3.9.1与锁定的BGE权重已实际执行。原生验证和Compose验收分别报告。

```powershell
uv sync --frozen --extra dev --extra embeddings
.venv\Scripts\python.exe scripts/prepare_embedding.py --download
.venv\Scripts\python.exe scripts/verify_embeddings.py --label bge-check-01
.venv\Scripts\python.exe scripts/prepare_native_kafka.py
.venv\Scripts\python.exe scripts/verify_native_kafka.py --label kafka-check-01
```

Windows可额外准备本地PostgreSQL，需已安装Visual Studio C++构建工具：

```powershell
.venv\Scripts\python.exe scripts/prepare_native_postgres.py
pwsh -File scripts/build_native_pgvector.ps1
.venv\Scripts\python.exe scripts/verify_native_postgres.py --label pg-check-01 --kafka
```

每个label必须唯一；各脚本创建自己的数据库/Topic/证据目录，停止自己启动的进程，保留原数据。PostgreSQL脚本会临时使用一个空闲DOS盘符指向本项目`.local`，解决Windows中文路径bootstrap编码问题；退出后解除映射，不复制工程、不改系统语言。原生Kafka单独验证默认SQLite，PostgreSQL脚本的`--kafka`会额外在真实PostgreSQL上执行六项故障矩阵。

BGE仅使用CPU轮子，依赖锁已移除CUDA运行库。模型文件按固定revision下载，核对Hub文件大小、LFS SHA256或Git blob哈希，保留清单后从本地离线加载。长资料按320字符、64重叠分块；198条原始资料产生659块，保留原来源及提取文本的字符偏移。检索缓存包含发布任务及代次，换模型需重新导入。

### 真实聊天模型配置

`MODEL_MODE=live`才使用Agno和兼容OpenAI协议的服务；配置`MODEL_ID`、`MODEL_API_KEY`、`MODEL_BASE_URL`、输入/输出人民币单价。没有密钥或单价时明确失败。真实密钥只写被忽略的`.env`，仅按本次授权导入必要模型参数，不复制其他轻归配置。

用户明确授权后，可只导入既有模型参数：`uv run python scripts/import_qinggui_model.py --source F:\QingGui`。脚本只读取模型密钥、模型地址/ID及GUI模型覆盖项，不导入QQ账号、历史偏好、私人记忆。当前按2026-11-10官方高峰缓存未命中价保守记账，脱敏来源见 `docs/evidence/model-configuration-20261110.json`，费用为估算而非供应商账单。

模型最多6次工具调用，默认并发2、超时60秒、单次输出2048 tokens。数据库原子预留费用，总预算200元、160元提示；用量缺失或中断按预留金额保守记账，不能把估算当供应商账单。每次运行保存实际模式、模型ID、提示词版本、耗时、用量、工具结果和引用。付费上限仅覆盖此项目发起并记账的请求。

## 数据与引用

- 固定快照：`freekill-local-b9dc701220bc`；外层standard、standard_cards、maneuvering三个包，25武将、43牌定义、44玩家技能、198资料记录。
- [快照清单](data/manifest.json)、[资料记录](data/documents.json)、`data/sources/`保留本地来源与哈希。
- [裁定目录](rulings/catalog.json)保留8个固定场景、必要条件、Lua断言和轨迹。其证据为固定快照Lua逻辑＋fake_backend，不能称为完整客户端或线上对局验证。
- 来源代码来自用户指定的原新月杀工程；第三方许可见冻结源文件中的许可声明及[来源说明](docs/来源与复用说明.md)。是否允许对外共享须确认。

## 接口与数据职责

- `/auth/token`：两个测试身份；只保存token摘要，token有效12小时。
- `/sessions`、`/sessions/{id}/runs`：会话及SSE；运行查询、取消位于`/runs/{id}`。
- `/catalog/entities`、`/catalog/rulings`、`/catalog/snapshots`：公共资料。
- `/feedback-drafts`：创建/修订草稿，确认接口需匹配revision；正式反馈以draft_id唯一约束防重复。
- `/jobs`：任务与Outbox同事务入库；按身份和幂等键去重；状态、失败、尝试、取消持久化。
- `/internal/qq/*`：专用桥接token和试用白名单；[适配器说明](integrations/onebot/README.md)。默认dry-run，真实发送不作为此README启动的副作用。

PostgreSQL是业务状态权威；Redis仅缓存公共检索，默认TTL300秒，故障回源。索引分批写暂存区，最后与任务完成同事务切换发布指针。Worker手动提交Kafka位点，持久化结果或重试安排后才确认；处理异常回退本地消费位置，租约/代次阻止旧实例回写。临时失败最多3次、退避10/30秒，坏输入直接结束。

## 验证

```powershell
uv run pytest -q
uv run ruff check backend tests migrations scripts/local_demo.py scripts/prepare_embedding.py
cd frontend
npm test
npm run build
```

固定样例通过HTTP执行，需先启动API：

```powershell
uv run python -m evaluations.run --mode mock --label mock-01
```

故障用例需独立测试实例启动`local_demo.py --faults`，正常实例不启用。模型替身记录只能证明程序链路；裁定、多轮语义、版本冲突仍要逐条审查。真实模型前后对比使用相同`cases.json`、不同label，并分别指定`--mode live`。详见[评测说明](evaluations/README.md)、[故障演示手册](docs/演示与故障恢复手册.md)。

GitHub Actions配置已落盘，尚未上传或在GitHub执行。它执行本机契约测试和构建，不替代Kafka/PostgreSQL集成验收。

最新 Python 记录为 99 项通过，其中 11 项 Agno 协议夹具覆盖工具、裁定引用、前提保护、用户反馈来源、用量、超时、供应商错误、空正文和连接关闭。协议夹具不是实际供应商调用；真实模型记录保存在 `evaluations/results/live-*`，语义审查状态单独标识。Redis 准备与验证脚本已落盘，但运行包下载 HTTP 502，实际 TTL/命中/停机验证仍待完成。

完整实模评测可用 `python -m evaluations.run --api-url http://127.0.0.1:15174/api --mode live --label 唯一标签 --concurrency 2`。并发仅限1或2，记录在元数据中。F01需要明确启用故障模式：先停止本机预览，再 `pwsh -File scripts/start_native.ps1 -EvaluationFaults`；评测结束停止后不带参数重新启动，恢复默认禁用故障注入。未启用时该条明确记录为blocked。

## 项目材料

[执行计划](docs/执行计划书.md) · [问答与决策](docs/问答与决策记录.md) · [验证与差距](docs/验证与差距.md) · [问题修正记录](docs/问题修正记录.md) · [试用记录](docs/试用与改进记录.md)

## 裁定与多轮定向修复（2026-11-10）

J01/J02/J04/J05/J08/M02原输入已逐条核对来源并完成6条、7回合真实复测，详见[定向核对记录](docs/裁定与多轮问题核对-20261110.md)。工具get_verified_ruling支持reference=True读取固定记录，默认按conditions匹配当前局面；两者适用范围分开。已验证裁定正文直接从记录呈现，保留前提、步骤、牌面和证据，不由模型重写数值断言。SC04新增一次实际离线执行的SC04V对照；原场景证据保留。

后续已完整重跑32条真实评测并继续修复，最终`live-full-regression-20261110-05`的35轮均完成。Codex逐条对照答案、工具回执与本地来源，129处引用完整性检查0项不一致，详见[完整核对报告](docs/完整32条真实回归核对-20261110.md)。输入和预期未更改；全部中间失败记录保留，真人及公司验收仍待进行。正常预览15174已恢复且故障注入关闭。本机曾发生Worker退出导致整组停止，长期内存稳定性仍待验证，见[中断记录](docs/evidence/native-preview-outage-20261110.json)。
