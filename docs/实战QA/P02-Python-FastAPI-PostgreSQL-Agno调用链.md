# P02 Python-FastAPI-PostgreSQL-Agno调用链

> 1.10补充（2026-11-14）：正文去除可见Markdown标记与源码位置，引用改为回答末尾按钮展开；原始正文、来源、行号和版本仍保留。此次前端22项、后端相关49项通过，旧1.9完整32条真实回归仍是历史证据，不冒充新提示词的全量实测。见[1.10报告](../1.10-回答展示与浏览器排查-20261114.md)。

核对日期：2026-11-14。代码基线：1.9（`7453cd3673b02d52b110b16503d283e97e3dac9a`）。

状态：**已实现，已有容器与真实模型证据**。

## 对应要求（原段要点，转述）

使用指定技术栈，打通用户输入、模型调用、工具执行和结果持久化。

来源：[故剑遗学习目标 · 功能要求 · 本段](https://biteagle.yuque.com/mw0520/rzyee0/ay7550zlq5vyq27t#ue59711c5)。
对应编号：P02。原段SHA256：`55e955947974cc2a2a8850fe0e2c6cabf9dea763d0d2b7887aba1ef6dea93168`。

这是原文一个段落的对应回答。要点使用转述；原段定位和哈希用于复核边界，不把此处概括当作公司新要求。

## 回答

本项目已经打通这条链路：React输入通过FastAPI进入应用，校验身份和会话归属后创建Run；Runtime使用Agno异步调用模型与受控工具；工具回执、最终正文、引用、用量和状态写入PostgreSQL，网页从SSE或轮询读取结果。

## 本项目如何实现

主要入口在[main.py](../../backend/app/main.py)的create_app、create_run与受理接口。模型执行在[runtime.py](../../backend/app/runtime.py)的Runtime.execute：Agno负责模型/工具循环，应用负责权限、预算、取消和最终保存。

网页默认发送`POST /sessions/{id}/submissions`，先返回202和run_id，本机再GET运行事件流，公网轮询`GET /runs/{id}`。历史`POST /sessions/{id}/runs`流式接口仍用于评测。消息及Run先落库，不能把HTTP已受理等同于模型已完成。

## 已有验证与证据

- [数据库模型](../../backend/app/models.py)：ChatSession、Message、Run、ToolCall、UsageRecord等。
- [真实运行](../../evaluations/results/live-v19-full-04/results.jsonl)：可查model_mode、model_id、prompt_version、tool_calls与usage。
- [部署核对](../evidence/v19-final-r4-runtime-source.json)：正式与隔离评测容器业务字节相符、安装版本1.9.0。
- [公网保存运行](../evidence/v19-browser-recovery-05/saved-run.json)：实际live请求与工具/持久化结果。

证据按各自原日期与运行模式解释。本次建立QA文档未新增付费模型评测或故障注入；已有测试通过也不等于公司正式验收通过。

## 怎样核对或演示

挑选一个已保存run_id，依次对照用户输入、ToolCall、回答引用、最终status和用量。现场查看时用有效身份查询自己的运行，不新建付费请求来证明已经存在的记录。

## 结论与边界

原轻归仅提供获授权的模型服务配置来源，运行不依赖其聊天进程或数据库。本机轻量演示会用SQLite和模型替身，不能据此声称PostgreSQL/真实模型链路已经验证；证据中的模式必须分别检查。

[返回目录与维护说明](00-目录与持续维护.md)
