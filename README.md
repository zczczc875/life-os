# LifeOS Phase 1

Windows 本地优先桌面工程。当前交付为 A 的工程骨架和**待 B、C、D 确认的接口草案**；UI、数据库、迁移、配置、日志和 AI Mock 尚待各负责人实现和集成，当前不能启动完整应用。

## 环境与安装

需要 Windows 和 Python 3.12 或更高版本。在项目目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

其他模块合并后，使用 `python -m lifeos` 启动。启动顺序和接口契约见 [架构文档](docs/ARCHITECTURE.md)。SQLite 默认目录为 `%LOCALAPPDATA%\LifeOS\data\`；安装包或导入模块时不应创建数据。

## 迁移与测试

C 交付 Alembic 配置和初始迁移后，在项目根目录执行 `alembic upgrade head`；具体配置及路径覆盖方式待 C、D 确认并补充。在独立临时数据库上运行测试，禁止测试使用正式数据。

```powershell
python -m pytest
ruff check .
ruff format --check .
```

当前测试仅覆盖 A 的启动编排，不能代替各模块测试、迁移验证或 Windows 图形验收。详见 [验收记录](docs/INTEGRATION.md)。
