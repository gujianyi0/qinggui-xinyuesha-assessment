# B02 Redis缓存边界与失效

核对日期：2026-11-14。代码基线：1.9（`7453cd3673b02d52b110b16503d283e97e3dac9a`）。

状态：**已实现，命中过期和故障回源已有验证**。

## 对应要求（原段要点，转述）

赋予Redis明确职责，并说明与PostgreSQL的边界、过期和不可用行为。

来源：[故剑遗学习目标 · 后台任务与可靠性 · 本段](https://biteagle.yuque.com/mw0520/rzyee0/ay7550zlq5vyq27t#ud696ee65)。
对应编号：B02。原段SHA256：`cd4c9285d0a701413bff50270b03482967db178075e68961f28ae7ed825711e4`。

这是原文一个段落的对应回答。要点使用转述；原段定位和哈希用于复核边界，不把此处概括当作公司新要求。

## 回答

Redis仅缓存公共知识检索结果，默认TTL为300秒。PostgreSQL保存业务身份、会话、消息、反馈、任务、发布索引和费用账本。缓存丢失不应导致任务状态或正式反馈丢失，也不能用缓存命中证明某任务已经发布。

## 本项目如何实现

[KnowledgeSearch.search](../../backend/app/catalog.py)的缓存键包含快照、发布任务/代次、向量模式/revision、查询和top_k。换发布代次就换键，避免旧索引结果继续命中。命中前还验证结果形状、快照和检索模式，坏缓存也回源。

未命中或Redis异常时，使用已发布PostgreSQL向量/资料查询；未建索引时明确为lexical_unindexed，不冒充语义检索。缓存公共资料，不放私人对话、任务终态或预算权威值。

## 已有验证与证据

- [缓存形状校验](../../backend/app/retrieval_cache.py)、[缓存测试](../../tests/test_retrieval_cache.py)。
- [真实容器结果](../evidence/compose-linux-20261111-04/summary.json)：pgvector_retrieval_and_redis_cache_hit、default_300_second_cache_natural_expiry、redis_outage_pgvector_fallback_and_reconnect。
- [故障回源测试](../../tests/test_jobs.py)：test_cache_down_falls_back_to_published_vectors。
- [历史Redis专项](../1.1-Redis缓存验证与进度-20261111.md)。

证据按各自原日期与运行模式解释。本次建立QA文档未新增付费模型评测或故障注入；已有测试通过也不等于公司正式验收通过。

## 怎样核对或演示

优先打开现有300秒自然过期和停机记录，对比缓存命中/失效/恢复的mode和结果。新的故障复现只在隔离Redis端口或测试Compose进行；不能停正式共享服务来制造本轮文档证据。

## 结论与边界

回源依赖PostgreSQL与本地向量模型可用；Redis回源设计不代表数据库也同时不可用时仍能正常查询。缓存键不是访问控制，私有资源隔离仍在后端鉴权和SQL归属条件中完成。

[返回目录与维护说明](00-目录与持续维护.md)
