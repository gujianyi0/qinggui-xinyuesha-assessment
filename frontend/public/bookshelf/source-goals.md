# 故剑遗学习目标 · 项目实战之前

来源：https://biteagle.yuque.com/mw0520/rzyee0/ay7550zlq5vyq27t

核对日期：2026-11-12；语雀显示更新时间：11-10 10:04。已逐项对照登录浏览器可见原文，补回本地总纲遗漏的 5 条 Python 目标。

## 学习内容
> 所有推荐阅读链接均为参考，实际可结合 AI 进行高效学习。
>

### Python 基础与异步编程
需要掌握：

+ Python 的模块、函数、类、类型标注、异常、上下文管理器，以及虚拟环境和依赖管理。可以结合已有的 C++、JavaScript 经验，重点看 Python 有哪些不同。

+ 能沿着请求入口读到业务逻辑、数据库和外部调用，理解输入、输出和错误怎样传递；修改已有代码前确认调用方和影响范围。

+ 协程、事件循环、Task，以及 async def、await、创建任务和并发执行之间的区别。

+ 同步网络请求、time.sleep、耗时计算为什么可能阻塞事件循环；异步客户端、线程池各适合什么场景。

+ 超时、取消、异常传播、资源清理和并发限制；一个模型请求很慢时，其他请求仍能得到响应。

+ HTTP 客户端与数据库连接的复用和关闭，服务停止时如何处理在途任务。

推荐阅读：

