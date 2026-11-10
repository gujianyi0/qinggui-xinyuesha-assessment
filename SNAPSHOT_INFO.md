# 本地版本快照说明

- **来源目录**：`F:\Work\Biteagle\入职考核`（工作区，非 git 仓库）
- **本仓库**：`F:\Work\Biteagle\入职考核\git`，分支 `main`，标签 `v1.0`
- **版本标记**：源目录 `VERSION` 文件内容为 `1.0`
- **快照时间**：2026-11-10
- **性质**：纯本地仓库，**没有配置任何远端，没有推送**。本仓库只用于保存当前版本，不改动远端。

## 纳入范围

按源目录 `.gitignore` 的规则纳入当前版本：源码、配置样例、文档、评测证据、数据、脚本、测试、迁移、裁定记录等。

明确排除（未进入仓库）：

- `.env`、`.env.*`（密钥；仅保留 `.env.example`）
- `.venv/`、`.local/`、`frontend/node_modules/`、`frontend/dist/`、`frontend/coverage/`
- `__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`htmlcov/`、`evaluation-runs/`
- `*.pyc` / `*.pyo` / `*.pyd`、`*.sqlite3*`、`*.tmp`、通用 `*.log`
- `git/` 自身（避免递归）
- `.gitignore` 的例外 `!docs/evidence/**/*.log` 已遵守，19 个证据日志已纳入

## 注意

`docs/evidence/worker-soak-20261110-02/` 下的 `samples.jsonl` 与 `progress.json` 是**运行中评测进程持续写入**的实时产物。本仓库保存的是快照时刻的内容；之后源目录若继续写入，两者会有差异，需要时再同步一次即可。

## 核验

- 每个纳入文件均按 SHA-256 与源目录逐字节比对
- `git remote -v` 为空
- 工作区干净（`git status --porcelain` 为空）
