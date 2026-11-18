# P10 可复现启动迁移测试与Compose

核对日期：2026-11-14。代码基线：1.9（`7453cd3673b02d52b110b16503d283e97e3dac9a`）。

状态：**已实现，已有CI、容器及匿名客户端验证**。

## 对应要求（原段要点，转述）

提供启动说明、数据库迁移、自动化测试和Docker Compose环境。

来源：[故剑遗学习目标 · 功能要求 · 本段](https://biteagle.yuque.com/mw0520/rzyee0/ay7550zlq5vyq27t#u6a14d6eb)。
对应编号：P10。原段SHA256：`3ba6b825118ee2d0681faae2bdae8257618131b17ea450bc59df514b5d0ecec3`。

这是原文一个段落的对应回答。要点使用转述；原段定位和哈希用于复核边界，不把此处概括当作公司新要求。

## 回答

仓库包含Python/前端锁文件、示例配置、Alembic迁移、Dockerfile、Compose和启动说明。完整环境包括PostgreSQL/pgvector、Redis、Kafka、一次性迁移、API、独立Worker和网页；迁移完成后才启动API。

## 本项目如何实现

[compose.yaml](../../compose.yaml)用于全新自托管；本机已有真实主库使用compose.live.yaml及专用脚本；compose.client.yaml仅运行连接提供者的网页。默认完整自托管是mock，真实模型需要本机配置凭据与单价。

迁移版本0002新增请求恢复数据和隔离评测费用预留表，旧运行允许字段为空，不能借升级重置账本。[GitHub工作流](../../.github/workflows/checks.yml)执行Python测试、Ruff、迁移往返、前端构建及公网入口检查。

## 已有验证与证据

- [README启动命令](../../README.md)、[迁移目录](../../migrations/)、[uv.lock](../../uv.lock)、[前端锁](../../frontend/package-lock.json)。
- [1.4实际容器验证](../1.4-Compose集成与故障恢复验证-20261111.md)。
- [1.9报告](../1.9-裁定约束断线恢复与完整回归-20261113.md)：209项后端、17项前端、匿名拉取与无私有配置客户端构建。
- [main CI](https://github.com/gujianyi0/qinggui-xinyuesha-assessment/actions/runs/43358424593)、[1.9 CI](https://github.com/gujianyi0/qinggui-xinyuesha-assessment/actions/runs/43358424675)。

证据按各自原日期与运行模式解释。本次建立QA文档未新增付费模型评测或故障注入；已有测试通过也不等于公司正式验收通过。

## 怎样核对或演示

查看README的三种入口，不混用已有主库启动与新库Compose。纯客户端只需Docker，不分发提供者密钥。需要验收完整后台时使用本机完整入口，下载版/公网访客没有后台任务操作权限。

## 结论与边界

1.9的匿名干净目录验证是客户端构建；历史完整Linux容器和当前部署的验证另行记录，未声称另一台物理电脑下载全栈后都已实测。CI不运行付费模型或整套Kafka故障注入，不能拿CI绿灯代替这些证据。

[返回目录与维护说明](00-目录与持续维护.md)
