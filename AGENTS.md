# LifeOS Phase 1 协作约定

动工前阅读 `docs/PRD.md` 和 `docs/ARCHITECTURE.md`。本项目以 Windows 本地优先为目标，使用 Python 3.12+、PySide6、SQLAlchemy 2.x、Alembic、Pydantic Settings 和 pytest；不要自行更换技术栈或扩大阶段范围。

## 所有权

- A：项目规则、依赖、公共接口、入口、文档和集成测试；负责审查与合并。
- B：`src/lifeos/ui/` 和 UI 测试；窗口只展示传入的数据，不直接访问数据库或执行业务 AI。
- C：`src/lifeos/infrastructure/database/`、`migrations/` 和数据库测试；数据库结构变化使用 Alembic。
- D：`src/lifeos/config/`、`src/lifeos/infrastructure/logging/`、`src/lifeos/ai/` 和对应测试。

各成员使用独立分支或 worktree，原则上只修改负责范围。公共接口和共享依赖由 A 统一维护；需要变更时先协调。不要绕过模块边界或擅自修改其他模块内部实现。`docs/ARCHITECTURE.md` 是接口约定及其确认状态的依据；在负责人确认前，不应把提案描述为全员已冻结。

## 实现和验收

- 模块导入不得创建目录、连接数据库、初始化日志或产生其他副作用；这些操作在显式启动时进行。
- 测试使用独立临时数据目录和数据库，不访问用户正式数据。不得提交密钥、真实数据库或日志。
- 日志不记录完整聊天内容。Phase 1 不调用真实模型 API，不接入消息平台，不实现完整任务引擎或多设备同步。
- 在适用条件下运行 `pytest`、`ruff check .`、`ruff format --check .`；记录未执行项及原因。修改数据库结构须附迁移和验证。
- 交付说明包含修改文件、启动与测试命令、结果、遗留问题和责任人。集成前审查每个分支，遇到接口差异先协调。

## Phase 2 任务管理

Phase 2 的范围、任务模型、服务接口和成员分工见 `docs/PHASE2_TASKS.md`。本阶段允许实现该文档所列的最小任务管理功能；Phase 1 的既有范围和验收记录保持不变。公共接口、依赖和入口由 A 维护，数据库、UI、AI 模块内部实现仍由对应负责人维护。
