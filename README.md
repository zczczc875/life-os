# LifeOS Phase 1

Windows 本地优先桌面工程。界面、数据库、配置、日志和 AI Mock 已合入架构分支；接口仍待 B、C、D 共同确认。验收结果和待解决问题见 [集成记录](docs/INTEGRATION.md)。

## 环境与安装

需要 Windows 和 Python 3.12 或更高版本。在项目目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

首次启动前先执行下方数据库迁移，再使用 `python -m lifeos` 启动。启动顺序和接口契约见 [架构文档](docs/ARCHITECTURE.md)。SQLite 默认目录为 `%LOCALAPPDATA%\LifeOS\data\`；安装包或导入模块时不应创建数据。

Phase 2 的任务面板支持添加任务、查看列表并标记完成。首次使用或更新代码后须先迁移至最新版本；任务表缺失时应用会提示迁移。并发完成时间覆盖问题仍待 C 修复，详见 [Phase 2 协作说明](docs/PHASE2_TASKS.md)。

## 迁移与测试

在项目根目录执行 `python -m alembic upgrade head`。可通过环境变量 `LIFEOS_DATA_DIR` 覆盖数据目录；常规迁移与应用使用相同的配置。配置无效时迁移会报错并停止。`-x url=...` 是显式指定迁移目标的高级选项，使用者需确保该目标与应用一致。测试使用独立临时数据库，不得使用正式数据。

```powershell
python -m pytest
ruff check .
ruff format --check .
```

当前测试覆盖模块、迁移及真实组件的隔离联调；仍需完成实际使用环境验收。详见 [验收记录](docs/INTEGRATION.md)。
