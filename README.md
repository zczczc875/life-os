# LifeOS

LifeOS 是 Windows 上的本地任务工具。你可以用一句话添加任务，也可以粘贴整段通知，从生成的草稿中选取要保存的任务。

在 [GitHub Releases](https://github.com/zczczc875/life-os/releases) 下载 Windows x64 的 `LifeOS.exe`，双击即可启动。首次启动时按提示初始化本地数据库。

v0.2.0 已支持按截止时间排序和今日计划。各阶段交付、验证记录与后续安排见 [项目路线图](docs/ROADMAP.md)。

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

选中任务列表里的一项，再点「编辑任务」，即可修改标题和截止时间。截止时间可填写 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm`，清空后保存即可移除。已完成任务的勾选和完成时间保留，逾期状态按修改后的截止时间计算。

## 今日计划

点击「今日计划」查看未完成任务。列表按已逾期、今天到期、本周到期、之后到期、未设截止日期分组，同组内截止时间早的排在前面。只填写日期的任务按当天结束排序，今天是否逾期以本机日期和分钟为准。

计划窗口打开期间会随本机时间更新到期分组。点击「刷新」可以重新读取已保存的任务。

计划会标出排在最前的三项作为今日建议。逾期和今天到期的任务优先级高，之后有截止日期的任务为中优先级，未设截止日期的任务为低优先级。勾选主界面的「按优先级排序」，也可以按此规则整理待办列表。

## 迁移与测试

在项目根目录执行 `python -m alembic upgrade head`。可通过环境变量 `LIFEOS_DATA_DIR` 覆盖数据目录；常规迁移与应用使用相同的配置。配置无效时迁移会报错并停止。`-x url=...` 是显式指定迁移目标的高级选项，使用者需确保该目标与应用一致。测试使用独立临时数据库，不得使用正式数据。

```powershell
python -m pytest
ruff check .
ruff format --check .
```

测试覆盖模块、迁移及真实组件的隔离联调；Phase 1 和 Phase 2 结果分别见 [第一阶段记录](docs/INTEGRATION.md)与 [第二阶段记录](docs/DELIVERY_PHASE2.md)。
