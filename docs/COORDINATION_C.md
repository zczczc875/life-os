# C → A：待确认与待协调事项清单

分支：`feat/phase2-database`　提出人：C　日期：2026-11-04

本文集中列出需要 A 决策或配合的事项，避免分散在各交付文档中。
**标注「阻塞」的项会影响 Phase 2 验收，建议优先处理。**
每项都给出了 C 的建议方案，确认后 C 可直接实施；C 不自行修改 A、B、D 的文件。

| # | 事项 | 类型 | 影响 |
| --- | --- | --- | --- |
| 1 | Repository 公共接口定稿 | 需确认 | 阻塞 A 的服务层实现 |
| 2 | 服务层读取时间须调用 `as_utc()` | 需知晓 | 阻塞「时区正确」验收 |
| 3 | 入口需调用 `ensure_schema()` | 需 A 改代码 | 阻塞安装版首次启动 |
| 4 | `mark_completed()` 返回值无法区分竞态胜负 | 需确认 | 当前不阻塞 |
| 5 | 数据库文件名写入 `DATA_MODEL.md` | 需 A 改文档 | 不阻塞 |
| 6 | 安装包未包含 `migrations/` | 需协调 | 阻塞独立安装包交付 |
| 7 | `tests/test_end_to_end.py` 需 A 环境复核 | 需 A 验证 | 验收记录完整性 |

---

## 1. Repository 公共接口定稿（阻塞）

`docs/PHASE2_TASKS.md` 写明「具体构造函数和 Repository 方法由 A、C 协调」。
C 已实现以下接口并通过测试，**作为提案提交，请 A 确认或提出修改**：

```python
class TaskRepository:
    def __init__(self, session: Session) -> None: ...

    def add(self, title: str, task_id: str | None = None) -> TaskRecord: ...
    def get(self, task_id: str) -> TaskRecord | None: ...
    def list_all(self) -> list[TaskRecord]: ...
    def mark_completed(
        self, task_id: str, completed_at: datetime | None = None
    ) -> TaskRecord | None: ...
    def count(self) -> int: ...
```

与服务层三个操作的对应：

| `TaskService` | `TaskRepository` | 异常/缺失的处理分工 |
| --- | --- | --- |
| `create_task(title)` | `add(title)` | 标题裁剪后为空抛 `TaskTitleError`，服务层转 `TaskValidationError` |
| `list_tasks()` | `list_all()` | 已按「创建时间倒序，相同时 id 升序」排序 |
| `complete_task(id)` | `mark_completed(id)` | 任务不存在返回 `None`，服务层转 `TaskNotFoundError` |

**需 A 决定的一项**：目前返回 `TaskRecord`（SQLAlchemy ORM 对象）。
文档要求「界面不依赖数据库 ORM 类型」，C 的设计是由服务层转换为 `Task` 数据对象。

- 若维持现状：A 在服务层做转换，C 无需改动。
- 若希望 Repository 直接返回 `Task`：需先确定 `Task` 的定义位置（建议由 A 定义在 `lifeos.tasks`），
  再由 C 调整。**此改动不影响表结构和迁移**，代价较小。

另两点设计取舍，请一并确认：

1. **Repository 不提交事务**：沿用 Phase 1 约定，只 `flush()` / 执行语句，
   事务由服务层经 `Database.session_scope()` 管理。已有测试用独立连接验证未提交数据不可见。
2. **缺失用返回值而非异常表达**：`get()` / `mark_completed()` 对不存在的任务返回 `None`。
   这样 Repository 不依赖服务层的异常类型，避免反向依赖。

`id` 默认由 `uuid4().hex` 生成（32 字符），列宽 `String(36)` 以兼容带连字符写法。
若服务层希望自行生成 id，`add()` 已支持传入 `task_id`。

---

## 2. 服务层读取时间须调用 `as_utc()`（阻塞）

现有 SQLite 列是**不带时区的 naive UTC**，而 `docs/PHASE2_TASKS.md` 要求
`created_at` / `completed_at` 在服务层为**带时区的 UTC**。

C 提供两个纯函数（位于 `lifeos.infrastructure.database.models`）：

| 函数 | 调用时机 |
| --- | --- |
| `as_utc(moment)` | **从 Repository 读出后调用**，给 naive 值附加 UTC |
| `to_naive_utc(moment)` | 写入前调用，Repository 内部已处理 |

```python
from lifeos.infrastructure.database.models import as_utc

record = repository.get(task_id)
task = Task(
    id=record.id,
    title=record.title,
    status=record.status,
    created_at=as_utc(record.created_at),  # 必须
    completed_at=as_utc(record.completed_at),  # 必须，None 安全
)
```

**不调用 `as_utc()` 会导致服务层拿到 naive datetime，不符合文档要求。**
已验证 `+08:00` 的 18:30 会正确存为 10:30 UTC，而非把本地时间当 UTC 写入。

若 A 希望 Repository 直接返回带时区的值（即在 Repository 内部完成转换），
C 可以调整——但那会让 ORM 对象的属性与数据库列语义不一致，故默认交给服务层转换。请 A 选择。

---

## 3. 入口需调用 `ensure_schema()`（阻塞，需 A 改 `app.py`）

`src/lifeos/app.py` 当前未调用迁移。安装版用户双击 exe 没有命令行，
无法执行 `alembic upgrade head`，结果是**首次启动时表不存在**，
UI 显示「已连接」但任何任务操作都抛 `no such table`。

