# C / Phase 2 任务持久化 交付说明

分支：`feat/phase2-database`　负责人：C　日期：2026-11-04

## 范围

按 `docs/PHASE2_TASKS.md` 分工，C 负责「任务表、Repository、Alembic 迁移和独立临时数据库测试」。
未实现 `lifeos.tasks` 服务层（A 负责），未改动 A、B、D 的任何文件。

## 新增与修改

| 文件 | 内容 |
| --- | --- |
| `src/lifeos/infrastructure/database/models.py` | 新增 `TaskRecord`、`to_naive_utc()`、`as_utc()`（修改） |
| `src/lifeos/infrastructure/database/task_repository.py` | `TaskRepository` 与 `TaskTitleError`（新增） |
| `src/lifeos/infrastructure/database/__init__.py` | 导出任务相关名称（修改） |
| `migrations/versions/0002_tasks.py` | 新增迁移，建 / 删 `tasks` 表（新增） |
| `tests/test_task_repository.py` | 29 项任务持久化测试（新增） |
| `tests/_helpers.py` | 测试共享工具，避免硬编码 head 版本（新增） |
| `tests/test_migration_state.py` | 4 项迁移状态检测测试（新增） |
| `src/lifeos/infrastructure/database/engine.py` | `is_migrated()` 改判 revision；新增 `current_revision()`（修改） |
| `src/lifeos/infrastructure/database/migrate.py` | 新增 `head_revision()`（修改） |
| `tests/test_migrations.py` | 探针迁移改用临时副本；补充源码目录守卫（修改） |
| `tests/test_database.py` 等 4 个文件 | 版本断言改为动态 `head_revision()`（修改） |

**未改写 `0001_app_settings.py`**，符合「不得改写已发布的初始迁移」的要求。

## 需与 A 协调的 Repository 接口（提案）

文档写明「具体构造函数和 Repository 方法由 A、C 协调」。以下是 C 的提案，**待 A 确认**：

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

与服务层三个操作的对应关系：

| `TaskService` | `TaskRepository` | 说明 |
| --- | --- | --- |
| `create_task(title)` | `add(title)` | 标题裁剪后为空时抛 `TaskTitleError`，服务层转为 `TaskValidationError` |
| `list_tasks()` | `list_all()` | 已按「创建时间倒序，相同时 id 升序」排序 |
| `complete_task(id)` | `mark_completed(id)` | 任务不存在返回 `None`，服务层转为 `TaskNotFoundError` |

三点设计取舍，请 A 一并确认：

1. **不提交事务**：沿用 Phase 1 约定，Repository 接收 Session、只 `flush()` 不 `commit()`，
   事务由服务层经 `Database.session_scope()` 管理。
2. **缺失用返回值而非异常表达**：`get()` / `mark_completed()` 对不存在的任务返回 `None`，
   由服务层决定抛 `TaskNotFoundError`。这样 Repository 不依赖服务层的异常类型，避免反向依赖。
3. **返回 ORM 对象**：当前返回 `TaskRecord`。文档要求「界面不依赖数据库 ORM 类型」，
   因此由 A 的服务层转换为 `Task` 数据对象。若 A 希望 Repository 直接返回 `Task`，
   需先确定 `Task` 的定义位置，再由 C 调整——此改动不影响表结构和迁移。

`id` 默认由 `uuid4().hex` 生成（32 字符），列宽留 `String(36)` 以兼容带连字符的 UUID 写法。
若 A 的服务层希望自行生成 id，`add()` 已支持传入 `task_id`。

## 任务表结构

```sql
CREATE TABLE tasks (
    id           VARCHAR(36) NOT NULL,
    title        TEXT        NOT NULL,
    status       VARCHAR(16) NOT NULL,
    created_at   DATETIME    NOT NULL,
    completed_at DATETIME,
    CONSTRAINT pk_tasks PRIMARY KEY (id),
    CONSTRAINT ck_tasks_status CHECK (status IN ('pending', 'completed')),
    CONSTRAINT ck_tasks_completed_at CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
     OR (status = 'pending'   AND completed_at IS NULL)
    )
);
CREATE INDEX ix_tasks_created_at_id ON tasks (created_at DESC, id);
```

两个 CHECK 约束是在存储层设的兜底，防止服务层缺陷写入 UI 无法渲染的状态。
已用原生 SQL 绕过 ORM 验证：非法 `status`、`completed` 无完成时间、`pending` 却有完成时间，
三种情况均被数据库拒绝。

索引对应文档要求的列表排序，避免数据增长后退化为全表排序。

## 时区处理

