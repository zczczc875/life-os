# Phase 2：任务管理模型与协作接口

## 目标和状态

目标是打通“创建任务 → 查看任务 → 标记完成 → 重启后状态保留”。用户已确认本文件中的任务字段和三个任务服务操作作为 Phase 2 的开发基线；B、C、D 尚需核对实现细节，有冲突先与 A 协调。本文描述的任务功能尚未实现。

Phase 2 保留 Python、PySide6、SQLAlchemy、SQLite、Alembic 和 pytest 技术栈。本阶段不接真实 AI 或消息平台，不实现提醒推送、多设备同步；截止日期、优先级、分类、删除和重新打开任务不在此次最小范围内。

## 任务模型

| 字段 | Python 类型 | 语义 |
| --- | --- | --- |
| `id` | `str` | 唯一标识，创建时由程序生成，之后不变。 |
| `title` | `str` | 任务标题；保存前去掉首尾空白，处理后不能为空。 |
| `status` | `str` 或字符串枚举 | 仅 `pending`（待完成）和 `completed`（已完成）。 |
| `created_at` | `datetime` | 创建时间，使用带时区的 UTC 时间。 |
| `completed_at` | `datetime` 或 `None` | 待完成时为空，完成时为带时区的 UTC 时间。 |

数据使用 SQLAlchemy 由 C 持久化，数据库结构变更必须通过新的 Alembic 迁移完成；不得改写已发布的初始迁移。现有 SQLite 模型采用不带时区的 UTC 时间；若任务表沿用此方式，写入前须转成 naive UTC，读取到服务层时须恢复 UTC 时区，不能混淆本地时间。

## 服务层公共接口

A 负责统一任务服务层。计划由 `lifeos.tasks` 暴露 `Task`、`TaskService` 和下面列出的异常；这些名称当前尚未实现。`Task` 是上表的数据对象，界面不依赖数据库 ORM 类型。

```python
class TaskService:
    def create_task(self, title: str) -> Task: ...

    def list_tasks(self) -> list[Task]: ...

    def complete_task(self, task_id: str) -> Task: ...
```

- `create_task` 去除标题首尾空白；空标题不创建任务，抛出 `TaskValidationError`（继承 `ValueError`）。成功时返回持久化后的 `pending` 任务。
- `list_tasks` 返回全部任务，按创建时间从新到旧排列，时间相同时按 `id` 升序；没有任务时返回空列表。
- `complete_task` 在任务存在时返回更新后的任务；首次完成时设置 `completed_at`。重复完成已完成任务应成功且保留原完成时间；不存在时抛出 `TaskNotFoundError`（继承 `LookupError`）。并发重复完成也应保留首次完成时间。
- 操作成功返回前应完成事务提交；持久化失败时回滚并抛出 `TaskStorageError`（继承 `RuntimeError`）。`Database.session_scope()` 已提供提交、回滚和关闭能力；Repository 与现有约定一致，接收 Session 并由服务管理事务。具体构造函数和 Repository 方法由 A、C 协调。
- B 的 UI 只依赖任务服务；A 将服务注入窗口并负责入口组装，UI 不导入数据库 Repository 或直接执行 SQL。涉及窗口构造函数的具体兼容方式由 A、B 协调。
- C 的 Repository 和 Session 细节由 A、C 在服务边界内协调；C 不直接修改 A 的服务模块。D 的 Provider 只提供结果，不自行创建或持久化任务；将来接入任务前需用户确认。
- 保持显式迁移：数据库连接成功不代表任务表已迁移。缺表或迁移失败时应提示先执行迁移，不能静默创建表或误报任务操作成功。

## 分工和验收

| 负责人 | 工作 |
| --- | --- |
| A | 维护模型与公共接口；实现任务服务、入口组装和集成测试；审查并整合。 |
| B | 任务输入、列表、完成操作和错误提示；UI 测试可使用服务替身。 |
| C | 任务表、Repository、Alembic 迁移和独立临时数据库测试。 |
| D | 维持 Mock Provider 与数据边界，检查配置和隐私；提出未来草稿确认流程建议。 |

建议从包含本文的共同基线分别创建 `feat/phase2-task-service`、`feat/phase2-ui`、`feat/phase2-database` 和 `feat/phase2-ai-boundary`，各自在分支中提交并提出合并请求。

验收至少覆盖：有效标题创建并显示；空标题不写库并提示；完成后状态显示正确；重复完成不改变原完成时间；不存在任务返回明确错误；关闭并重启后数据和状态保留；已有 Phase 1 数据可通过迁移保留。全量 `pytest`、`ruff check .`、`ruff format --check .` 的实际结果必须记录。

**已有遗留问题仍有效**：安装包迁移资源、迁移测试隔离、暗色主题可读性和日志重复初始化，见 `docs/DELIVERY_PHASE1.md`；用户此前要求暂缓日志重复初始化问题。
