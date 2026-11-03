# LifeOS Phase 1 交付说明

交付日期：2026-11-03。范围为 Windows 本地优先桌面基础，基于远程架构分支提交 `5edcee5`，包含 A 的集成测试和文档更新。B、C、D 的代码已合入。

## 已实现

- PySide6 主窗口展示名称、版本、欢迎信息和数据库连接状态，支持关闭。
- Pydantic Settings 提供版本及可覆盖的数据目录；日志写入轮转文件。
- SQLAlchemy 和 SQLite 提供数据库连接及基础设置读写；Alembic 管理初始迁移。
- AI Provider 定义接口并提供可重复的 Mock，不连接真实模型服务。
- 自动化测试覆盖各模块、迁移及真实组件的隔离集成。公共接口仍需负责人共同确认。

## 环境与启动

使用 Python 3.12 或更高版本，在项目根目录创建虚拟环境并安装依赖。以下为 Windows CMD 示例：

```cmd
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m lifeos
```

如机器没有 `py` 启动器，请使用已安装的 Python 3.12+ 解释器创建虚拟环境。本项目当前使用源码工作目录执行迁移；默认数据库位于 `%LOCALAPPDATA%\LifeOS\data\lifeos.sqlite3`。可通过 `LIFEOS_DATA_DIR` 设置数据目录。常规迁移与应用读取相同配置，显式 `-x url=...` 属于手动指定迁移目标，使用时应确认目标。

## 验证结果

- Windows / Python 3.12.14：`python -m pytest -q` **77 项通过**；`ruff check .` 和 `ruff format --check .` 通过。
- 临时数据库：初始迁移、跨进程写入与读取通过；配置无效时迁移停止且不创建其他数据库；常规迁移与应用数据目录一致。
- Windows Qt：真实入口显示主窗口、数据库状态为已连接，定时关闭后正常退出。尚未完成逐项人工视觉验收。
- 构建 wheel 成功，但产物未包含迁移资源；目前仅验证源码目录方式，不作为独立安装包交付。

## 遗留问题

1. **C / A**：补充安装包中的迁移资源及安装后迁移测试。迁移测试中使用固定文件名写入源码目录的问题也应由 C 改为临时副本。
2. **D**：同一进程切换数据目录重新初始化日志后，旧处理器仍可能写入旧目录；按用户要求暂缓。
3. **B**：状态文字使用固定颜色，在暗色主题下可能对比不足。
4. **A、B、C、D**：确认 `docs/ARCHITECTURE.md` 中的公共接口。实际环境的人工验收尚待完成。

微信、钉钉接入、真实 AI 模型调用、完整任务和提醒引擎、多设备同步均不属于本阶段交付。