现有 SQLite 列为**不带时区的 naive UTC**，而 Phase 2 要求服务层使用**带时区的 UTC**。
按文档「写入前须转成 naive UTC，读取到服务层时须恢复 UTC 时区」，提供两个纯函数：

| 函数 | 用途 |
| --- | --- |
| `to_naive_utc(moment)` | 写入前调用。带时区的值先转 UTC 再去掉 tzinfo；naive 值视为已是 UTC |
| `as_utc(moment)` | 读取后调用。给 naive 值附加 UTC；带时区的值归一化到 UTC |

已验证 `+08:00` 的 18:30 会正确存为 10:30，而不是把本地时间当 UTC 写入。
**服务层读取 `created_at` / `completed_at` 后需调用 `as_utc()`**，这一点请 A 注意。

## 语义实现要点

- **标题裁剪**：`add()` 去首尾空白，结果为空抛 `TaskTitleError`（继承 `ValueError`）。
  已测 `""`、空格、制表换行、全角空格 `\u3000` 四种情况，均不写库。
- **重复完成保留原时间**：`mark_completed()` 通过**带条件的单条 `UPDATE`**（`WHERE status = 'pending'`）
  完成，由数据库裁定竞态胜者。已测连续两次完成、以及两个 Session 先读后写的并发完成，
  `completed_at` 均保持首次值。详见下方「并发完成的丢失更新修复」。
- **显式迁移**：未实现任何自动建表。`Database.is_migrated()` 通过比对 Alembic revision
  检测数据库是否为最新，缺表或版本落后均返回 `False`。

## 测试与验证结果

环境：Windows，Python 3.12.6，SQLAlchemy 2.1.6，Alembic 1.20.1，pytest 9.2.0，ruff 0.17.3。

```
python -m pytest -q -o pythonpath=src --ignore=tests/test_end_to_end.py  ->  111 passed
python -m ruff check .                                                   ->  All checks passed!
python -m ruff format --check .                                          ->  48 files already formatted
```

111 项 = C 的 Phase 1 部分 47 项 + 任务持久化 29 项 + 迁移测试 6 项 + 迁移状态 4 项 + A、B、D 的既有测试。
数据库相关测试单独运行：82 passed。

**`tests/test_end_to_end.py` 被排除**：A 的这个测试通过 `subprocess` 启动 Python 子进程，
当前开发沙箱禁止子进程创建（`PermissionError: preserve Python deletion guard`），
与本次改动无关。已确认该限制属环境问题：同样的子进程调用在改动前也失败。
**请 A 在常规 Windows 环境下运行全量 `pytest` 复核这一项。**

补充的手工验证：

- **迁移链**：空库 `upgrade head` 依次执行 `0001` → `0002`，生成 `tasks` 表，版本号 `0002_tasks`；
  `downgrade` 可回滚。
- **模型与迁移无漂移**：autogenerate 比对差异为空。
- **Phase 1 数据保留**（文档验收项）：模拟老用户只升到 `0001` 并写入设置，
  再升级到 `head`，设置完好且可正常创建任务。
- **重启保留**（文档验收项）：创建 + 完成任务后 `dispose()`，新建 engine 重开，
  状态与完成时间均保留。
- **Repository 不提交**：在未提交的 Session 中创建任务后，用独立 `sqlite3` 连接读取，
  确认记录不可见，证明事务边界确实留给服务层。
- **测试有效性**：将列表排序改反、把 `created_at` 改为升序，相应测试均失败，确认非占位测试。

## 已修复的 Phase 1 遗留问题

`docs/DELIVERY_PHASE1.md` 遗留问题 1 中属于 C 的部分（迁移测试使用固定文件名写入源码目录）已修复：
探针迁移改为复制 `migrations/` 到 `tmp_path` 后在副本中创建，源码目录不再被写入。
新增测试断言探针不在 `migrations/versions/` 下，并保留「只有已审查迁移被提交」的守卫。

另外修掉一处本次暴露的脆弱设计：4 个测试文件硬编码 `"0001_app_settings"` 作为 head 版本，
新增迁移后集体失败。已抽出 `tests/_helpers.head_revision()` 动态读取。

## 修复的 `is_migrated()` 误报

开发中验证发现并修复了一个符合文档禁止情形的缺陷：

老用户数据库停在 `0001` 时，`Database.is_migrated()` 返回 `True`（它只检查 `app_settings` 是否存在），
但任何任务操作都会抛 `no such table: tasks`。这正是文档要求避免的「误报任务操作成功」。

已改为比对数据库当前 Alembic revision 与迁移脚本的 head：

