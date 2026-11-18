# T05 AI生成代码修复及调用方检查

核对日期：2026-11-14。代码基线：1.9（`7453cd3673b02d52b110b16503d283e97e3dac9a`）。

状态：**FIX43保留故障原因恢复与调用方验证**。

## 对应要求（原段要点，转述）

选择一处修过的AI生成代码，解释原问题、修改原因和调用方影响检查，核实原因与结果。

来源：[故剑遗学习目标 · 测试与问题修复记录 · 本段](https://biteagle.yuque.com/mw0520/rzyee0/ay7550zlq5vyq27t#ub7740696)。
对应编号：T05。原段SHA256：`561033b56861f4f778ef8d6beba587d2ed07fa6faa2259d16bfbdbdf7b0cb6dc`。

这是原文一个段落的对应回答。要点使用转述；原段定位和哈希用于复核边界，不把此处概括当作公司新要求。

## 回答

选择FIX43：AI协助新增的补充评测用例使用了错误字段source_checks，评测器实际要求sources。原执行顺序在真实模型调用结束后才读取该字段，导致已经付费却以KeyError结束记录。这是评测链路缺陷，不能把它算成问答模型答错。

## 本项目如何实现

**最初问题与定位**：初始补充评测3条记录报KeyError；检查[evaluations/run.py](../../evaluations/run.py)的run_case与新用例结构，发现不合法输入在付费之前没有完整校验。

**实际改动与原因**：修正补充套件字段；增加validate_suite，在网络请求前检查case_set、cases、唯一id、category、非空messages、expected.judgment和sources等必要结构。这样输入错误能在尚未调用模型时直接报错，不让schema问题进入付费阶段。

**调用方影响检查**：固定32条套件通过新校验，文件哈希不变；重复ID和错误字段立即拒绝。CLI、execute/run_case的正常请求及结果格式保留，合法补充套件仍能独立运行。

**结果恢复**：从隔离评测库已有Run读取当时已经生成的答案，单独保存recovered目录与recovery.json，paid_calls_repeated=0；原SSE事件未留存，因此events为空，不能伪造完整事件轨迹。之后修后代码的补充最终运行另存，不能用恢复文件冒充新代码执行。

## 已有验证与证据

- [FIX43及原因说明](../问题修正记录.md)。
- [评测前置校验测试](../../tests/test_evaluation_preflight.py)：错误字段拒绝、正常固定套件通过、重复ID拒绝。
- [初始失败](../../evaluations/results/live-v19-supplemental/results.jsonl)。
- [只读恢复结果](../../evaluations/results/live-v19-supplemental-recovered/results.jsonl)、[恢复范围](../../evaluations/results/live-v19-supplemental-recovered/recovery.json)。
- [修后补充最终运行](../../evaluations/results/live-v19-supplemental-final/results.jsonl)、[全套209项](../evidence/v19-release-final-209.xml)。

证据按各自原日期与运行模式解释。本次建立QA文档未新增付费模型评测或故障注入；已有测试通过也不等于公司正式验收通过。

## 怎样核对或演示

先比较坏套件与有效套件的字段，再确认validate_suite早于HTTP与模型调用。打开recovery.json核对0次重复付费，再看恢复结果缺失事件的说明。对正常调用方核对固定cases.json哈希与新测试，而不是仅凭“现在不报错”。

## 结论与边界

这里记录的是本次AI协助产生并修正的评测代码问题，不把第三方SDK本身归为本项目原创缺陷。前置校验阻止这类结构错误，不能预先判断所有语义预期都正确；规则预期与来源仍需要人工核对。

[返回目录与维护说明](00-目录与持续维护.md)
