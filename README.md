# 轻归 · 新月杀资料与反馈助手

面向普通新月杀玩家：查武将、卡牌和技能资料，核对有明确前提的复杂结算，整理并确认问题反馈。所有实现均位于本目录，未修改原轻归或原游戏工程。

**当前版本1.9（2026-11-13）：裁定应用层校验、断线原请求找回、完整32条真实回归及Docker主库备份恢复。** 209项Python、17项前端及构建通过；四组完整真实记录保留，最终同版本32条选定断言通过（整组V01超时后定向复测），109处采用引用完整性问题0。公网丢失回执后刷新找回原回答，仅一次模型提交。密钥保留本机、费用由提供者承担，不设置次数/频率配额，保留200元总预算。QQ和真人试用仍移除，本轮没有重跑一小时。

[1.9测试与修正报告](docs/1.9-裁定约束断线恢复与完整回归-20261113.md) · [32条逐条核对](docs/完整32条真实回归-1.9-20261113.md) · [验收矩阵](docs/验收矩阵.md) · [备份与恢复](docs/Docker主库备份与恢复.md) · [当前进度](docs/进度同步-20261113.md) · [共享服务运维](docs/本机对外服务.md)。公司正式验收仍待安排，历史报告中的版本、数量和私有仓库状态仅代表当时。