| 数据库状态 | revision | `is_migrated()` |
| --- | --- | --- |
| 全新空库 | `None` | `False` |
| 停在 `0001`（老用户） | `0001_app_settings` | `False` |
| 已升到最新 | `0002_tasks` | `True` |
| 有表但无 revision（`create_all`） | `None` | `False` |

同时新增 `Database.current_revision()` 供入口诊断使用，并新增
`migrate.head_revision()` 动态读取 head，避免再次硬编码版本号。

**对 A 的影响**：入口原有的 `if not database.is_migrated(): database.ensure_schema()` 判断
无需改动，语义更准确了——老用户数据库现在会被正确识别为需要升级。

## 并发完成的丢失更新修复（2026-11-04）

A 指出 `mark_completed()` 存在先读后写的丢失更新问题。已复现确认并修复。

**复现**：两个独立 Session 各自 `get()` 到同一个 `pending` 任务后，A 先完成并提交，
B 的 Session 中仍持有 `pending` 快照，`session.get()` 命中 identity map 不回查数据库，
于是把 `completed_at` 覆盖为 B 的时间。实测第一次写入 `2026-05-01T08:00Z`
被覆盖成 `2026-09-09T20:00Z`。

**修复**：改为单条带条件的 `UPDATE`，由数据库保证原子性：

```sql
UPDATE tasks SET status='completed', completed_at=?
 WHERE id = ? AND status = 'pending'
```

未命中（任务不存在或已完成）时不写入任何内容。随后只失效该行的缓存对象并重新读取，
因此返回值始终是数据库中的真实状态——包括另一个 Session 已写入的首次完成时间。
`expire()` 只作用于目标行而非 `expire_all()`，避免连带失效调用方在同一 Session 中的其他对象。

**四项要求的落实**：

| 要求 | 实现 |
| --- | --- |
| 仅 `pending` 可被改为 `completed` | `WHERE status = 'pending'` 条件 |
| 已完成则返回已有结果、保留原时间 | UPDATE 未命中，重新读取返回已存值 |
| 任务不存在仍返回 `None` | 重新读取得到 `None`，公共接口未变 |
| 事务仍由调用方负责 | 只执行语句，不 `commit()`；已用独立连接验证未提交数据不可见 |

**回归测试**（`tests/test_task_repository.py`）：

- `test_concurrent_repeated_completion_keeps_the_first_time`：两个独立 Session 都先读到
  同一 `pending` 任务，B 显式持有陈旧快照，先后完成并提交，最终时间仍为首次写入值。
- `test_a_stale_pending_snapshot_cannot_overwrite_a_completion`：加载对象后由另一 Session
  完成，再用持有陈旧快照的 Session 执行完成，验证守卫在 `UPDATE` 而非前置读取中。

两项均已反向验证：将实现还原为先读后写后，**两个测试都失败**，确认不是占位测试。

### 同时修正的两处测试缺陷

1. 原 `test_concurrent_repeated_completion_keeps_the_first_time` 让任务先被完成，
   再由两个 Session 重复完成，并未构造出真正的竞态；且两个未提交写事务并存会触发
   SQLite `database is locked`。已改为先读后写、依次提交。
2. `test_repository_does_not_commit_on_its_own` 用 `with sqlite3.connect(...)` 探测，
   该上下文管理器只管理事务不关闭连接，导致探测结果不可靠（一度误显示"未提交却可见"）。
   已改为显式 `close()`，并补充回滚后的二次校验。

## 遗留问题与待协调

1. **Repository 接口待 A 确认**：见上方提案，尤其是返回 ORM 对象还是 `Task` 数据对象。
2. **`mark_completed()` 无法区分「本次完成」与「已被他人完成」**（A + C，需决策）：
   修复后该方法返回的是数据库真实状态，而非调用方传入的时间。并发场景下，
   后执行的那次调用会拿到**首次**的 `completed_at`，但返回值本身看不出自己是否是胜者。

   当前对 `TaskService.complete_task` 无影响——文档要求「重复完成已完成任务应成功且保留原完成时间」，
   现有行为正好满足。但若 A 之后需要区分（例如 UI 想提示「该任务已被完成」），
   则需扩展返回值，例如：

   ```python
   def mark_completed(...) -> tuple[TaskRecord | None, bool]: ...   # (记录, 是否本次完成)
   ```

   这会**改动公共接口**，因此本次未擅自实施。请 A 确认是否需要。
3. **安装包迁移资源**（C / A，Phase 1 遗留）：wheel 产物仍未包含 `migrations/`，
   本次未处理，需与打包方式一并决定。
4. **`tests/test_end_to_end.py` 未在本地验证**：见上方说明，需 A 在常规环境复核。
5. 未验证真实 UI 联调，B 的任务界面尚未提供。