+ [Python 3.13 官方教程](https://docs.python.org/3.13/tutorial/)
+ [协程、任务、超时与取消](https://docs.python.org/3.13/library/asyncio-task.html)
+ [FastAPI：并发与 async / await](https://fastapi.tiangolo.com/async/)



### 大模型原理、API 与输出校验
需要掌握：

+ Token、上下文窗口、输入与输出用量、自回归生成的基本含义；理解为什么模型可能编造事实，为什么长上下文不等于可靠记忆。
+ 概念上了解 Transformer、Attention、预训练和指令微调，分清训练模型、运行模型与调用模型 API 的区别。
+ 系统要求、用户输入、历史消息和外部资料的作用与边界；根据任务选择上下文，避免无上限累积历史。
+ 提示词中的任务、资料、约束、示例和输出格式如何组织；修改提示词后用同一组样例比较，不能只凭一次满意的回答判断有效。
+ 能用 Python 直接完成一次模型调用，读懂请求、响应、结束状态和用量；区分模型调用与使用 AI 编程工具。
+ 普通响应与流式响应的差别，文本增量、结束事件、超时和中途断开如何处理。
+ JSON 输出、Schema 和业务校验的区别；能解析 JSON 不代表字段正确、事实可靠或符合业务约束。
+ 用 Pydantic 等方式校验模型结果，分别处理格式错误、缺字段、拒答和信息不足，让调用方知道发生了什么。
+ 重要数值由程序计算，重要事实有资料依据。记录模型、提示词版本、耗时与用量，比较一次修改的收益和代价。

推荐阅读：

+ [DeepSeek API：首次调用](https://api-docs.deepseek.com/)
+ [DeepSeek：JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)
+ [Pydantic：模型与校验](https://pydantic.dev/docs/validation/latest/concepts/models/)



### Agent、工具调用与执行边界
需要掌握：

+ 普通对话、固定工作流和 Agent 的适用范围。能说明哪些决定交给模型，哪些由确定的程序规则完成。
+ 一次完整工具调用：模型提出调用意图，程序校验参数与权限，执行工具，返回结果，再决定继续还是结束。
+ 工具名称、描述、参数 Schema、返回值和错误信息怎样影响模型的选择；保留工具实际执行的结果，方便检查模型为什么这样回答。
+ 工具超时、失败重试、最大执行步数、总耗时和调用预算，避免循环调用和无边界消耗。
+ 会话历史、执行状态与工具记录的区别；多个用户或会话之间不能串数据。
+ 外部文档、用户输入和工具结果属于待处理数据，其中的指令不能扩大工具权限或覆盖应用规则。
+ 写入、删除、发送等操作的确认边界；确认后执行的对象和内容必须与用户看到的一致。
+ 使用 Agno 接入模型与工具、发起异步运行、处理流式事件。弄清框架提供了什么，业务代码负责什么，先用熟这一套框架。

推荐阅读：

+ [Anthropic：如何构建有效的 Agent](https://www.anthropic.com/research/building-effective-agents)
+ [Agno 官方文档](https://docs.agno.com/)



### RAG、来源引用与知识更新
需要掌握：

+ 从文档解析、分块、Embedding、检索到组织上下文和生成回答的完整过程。
+ 分块大小、重叠、Top-K 和元数据过滤如何影响结果；能区分资料没收进来、检索没找到和模型答错。
+ 保留资料来源、章节和版本；回答引用能指向实际支持该说法的内容。
+ 新旧规则冲突、资料缺失或问题超出资料范围时，能够澄清、说明不确定或拒绝编造。
+ 用固定问题和独立参考依据验证效果；模型或提示词修改后，用同一组样例检查是否退步。

推荐阅读：

+ [LlamaIndex：RAG 完整流程](https://developers.llamaindex.ai/python/framework/understanding/rag/)
+ [pgvector：PostgreSQL 向量检索](https://github.com/pgvector/pgvector)



### HTTP 服务、SQL、数据库与缓存
需要掌握：

+ FastAPI 请求与响应模型、输入校验、错误状态和生命周期；前端能区分请求失败、处理中和业务成功。
+ SQL 查询、关联、约束、索引和事务。结合 ORM 发出的 SQL，弄清数据如何保存、何时提交、失败时回滚什么。
+ PostgreSQL 保存会话、消息、资料版本、工具执行和最终结果；SQLAlchemy 异步访问与 Alembic 迁移。
+ 业务唯一性、并发修改和重复请求；数据库约束与事务如何防止重复记录和不完整结果。
+ Redis 的键、TTL 和原子操作，以及缓存、临时状态与持久化记录的分工。
+ 缓存过期、资料更新和 Redis 不可用时的行为；弄清 Redis 锁能解决什么，哪些问题还需要数据库约束和事务处理。
+ 身份校验与数据访问范围，在后端检查用户是否有权读取和修改数据。

推荐阅读：

+ [FastAPI 学习入口](https://fastapi.tiangolo.com/zh/learn/)
+ [PostgreSQL：事务](https://www.postgresql.org/docs/current/tutorial-transactions.html)
+ [SQLAlchemy：异步数据库访问](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
+ [Alembic：数据库迁移](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
+ [Redis String 与过期时间](https://redis.io/docs/latest/develop/data-types/strings/)



### 消息队列与后台任务可靠性
导入资料、批量调用模型可能要等很久。这部分学习怎样把任务放到后台，并在断开请求或重启服务后继续查询和处理。

需要掌握：

+ Kafka 的 Topic、Partition、Offset、Producer、Consumer 和 Consumer Group；分区内顺序与跨分区顺序的区别。
+ 自动提交与手动提交位点的差别；在业务完成之前或之后提交，分别有什么风险。
+ 至少一次投递意味着可能重复处理。业务幂等键、最终结果唯一性与消息标识分别解决什么问题。
+ 业务已经写入但位点还没提交、处理中进程退出、重复消息同时到达时，系统怎样恢复。
+ 同分区并发处理时，后完成的消息不能越过尚未完成的较早消息，导致重启后漏处理。
+ 重试次数、退避、最终失败与失败消息留存，避免一条坏消息永远堵住正常任务。
+ 消费延迟、在途任务、优雅停机和重平衡，区分进程存活与任务真正推进。

推荐阅读：

+ [Apache Kafka：基本概念](https://kafka.apache.org/intro/)
+ [aiokafka：消费、位点提交与重平衡](https://aiokafka.readthedocs.io/en/stable/consumer.html)



### 测试、部署与效果验证
需要掌握：

+ 用 pytest 检查核心逻辑和失败分支，用集成测试检查接口、数据库与后台任务；每个测试写清预期结果。
+ 用可控的模型替身模拟超时、非法 JSON、缺字段、工具错误和暂时失败，让常规测试不依赖付费模型调用。
+ 将模型效果测试与程序测试分开：真实模型验证回答与工具选择，模型替身验证错误处理和系统可靠性。
+ 用请求号或任务号关联模型、工具和持久化记录；记录状态、耗时、重试和错误，日志不暴露密钥及敏感内容。
+ Dockerfile、Compose、环境变量、数据卷、健康检查和日志；能排查配置错误、依赖未就绪、服务连不上等问题。
+ GitHub Actions 中运行必要的检查与测试，记录实际使用的依赖版本和运行方式。
+ 从使用者角度验证等待、失败、重试、引用查看和取消。技术接口能调用之后，还要确认用户能理解结果、知道下一步怎么办。

推荐阅读：

+ [pytest 官方文档](https://docs.pytest.org/en/stable/)
+ [Docker Compose](https://docs.docker.com/compose/)
+ [GitHub Actions](https://docs.github.com/en/actions)