项目公开仓库（按用户要求开放，任何人可访问）：[gujianyi0/qinggui-xinyuesha-assessment](https://github.com/gujianyi0/qinggui-xinyuesha-assessment)。托管检查结果见[GitHub Actions](https://github.com/gujianyi0/qinggui-xinyuesha-assessment/actions)。实际凭据、数据库、运行卷和下载缓存均排除提交。

## 别人如何真实对话

直接打开[真实问答网页](https://qinggui-assessment.c2115259095.workers.dev/)，点击“进入工作区”，不需要API密钥或密码。

拉取后只在自己电脑运行客户端：

```powershell
git clone https://github.com/gujianyi0/qinggui-xinyuesha-assessment.git
cd qinggui-xinyuesha-assessment
docker compose -f compose.client.yaml up -d --build
```

打开 <http://127.0.0.1:15176/>。此命令只启动界面，连接提供者电脑上的同一个真实后端与费用账本；不需要复制`.env`。提供者电脑须保持开机联网并运行服务。下面的完整Compose自托管方式仍默认mock，与下载版客户端命令不同。

## 本机当前入口：Docker真实问答

打开 http://127.0.0.1:15174 ，账号alice或bob，演示密码以本机私有配置为准。会话、索引和费用账本均来自原生库完整迁移，现由Docker中的PostgreSQL持久保存；模型服务继续使用获授权的deepseek-flash，Redis、Kafka、BGE及独立Worker实际运行。

```powershell
pwsh -File scripts/start_docker_live.ps1
pwsh -File scripts/stop_docker_live.ps1
```

启动脚本先启动Docker Desktop，再等待服务就绪；停止保留全部命名卷和主库标记。私有配置是`.env.docker-live`，不进入Git。本机普通`.env`已改为mock，避免误用普通Compose另开空库并重置付费额度；当前真实服务只使用专用配置。`.local/deployment.json`记录Docker为主库，旧`start_native.ps1`及直接native_demo入口会拒绝启动旧副本。

原生数据库、只读导出的source.dump及备份清单位于`.local`，保留但不进入Git。切换后不能把旧库直接当主库运行；如需回切，先迁回最新Docker数据与费用账本并验证，再调整主库标记。当前不自动回退到旧费用副本。[迁移、启动及恢复手册](docs/Docker主库迁移与运行手册.md)。

## 无模型密钥的隔离流程演示

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

## 全新目录／新库的Compose启动

以下用于全新目录或新库。本机已经迁移的真实主库使用上面的专用启动脚本，不在此另建付费库。先启动Docker服务。Windows使用Docker Desktop时可运行`docker desktop start`并等待引擎就绪，再执行下列命令。

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose build
docker compose run --rm --no-deps api python scripts/prepare_embedding.py --download
docker compose up -d --wait
docker compose ps
```

复制配置只在`.env`尚不存在时执行。修改本项目`.env`中的演示密码、数据库密码、模型配置；不需要修改系统代理或其他账号配置。Compose内数据库、Redis、Kafka使用内部服务地址，网页和API仅绑定本机。初始模型模式为mock。需要真实语义索引时：

```powershell
docker compose run --rm --no-deps api python scripts/prepare_embedding.py --download
```

示例配置已锁定`EMBEDDING_REVISION=7999e1d3359715c523056ef9478215996d62a620`，只需确认本项目`.env`没有改动它且`EMBEDDING_MODE=local`。打开 http://127.0.0.1:15175 ，账号alice或bob，演示密码以`.env`为准。网页“后台任务”选择固定快照并导入，成功后 http://127.0.0.1:18082/health 的`index_published=true`。可通过`WEB_PORT`和`API_PORT`修改端口；示例使用15175/18082，避开本机Windows的5173保留范围。下载缓存位于专用models卷，不写入仓库。网络暂时不可用时按错误处理，不切换代理或出口。

服务：PostgreSQL 17＋pgvector、Kafka KRaft单节点、Redis 7、Alembic迁移、一个API进程、独立Worker、Nginx＋React。API启动依赖迁移成功；单机验收限定**一个API进程**，启动会清理上个API进程中断的运行。不要使用`--workers`扩展API；多实例运行恢复需要另行实现租约。

```powershell
docker compose logs --tail 100 api worker
docker compose stop
```

`stop`保留数据卷。升级先备份本项目数据库，再运行`docker compose run --rm migrate`。此处不提供清空数据操作。本机已安装Docker Desktop/WSL2；项目容器验证结果单独记录。内存有限时先停止原生预览，避免两套基础设施同时占用资源。

### 隔离的Linux容器验证

先按上文构建镜像。每次使用新的英文project和label，保留旧结果及数据卷：

```powershell
$env:ASSESSMENT_ENV_FILE = '.env.example'
$verifyProject = 'qinggui-assessment-verify-demo01'
docker compose --env-file .env.example -p $verifyProject -f compose.yaml -f compose.verify.yaml run --rm --no-deps api python scripts/prepare_embedding.py --download
.venv\Scripts\python.exe scripts/verify_compose.py --label compose-demo01 --project $verifyProject
docker compose --env-file .env.example -p $verifyProject -f compose.yaml -f compose.verify.yaml stop
Remove-Item Env:ASSESSMENT_ENV_FILE
```

复查脚本需要本项目Python依赖，首次可用`uv sync --frozen --extra dev`安装；常规Docker启动只需Docker。验证配置读取`.env.example`，聊天为替身且模型密钥为空；数据库、Kafka、Redis、CPU BGE及Worker实际运行。脚本覆盖并发提交、取消、崩溃、位点、重试、依赖停机及重建，约需十几至二十分钟，以实测为准，证据保存在`docs/evidence/<label>`。

异常退出测试使用一个无网络、无数据挂载、只读根目录的辅助容器；它在Docker VM的PID命名空间内核对目标命名空间后发送信号，只授予KILL及读取目标身份所需的SYS_PTRACE能力。正常运行不需要这一步。测试仅接受`qinggui-assessment-verify`前缀的项目名。

验证库与原生预览库独立，验证费用为0。切换真实付费服务时须沿用或迁移项目用量账本，200元为整个项目总额。

## 原生验证与模型配置

### 已完成的本机真实依赖验证

在Docker安装前，使用项目`.local`中的便携原生依赖验证，未注册Windows服务；历史验证工具继续保留，当前迁移主库不再直接启动原生副本。PostgreSQL 17.11、pgvector 0.8.7、Kafka 3.9.1与锁定的BGE权重已实际执行。原生验证和Compose验收分别报告。

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
- 历史`/internal/qq/*`与适配器代码仅保留作归档和协议证据，当前无桥接凭据、白名单或真实QQ连接；[归档说明](integrations/onebot/README.md)。

PostgreSQL是业务状态权威；Redis仅缓存公共检索，默认TTL300秒，故障回源。索引分批写暂存区，最后与任务完成同事务切换发布指针。Worker手动提交Kafka位点，持久化结果或重试安排后才确认；处理异常回退本地消费位置，租约/代次阻止旧实例回写。临时失败最多3次、退避10/30秒，坏输入直接结束。

## 验证

```powershell
uv run pytest -q
uv run ruff check backend tests migrations scripts/local_demo.py scripts/prepare_embedding.py scripts/verify_compose.py
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

最新 Python 记录为 147 项通过，其中 11 项 Agno 协议夹具覆盖工具、裁定引用、前提保护、用户反馈来源、用量、超时、供应商错误、空正文和连接关闭。协议夹具不是实际供应商调用；真实模型记录保存在 `evaluations/results/live-*`，语义审查状态单独标识。Redis原下载502阻碍已解除；1.1实际命中、300秒自然失效、停机回源与重连验证通过，详见本轮报告。

当前Docker实模可用 `python -m evaluations.run --api-url http://127.0.0.1:15174/api --mode live --label 唯一标签 --concurrency 1`，费用计入迁移后的原账本。并发仅限1或2，记录在元数据中。历史F01由明确故障模式验证。当前真实主库不启用故障注入，也不为复测启动旧原生库；故障评测应在独立替身实例运行。未启用时该条明确记录为blocked。

## 项目材料

[执行计划](docs/执行计划书.md) · [问答与决策](docs/问答与决策记录.md) · [验证与差距](docs/验证与差距.md) · [问题修正记录](docs/问题修正记录.md) · [范围调整记录](docs/试用与改进记录.md)

## 裁定与多轮定向修复（2026-11-10）

J01/J02/J04/J05/J08/M02原输入已逐条核对来源并完成6条、7回合真实复测，详见[定向核对记录](docs/裁定与多轮问题核对-20261110.md)。工具get_verified_ruling支持reference=True读取固定记录，默认按conditions匹配当前局面；两者适用范围分开。已验证裁定正文直接从记录呈现，保留前提、步骤、牌面和证据，不由模型重写数值断言。SC04新增一次实际离线执行的SC04V对照；原场景证据保留。

后续已完整重跑32条真实评测并继续修复，最终`live-full-regression-20261110-05`的35轮均完成。Codex逐条对照答案、工具回执与本地来源，129处引用完整性检查0项不一致，详见[完整核对报告](docs/完整32条真实回归核对-20261110.md)。输入和预期未更改；全部中间失败记录保留，最终公司验收仍待进行；真人试用执行环节已按1.2决定移除。正常预览15174已恢复且故障注入关闭。本机曾发生Worker退出导致整组停止，一小时稳定性与恢复验证现已通过，见[历史1.0报告](docs/Worker一小时稳定性验证与1.0交付-20261111.md)；历史[中断记录](docs/evidence/native-preview-outage-20261110.json)保留。


## 历史：1.1 Redis本机集成

以下保留当时的原生验证方式。当前主库已迁入Docker，不再执行旧预览的重启；使用当前专用Docker启动脚本。

先执行`python scripts/prepare_native_redis.py`准备锁定哈希的7.4.11社区Windows构建（不安装系统服务），再重启原生预览。准备成功后`start_native.ps1`会自动在127.0.0.1:16379启动本项目Redis；未准备时保持回源。正在运行的旧预览需停止并重新启动才加载新配置。

`/api/health`的`cache=available`表示连接可用；Redis停止时为`unavailable_fallback`，API仍可用。原生监督器独立恢复Redis，不重启网页/PG/Worker。只缓存公共检索资料，TTL300秒；会话、反馈和任务状态以PostgreSQL为准。

复查命令：`python scripts/verify_native_redis.py --label 唯一标签`（隔离SQLite/测试向量）；`python scripts/verify_redis_postgres.py --label 唯一标签`（在已运行原生PG上建立独立测试数据库、实际BGE、完整300秒自然TTL）。两者只操作各自Redis测试端口，不调用QQ；正式项目模型费用另行记账。Redis进程为Windows社区版本，不能代替Linux Compose实际运行结论。
