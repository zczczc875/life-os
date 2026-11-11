# LifeOS

LifeOS 是 Windows 上的本地任务工具。你可以用一句话添加任务，也可以粘贴整段通知，从生成的草稿中选取要保存的任务。

## 环境与安装

需要 Windows 和 Python 3.12 或更高版本。在项目目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

首次启动前先执行下方数据库迁移，再使用 `python -m lifeos` 启动。启动顺序和接口契约见 [架构文档](docs/ARCHITECTURE.md)。SQLite 默认目录为 `%LOCALAPPDATA%\LifeOS\data\`；安装包或导入模块时不应创建数据。

Phase 2 的任务面板支持添加任务、查看列表并标记完成。首次使用或更新代码后须先迁移至最新版本；任务表缺失时应用会提示迁移。并发完成时间覆盖问题已修复并复测，详见 [Phase 2 交付记录](docs/DELIVERY_PHASE2.md)。

在「我的任务」输入「明天下午 5 点前提交实验报告」，回车即可添加。列表将「提交实验报告」显示为标题，将截止时间显示为 `YYYY-MM-DD 17:00`。也可以只输入标题，例如「整理桌面」。

点击「从通知导入」，粘贴整段通知，再点「生成草稿」。核对或修改提取出的标题和截止时间，再点「保存选中任务」。解析在本机完成。示例和日期规则见 [Phase 3 说明](docs/PHASE3_MESSAGE_DRAFTS.md)，EXE 构建方式见 [Windows 打包文档](packaging/README.md)。

## 迁移与测试

在项目根目录执行 `python -m alembic upgrade head`。可通过环境变量 `LIFEOS_DATA_DIR` 覆盖数据目录；常规迁移与应用使用相同的配置。配置无效时迁移会报错并停止。`-x url=...` 是显式指定迁移目标的高级选项，使用者需确保该目标与应用一致。测试使用独立临时数据库，不得使用正式数据。

```powershell
python -m pytest
ruff check .
ruff format --check .
```

测试覆盖模块、迁移及真实组件的隔离联调；Phase 1 和 Phase 2 结果分别见 [第一阶段记录](docs/INTEGRATION.md)与 [第二阶段记录](docs/DELIVERY_PHASE2.md)。
