# B01 Kafka独立Worker与任务追踪

核对日期：2026-11-14。代码基线：1.9（`7453cd3673b02d52b110b16503d283e97e3dac9a`）。

状态：**已跑通，已有真实Kafka与Worker记录**。

## 对应要求（原段要点，转述）

以Kafka和独立Worker处理任务，HTTP受理后可查状态、结果、失败原因及尝试次数。

来源：[故剑遗学习目标 · 后台任务与可靠性 · 本段](https://biteagle.yuque.com/mw0520/rzyee0/ay7550zlq5vyq27t#u666a8aab)。
对应编号：B01。原段SHA256：`2960904ed51fa7d42d499ab1dcdd8662fe5fa9738488184a0342cc57cc4e0b7a`。

这是原文一个段落的对应回答。要点使用转述；原段定位和哈希用于复核边界，不把此处概括当作公司新要求。

## 回答

已跑通。API不在HTTP请求里完成向量导入，而是创建可追踪Job后返回任务号。独立Worker以`python -m backend.app.worker`运行，通过Kafka接收任务通知，结果和状态写回PostgreSQL。进程独立不等于任务数据只存在进程里。

## 本项目如何实现

`POST /jobs`受理，`GET /jobs`列本人任务，`GET /jobs/{id}`返回状态、progress、error、attempts、generation、result及attempt_records。JobAttempt保存每次执行状态/原因；Outbox保留未投递事件。

实际状态包括queued、running、retry_wait、cancel_requested，以及succeeded/failed/cancelled三个终态。查询不靠Kafka消息还在不在，也不以Redis缓存判断任务完成。

## 已有验证与证据

- [任务接口](../../backend/app/main.py)、[Job/JobAttempt/Outbox模型](../../backend/app/models.py)、[Worker](../../backend/app/worker.py)。
- [1.4真实容器17组](../evidence/compose-linux-20261111-04/summary.json)：导入、进度、重试、取消和恢复。
- [1.9服务快照](../evidence/v19-final-overview.json)：Worker/Kafka等处于运行状态，属于2026-11-13记录。

证据按各自原日期与运行模式解释。本次建立QA文档未新增付费模型评测或故障注入；已有测试通过也不等于公司正式验收通过。

## 怎样核对或演示

2026-11-14本会话通过现有API只读查询alice：14个成功、7个取消，排队/运行/等待重试/取消中均为0；最新任务100%、执行1次。这是当次alice可见任务快照，不是全库所有身份的实时保证。现场以网页后台任务或GET接口查看。

## 结论与边界

API返回202只证明已持久受理，不代表Kafka已经送达或任务已经成功。当前单Worker、单分区用于本机考核；公网访客入口不开放后台任务，后台演示使用本机完整网页。

[返回目录与维护说明](00-目录与持续维护.md)
