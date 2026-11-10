# 固定样例与评测

`cases.json` 固定32条规格：8规则、6结构化、8裁定、3多轮、2冲突、2无答案、1工具失败、2反馈不足。来源来自本次冻结的本地外层三个业务包。`build_cases.py` 只重建规格文件，不调用模型。

每条均有输入、前提、预期工具、人工核对规则和来源定位。8条裁定以实际离线规则引擎证据为判据；没有执行证据时保持待验证。

## 手动运行

启动后端、创建迁移并导入资料后，从项目根执行：

```powershell
uv run python -m evaluations.run --mode mock --label mock-baseline
```

模型服务、精确模型ID、价格和本地密钥配置完成，后端 `/health` 明确返回 `model_mode=live` 后，才能运行真实模型记录：

```powershell
uv run python -m evaluations.run --mode live --label live-before-01
# 完成实际修正后，使用相同 cases.json
uv run python -m evaluations.run --mode live --label live-after-01
```

脚本核对实际模式并保存用例文件SHA256，模式不符立即停止。`--only R01,D01` 可跑子集，结果明确标注覆盖范围。目录名不可复用，避免覆盖基线。

后端预算控制负责总额200元上限；运行此脚本不会读取旧轻归密钥。模型及提示词版本、工具调用、运行号、耗时和用量从后端记录中保存。用量或价格缺失时只能视为估算。

## 受控工具失败

F01要求真实注入工具不可用，而非让模型口头描述失败。只有后端显式启用测试故障注入并在 `/health` 返回 `fault_injection_enabled=true` 时，脚本才发送 `X-Assessment-Fault: tool_unavailable`。否则该条记录为 `blocked`，不能计作通过。

## 报告解释

每轮保存 `metadata.json`、`results.jsonl` 和 `summary.json`，包括实际HTTP/SSE结果、工具审计和人工审查入口。

自动检查只核对终止事件、工具名、引用存在和关键词，**不代表语义正确**。人工逐条核对预期、原文、引用及版本后补充评审记录。真实模型、替身、规则引擎执行和真人试用分别留档；当前没有真实模型或真人试用结果时，不填写通过率。
