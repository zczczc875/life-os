# 架构与协作接口（提案，待确认）

本文是 A 提供给 B、C、D 的首版契约，尚未获得负责人确认，不能标记为共同冻结。各负责人确认类型、异常、行为后由 A 更新，公共接口或依赖变化先协调。

## 边界与启动

Windows、Python 3.12+、PySide6、SQLAlchemy 2.x、Alembic、Pydantic Settings、pytest。入口依次调用配置、日志、数据库连接检查和窗口，之后进入 Qt 事件循环；数据库生命周期由入口管理，退出时释放。UI 只展示状态，不执行 SQL 或 AI 业务。迁移由 Alembic 显式执行，启动不自动修改数据库结构。所有模块导入应无文件、网络或 GUI 副作用。

## 提议公共契约

| 负责人 | 导入路径和签名 | 语义 |
| --- | --- | --- |
| D | `lifeos.config.settings.get_settings() -> Settings` | 无参；对象至少有 `app_version: str`、`data_dir: pathlib.Path`。默认数据目录 `%LOCALAPPDATA%/LifeOS/data`；允许配置覆盖，测试不得使用正式目录。数据库文件名和其他设置由 C、D 与 A 协商。 |
| D | `lifeos.infrastructure.logging.setup.setup_logging(settings: Settings) -> None` | 显式初始化轮转日志；不记录密钥或完整聊天内容。失败抛出异常。 |
| C | `lifeos.infrastructure.database.engine.create_database(settings: Settings) -> Database` | 管理 engine 和 session；`check_connection() -> bool`，成功为 True、连接不可用为 False；`dispose() -> None` 释放资源。初始化或资源管理错误抛出异常。失败状态可交给 UI 展示；不自动运行迁移。 |
| B | `lifeos.ui.main_window.MainWindow(app_version: str, database_status: bool)` | PySide6 窗口；展示名称、版本、欢迎信息和连接状态，支持关闭；不触碰数据库。 |
| D | `lifeos.ai.provider.LLMProvider.extract_tasks(message: str) -> TaskExtractionResponse` | 接收字符串；返回结构化响应，空输入和失败语义见下；Mock 可重复调用，无真实 API。 |

AI 响应提议为 `TaskExtractionResponse(tasks: list[ExtractedTask])`，每项至少 `title: str`；空白输入返回空列表；Provider 处理失败抛出 `ProviderError`，调用者负责处理。不从日志输出消息全文。具体类、校验和异常语义仍须 D 确认；此阶段不要求持久化任务。

入口将初始化异常向上传播并返回非零退出；成功创建数据库后，无论窗口或事件循环是否失败都调用 `dispose()`。Qt 窗口显示前进行本地连接检查；若 C 的检查可能耗时，须在集成时协调非阻塞方案。

## 文件所有权与顺序

A 维护公共依赖、入口、文档和集成测试；B 维护 `ui/`；C 维护 `infrastructure/database/` 和 `migrations/`；D 维护 `config/`、`infrastructure/logging/` 和 `ai/`。各模块测试由负责人维护。先确认契约并在各自分支实现，再由 A 审查合并与验收。此仓库当前未包含其他成员模块。
