# LifeOS 开发约定

动工前阅读 `docs/PRD.md` 和 `docs/ARCHITECTURE.md`。本项目以 Windows 本地优先为目标，使用 Python 3.12+、PySide6、SQLAlchemy 2.x、Alembic、Pydantic Settings 和 pytest；不要自行更换技术栈或扩大阶段范围。

## 维护与模块边界

Phase 3 起由项目所有者单人维护。使用独立功能分支开发，保持公共接口、依赖和入口统一管理。Phase 1、2 的四人分工和确认状态见各阶段原始记录。

- `ui/` 只通过注入的服务及回调读写任务、预览草稿，不访问数据库或实现解析规则。
- `ai/` 只生成草稿，不保存任务或记录通知正文；当前本地解析不联网。
- 任务服务管理事务；数据库模型变更使用新的 Alembic 迁移，保留已发布迁移。

## 实现和验收

- 模块导入不得创建目录、连接数据库、初始化日志或产生其他副作用；这些操作在显式启动时进行。
- 测试使用独立临时数据目录和数据库，不访问用户正式数据。不得提交密钥、真实数据库或日志。
- 日志不记录完整聊天内容。Phase 1 不调用真实模型 API，不接入消息平台，不实现完整任务引擎或多设备同步。
- 在适用条件下运行 `pytest`、`ruff check .`、`ruff format --check .`；记录未执行项及原因。修改数据库结构须附迁移和验证。
- 交付说明包含修改文件、启动与测试命令、结果、遗留问题和责任人。集成前审查每个分支，遇到接口差异先协调。

## 当前范围

Phase 3 的通知草稿与截止日期见 [PHASE3_MESSAGE_DRAFTS.md](docs/PHASE3_MESSAGE_DRAFTS.md)。Phase 2 的任务基线见 [PHASE2_TASKS.md](docs/PHASE2_TASKS.md)。