建议改法（`app.py`，属 A 的所有权，C 未改动）：

```python
database = create_database(settings)
try:
    if not database.is_migrated():
        database.ensure_schema()
    database_status = database.check_connection()
    ...
finally:
    database.dispose()
```

`ensure_schema()` 可在每次启动时无条件调用：Alembic 会跳过已应用的版本，
数据库已是最新时为空操作。`is_migrated()` 现已改为比对 Alembic revision，
因此停在 `0001` 的 Phase 1 老库会被正确识别为需要升级：

| 数据库状态 | `current_revision()` | `is_migrated()` |
| --- | --- | --- |
| 全新空库 | `None` | `False` |
| 停在 `0001`（Phase 1 老用户） | `0001_app_settings` | `False` |
| 已升到最新 | `0002_tasks` | `True` |
| 有表但无 revision | `None` | `False` |

若 A 倾向「不自动迁移，而是提示用户先迁移」，C 无需改动模块内部即可配合，
`is_migrated()` 与 `current_revision()` 已可支撑该提示。请 A 选择其一。

---

## 4. `mark_completed()` 返回值无法区分竞态胜负（需确认，当前不阻塞）

修复并发丢失更新后，该方法返回的是**数据库真实状态**，而非本次调用的效果。
并发场景下后执行的调用会收到**首次**的 `completed_at`，但从返回值看不出自己是否是胜者。

**当前不影响 `TaskService.complete_task`**：文档要求「重复完成已完成任务应成功且保留原完成时间」，
现有行为正好满足。

仅当 A 之后需要区分时（例如 UI 提示「该任务已被完成」）才需扩展：

```python
def mark_completed(...) -> tuple[TaskRecord | None, bool]: ...   # (记录, 是否本次完成)
```

这会**改动公共接口**，故本次未擅自实施。请 A 确认是否需要。

---

## 5. 数据库文件名写入 `DATA_MODEL.md`（需 A 改文档）

`docs/DATA_MODEL.md` 写明「数据库文件名由 C、D 与 A 协商」，目前尚未填入。
C 的实现采用 **`lifeos.sqlite3`**，位于 `Settings.data_dir` 下
（默认 `%LOCALAPPDATA%\LifeOS\data\`）。请 A 确认后更新该文档。

已与 D 的 `Settings` 联调验证：仅依赖 `data_dir: Path`，
`database_filename` / `database_path` 为可选覆盖项，D 未定义时自动采用默认文件名。

---

## 6. 安装包未包含 `migrations/`（Phase 1 遗留，需协调）

`docs/DELIVERY_PHASE1.md` 遗留问题 1 的另一半。`pyproject.toml` 未声明包数据，
构建 wheel 时不会带上 `migrations/`，安装后无法迁移。

C 已在代码侧做好准备：`migrate.find_migrations_dir()` 按
「PyInstaller 解包目录 → exe 同级目录 → 源码树」顺序查找，三者都没有时抛
`MigrationError`，错误信息直接提示需将 migrations 作为数据文件打包。

但**打包配置本身属于 A 的所有权**（`pyproject.toml`），且 PyInstaller 方案需要：

```
pyinstaller --add-data "migrations;migrations" -w src/lifeos/__main__.py
```

请 A 决定打包方式（wheel 还是 PyInstaller），C 再配合调整查找逻辑。
**注意**：frozen 分支目前是用 `monkeypatch` 模拟 `sys.frozen` / `sys._MEIPASS` 测试的，
**未实机跑过 PyInstaller**，出包前需实测验证。

---

## 7. `tests/test_end_to_end.py` 需 A 环境复核（需 A 验证）

A 新增的该测试通过 `subprocess` 启动 Python 子进程，
当前 C 的开发沙箱禁止子进程创建（`PermissionError: preserve Python deletion guard`），
因此该项在本地无法运行。

**已确认与 C 的改动无关**：用 `git stash` 回到改动前的代码复测，该测试同样失败。

C 记录的测试结果均为排除该文件后的数据：

```
python -m pytest -q -o pythonpath=src --ignore=tests/test_end_to_end.py  ->  111 passed
python -m ruff check .                                                   ->  All checks passed!
python -m ruff format --check .                                          ->  48 files already formatted
```

数据库相关测试单独运行：**82 passed**。

**请 A 在常规 Windows 环境下运行一次完整 `pytest`**（不加 `--ignore`）以补全验收记录。

---

## 附：C 本次已自行修复、无需协调的项

以下为 C 在职责范围内发现并修复的问题，仅供 A 审查时参考：

- **并发完成丢失更新**：`mark_completed()` 改为带条件的单条 `UPDATE`
  （`WHERE status = 'pending'`），由数据库裁定竞态胜者。两项回归测试已反向验证有效。
- **`is_migrated()` 误报**：原只检查 `app_settings` 是否存在，停在 `0001` 的老库会返回 `True`
  但任务操作失败。已改为比对 Alembic revision。
- **迁移测试写入源码目录**（Phase 1 遗留问题 1 的 C 部分）：探针迁移改为在 `tmp_path`
  的副本中创建，源码目录不再被写入，并新增守卫断言。
- **测试硬编码 head 版本**：4 个测试文件写死 `"0001_app_settings"`，新增迁移后集体失败。
  已抽出 `tests/_helpers.head_revision()` 动态读取。
- **测试探测方式不可靠**：`with sqlite3.connect(...)` 只管理事务不关闭连接，
  曾导致事务边界检查结果失真。已改为显式 `close()`。
