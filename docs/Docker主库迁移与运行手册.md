# Docker主库迁移与运行手册

2026-11-12，当前主库qinggui-assessment-live，网页15174、API18081。已有会话、用户、运行、工具、反馈、任务、发布向量及费用账本已完整迁入Docker；旧原生库保留为备份且启动受阻。QQ不属于当前运行范围。

## 日常启动／停止

在项目根目录执行：

```powershell
pwsh -File scripts/start_docker_live.ps1
pwsh -File scripts/stop_docker_live.ps1
```

启动器会启动Docker Desktop并等待Compose就绪。私有配置为.env.docker-live，不进入Git，公开仓库只保留.env.example。停止不删除命名卷、不解除Docker主库标记；重新打开网页后会话和费用继续。

本机普通.env保留mock模式，仅用于独立流程演示；不要用它另开付费主库。完整Compose命令需要指定私有配置、固定项目和两份文件：

```powershell
$env:ASSESSMENT_ENV_FILE = '.env.docker-live'
docker compose --env-file .env.docker-live -p qinggui-assessment-live -f compose.yaml -f compose.live.yaml ps
docker compose --env-file .env.docker-live -p qinggui-assessment-live -f compose.yaml -f compose.live.yaml logs --tail 80 api worker
```

健康接口为http://127.0.0.1:15174/api/health，核对model_mode=live、database=postgresql、cache=available、index_published=true、fault_injection_enabled=false，以及spent/reserved。

## 本次迁移步骤与复验

1. 原生库确认没有运行中问答、未完成任务、未结算费用和未投递Outbox。
2. `python scripts/backup_native_database.py --label 唯一英文标签`停止原生写入方，使用只读PG、ASCII临时盘符，生成私有source.dump及逐表指纹。
3. 准备本项目私有.env.docker-live并构建镜像。`python -m scripts.restore_docker_database --label 相同标签`只接受检查过的冻结源和空目标库，单事务恢复，前后逐表核对；目标已有表时保留并拒绝覆盖。
4. 核对模型参数及源预算，标记Docker为主库后启动服务，进行固定实模、旧会话续问和新任务验证。`python -m scripts.verify_docker_cutover --label 新验证标签`会追加一轮付费真实续问，费用入原账本，并进行冷重建核对；重复执行会新增验证记录及模型费用。

本机已经完成迁移，不能直接重复第2/3步；脚本会检查主库标记和目标内容。原备份在.local/migrations/native-to-docker-v15-20261112，包含完整会话及认证摘要，保持私有，不上传。公开证据只含表数量、内容哈希、费用和验证结果。

工具依据：[PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)、[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)。自定义归档采用-Fc，恢复使用--single-transaction与--exit-on-error；二进制经无TTY的exec -T输入，避免终端改写。

## 恢复边界

服务故障先重启同一Docker项目，保留现有卷；不得因网页暂时失败直接启动旧原生副本。模型调用后，新费用与会话已经只存在Docker主库。若确需切回原生，必须先备份最新Docker库，将其恢复到校验过的目标库，比较内容、已花费用与未结算记录，再调整主库标记；本轮没有提供自动回退到旧费用副本的操作。

删除数据卷、Docker恢复出厂或用迁移前归档覆盖主库不属于普通停止流程。历史Kafka位点没有迁移，因为切换前业务任务及Outbox已全部结束；新任务使用独立live topic/group。公共Redis缓存可重新生成，BGE资产使用锁定revision/哈希，均不能替代PG业务备份。
