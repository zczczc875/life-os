# C / 数据库与持久化 交付说明

分支：`feat/phase1-database`　负责人：C　日期：2026-11-03

## 范围

按 `AGENTS.md` 的所有权，本次只新增 `src/lifeos/infrastructure/database/`、`migrations/`、`alembic.ini` 和 `tests/test_database.py`。
未修改 A 的入口、文档、`pyproject.toml`、`.gitignore`，也未触碰 B、D 的目录。

## 新增文件

| 文件 | 内容 |
| --- | --- |
| `src/lifeos/infrastructure/__init__.py` | 包声明（原仓库缺失，导入 `infrastructure.database` 必需） |
| `src/lifeos/infrastructure/database/__init__.py` | 导出 `create_database`、`Database`、`Base`、`AppSetting`、`SettingsRepository` 等 |
| `src/lifeos/infrastructure/database/engine.py` | Engine、Session 工厂、`create_database`、`check_connection`、`dispose` |
| `src/lifeos/infrastructure/database/models.py` | `Base` 与 `app_settings` 模型 |
| `src/lifeos/infrastructure/database/repository.py` | `SettingsRepository`：`get` / `set` / `delete` / `all` / `exists` |
| `src/lifeos/infrastructure/database/url.py` | 数据库位置解析，含打包（frozen）环境判断 |
| `src/lifeos/infrastructure/database/migrate.py` | 代码内迁移 `upgrade_to_head`，供安装版自动建表 |
| `alembic.ini` | Alembic 配置，`script_location = migrations`，`prepend_sys_path = src` |
| `migrations/env.py` | 迁移环境，解析数据库 URL |
| `migrations/script.py.mako` | 迁移模板 |
| `migrations/versions/0001_app_settings.py` | 初始迁移，建 / 删 `app_settings` |
| `tests/test_database.py` | 17 项数据库测试，全部使用临时库 |
| `tests/test_packaging.py` | 11 项安装 / 打包行为测试 |
| `tests/test_migrations.py` | 4 项迁移演进测试（叠加、回滚、模型漂移、残留守卫） |
| `tests/test_settings_contract.py` | 7 项与 D 真实 `Settings` 的契约联调测试 |
| `tests/test_migration_target.py` | 8 项迁移目标解析测试（A 的审查意见） |

## A 的审查意见处理（2026-11-03）

> 配置出错时停止迁移；统一迁移和应用使用的数据库路径；补充相应测试。

两项意见均已复现确认为真实缺陷，根因相同：`env.py` 自建了一套路径解析，与应用端脱节。

**问题 1：配置出错被静默吞掉**

原 `_url_from_settings()` 捕获异常后 `return None`，继而回退到 `%LOCALAPPDATA%` 默认路径。
实测：把 `LIFEOS_LOG_MAX_BYTES` 设为非法值后，`Settings` 校验失败，迁移却照常在默认位置建表——
用户配置的目录被无声忽略。
现改为抛出 `MigrationTargetError` 并终止，错误信息包含具体的校验失败字段。

**问题 2：迁移与应用可能指向不同文件**

原解析链包含我自造的 `LIFEOS_DATABASE_URL`，优先级高于 `Settings`，而 D 的配置用的是
`LIFEOS_DATA_DIR`，两套机制互不知情。实测可造成迁移在 A 文件建表、应用打开 B 文件，
最终表现为 `no such table`。
现已移除该旁路，迁移与应用统一走 `resolve_target(settings)`。
`upgrade_to_head()` 另增校验：迁移后读不到 revision 即报错，避免“静默成功但表在别处”。

**测试有效性验证**：新增 8 项测试后，分别将两处修复临时还原，确认测试会失败
（问题 1 → 2 项失败，问题 2 → 1 项失败），证明不是走空路径的占位测试。

**真实迁移验证**：配置损坏时 `alembic upgrade head` 确实拒绝执行；
设置 `LIFEOS_DATA_DIR` 后迁移跟随该目录，旧旁路变量已失效，目录下仅生成一个数据库文件。

## 接口实现情况

按 `docs/ARCHITECTURE.md` 的提案实现，签名一致：

- `create_database(settings) -> Database`：确保数据目录存在、创建 engine；**不建表、不跑迁移**。初始化失败抛 `DatabaseError`。
- `Database.check_connection() -> bool`：可读返回 `True`，连接或文件不可用返回 `False`（不抛给 UI）。
- `Database.dispose() -> None`：释放连接池，可重复调用。
- 额外提供 `engine`、`path`、`url`、`session()`、`session_scope()`，供集成和其他模块按需使用。
- 额外提供 `is_migrated() -> bool`（见下方遗留问题 3），用于区分「连得上」和「可用」。

### 对 Settings 的依赖（已与 D 的实现联调验证）

D 的 `config/settings.py` 已合入主干（PR !1）。已用**真实 `Settings` 对象**而非测试替身验证，契约吻合：

| C 的要求 | D 的实现 | 结果 |
| --- | --- | --- |
| `app_version: str` | `app_version: str = "0.1.0"` | 一致 |
| `data_dir: Path` | `data_dir: Path`，默认 `%LOCALAPPDATA%\LifeOS\data` | 一致 |
| 数据目录可覆盖 | `LIFEOS_DATA_DIR` 环境变量 | 已验证贯通到数据库与迁移 |

`settings` 只按属性读取，当前支持三种形态，优先级从高到低：

1. `settings.database_path`：直接指定数据库文件。
2. `settings.data_dir` + `settings.database_filename`。
3. `settings.data_dir` + 默认文件名 `lifeos.sqlite3`。

D 的 `Settings` 未定义 `database_path` / `database_filename`，属**可选覆盖项**，缺失时自动走第 3 条，
已有测试覆盖该情形。`docs/DATA_MODEL.md` 中「数据库文件名由 C、D 与 A 协商」一项，C 方提议取
**`lifeos.sqlite3`**，待 A 确认后写入文档。

注意：`get_settings()` 带 `lru_cache`。同进程内先调用过它再改环境变量时，需 `get_settings.cache_clear()`
才会生效；命令行迁移在独立进程中执行，不受影响。已有测试固化该行为。

## 对照 C 的完成标准逐条验收

文档原文：「数据位于 `%LOCALAPPDATA%\LifeOS\data\`；配置路径可覆盖；迁移可执行；设置可插入、查询、修改，
重启后保留。结构变更由 Alembic 管理。」

| 标准 | 结果 | 证据 |
| --- | --- | --- |
| 数据位于 `%LOCALAPPDATA%\LifeOS\data\` | 通过 | 默认解析为 `…\LifeOS\data\lifeos.sqlite3`；另有测试断言不落在安装目录下 |
| 配置路径可覆盖 | 通过 | 三种覆盖均生效：`data_dir`、`data_dir`+`database_filename`、`database_path` |
| 迁移可执行 | 通过 | 空库 `upgrade head` 成功；命令行与代码内两种方式均验证 |
| 设置可插入、查询、修改 | 通过 | `set` / `get` / `all` / `delete` / `exists` 均有测试 |
| 重启后保留 | 通过 | `dispose()` 后新建 engine 重开数据仍在；并用原生 `sqlite3` 直读文件确认落盘 |
| 结构变更由 Alembic 管理 | 通过 | 见下方「迁移演进验证」 |

交付清单要求的 `engine.py`、`models.py`、`repository.py`、`app_settings` 表、`migrations/` 与初始迁移、
`tests/test_database.py` 均已就位。

### 迁移演进验证

仅验证「初始迁移能建表」不足以证明结构变更受 Alembic 管理，因此补充 `tests/test_migrations.py`：

- **后续迁移可叠加且不丢数据**：模拟用户已装旧版并存有设置，再引入第二个迁移，`ensure_schema()`
  正确升级、新列出现、原有设置完好。这正是「发布新版本后老用户数据不丢」的场景。
- **可回滚**：`downgrade` 撤销新列后，已存设置仍在。
- **模型与迁移无漂移**：用 Alembic autogenerate 比对 `models.py` 与迁移后的库，差异为空，
  可拦住「改了模型却忘写迁移」这一常见错误。
- **残留守卫**：断言 `migrations/versions/` 只含已审查的 `0001_app_settings.py`。
  已反向验证该守卫有效（放入多余迁移文件即失败）。

测试用的探针迁移在运行时生成、结束即删除，不会提交进仓库。

## 安装版 / exe 分发支持

目标形态是「打包成安装包或 exe 发给用户，各自本地使用、数据各自独立」。这带来两个数据层约束，已实现并测试：

**1. 终端用户没有命令行，必须能自动建表**

原设计要求先手动执行 `alembic upgrade head`。用户双击 exe 不会开命令行，结果是表不存在、读写设置直接抛
`no such table: app_settings`。为此新增：

```python
database = create_database(settings)
if not database.is_migrated():
    database.ensure_schema()  # 代码内执行迁移，等效于 alembic upgrade head
```

`ensure_schema()` 可在每次启动时无条件调用：Alembic 会跳过已应用的版本，数据库已是最新时为空操作。
**这需要 A 在 `app.py` 启动流程中加一次调用**（见遗留问题 3），C 不擅自改入口。

**2. 打包后 `migrations/` 不在源码目录**

PyInstaller 会把数据文件解包到 `sys._MEIPASS`，源码树不存在。`migrate.find_migrations_dir()` 按
「bundle 目录 → exe 同级目录 → 源码树」顺序查找，三者都没有时抛 `MigrationError`，错误信息直接提示
「打包时需把 migrations 作为 data files 一并打包」，避免这类配置漏项在用户机器上才暴露。

打包时需要（由 A 或负责打包的人配置，示例）：

```
pyinstaller --add-data "migrations;migrations" -w src/lifeos/__main__.py
```

**3. 数据不写在安装目录**

默认仍为 `%LOCALAPPDATA%\LifeOS\data\`。安装目录（如 `C:\Program Files\...`）通常只读，且升级时会被替换，
把数据库写在那里会失败或丢数据。已有测试断言默认路径不在可执行文件所在目录下。

## 数据表

```sql
CREATE TABLE app_settings (
    "key"      VARCHAR(128) NOT NULL,
    value      TEXT         NOT NULL,
    updated_at DATETIME     NOT NULL,
    CONSTRAINT pk_app_settings PRIMARY KEY ("key")
);
```

Phase 1 只需字符串设置，故 `value` 为 `TEXT`。`updated_at` 为**朴素 UTC**（SQLite 不保留时区），由模型的 `default` / `onupdate` 维护。

## 迁移操作

**安装版 / 普通用户**：无需任何操作，首次启动由 `ensure_schema()` 自动建表（前提是 A 已在入口调用）。

**开发者**（命令行方式仍然可用）：

```powershell
# 跟随应用配置（LIFEOS_DATA_DIR），默认 %LOCALAPPDATA%\LifeOS\data\lifeos.sqlite3
alembic upgrade head

# 隔离环境：改配置，迁移与应用会一起跟随
$env:LIFEOS_DATA_DIR = "D:\tmp\lifeos"; alembic upgrade head

# 仅运维排查时直接指定文件（绕过配置，请谨慎）
alembic -x url=sqlite+pysqlite:///D:/tmp/lifeos.sqlite3 upgrade head
```

`migrations/env.py` 的解析顺序：代码内调用传入的 `config.attributes["lifeos_url"]` →
`-x url=` → `lifeos.config.settings.get_settings()`。

**配置无法读取时直接报 `MigrationTargetError` 并终止，不再回退到默认路径**；
迁移与应用共用 `resolve_target(settings)`，因此两者解析到的始终是同一个文件。

## 测试与验证结果

环境：Windows，Python 3.12.6，SQLAlchemy 2.1.6，Alembic 1.20.1，pytest 9.2.0，ruff 0.17.3。

```
python -m pytest -q -o pythonpath=src   ->  65 passed
python -m ruff check .                  ->  All checks passed!
python -m ruff format --check .         ->  36 files already formatted
```

65 项 = C 的 47 项（数据库 17、安装/打包 11、迁移演进 4、Settings 契约 7、迁移目标 8）
+ A 原有集成 3 项 + D 的 15 项（配置、日志、AI Provider）。

### 与 D 的合并与联调（2026-11-03）

已将主干 `feat/phase1-architecture`（含 D 的 PR !1）合入本分支：

- **冲突**：仅 `src/lifeos/infrastructure/__init__.py` 一处（双方都新建了该包声明）。
  已采用 D 的版本（描述更完整，且属先合并方），C 无实质损失。
- **全量测试**：合并后 57 项全部通过，C 与 D 的测试无相互干扰。
- **启动顺序联调**：按 `app.py` 的顺序串联「配置 → 日志 → 数据库 → 连接状态 → dispose」，
  实际生成了日志文件与数据库文件，流程贯通（窗口部分待 B）。
- `pyproject.toml` 已由 A 声明 `pydantic-settings`，无需改动。

补充的手工验证：

- **模拟 exe 首次启动**：数据目录完全不存在的情况下，`create_database` → `ensure_schema()` 自动建表成功，
  写入设置后用原生 `sqlite3` 直读文件确认落盘（20480 bytes）；第二次启动 `ensure_schema()` 为空操作且数据保留。
- **空库迁移**：全新临时文件上 `upgrade head` 成功，版本 `0001_app_settings`；`downgrade base` 可回滚。
- **持久化**：写入后 `dispose()`，新建 engine 重开，设置仍在并可修改。
- **连接检查**：对损坏文件返回 `False`。注意 `SELECT 1` **不足以**检测损坏库（SQLite 延迟校验文件头）。
- **未迁移库**：`check_connection()` 为 `True` 而 `is_migrated()` 为 `False`，见遗留问题 3。
- **含空格路径**：`Local App Data\Life OS` 这类路径可正常建库读写。
- **导入无副作用**：导入模块后真实目录 `%LOCALAPPDATA%\LifeOS\data` 未被创建。
- 全部测试使用 `tmp_path` 临时目录，未访问正式数据库。

### 开发中修正的两个缺陷

1. `check_connection()` 原用 `SELECT 1`，在损坏的数据库文件上仍返回 `True`（SQLite 延迟校验文件头）。
   已改为通过 SQLAlchemy `inspect` 列举表名。
2. 代码内迁移原通过 `Config.set_main_option("sqlalchemy.url", ...)` 传 URL，Windows 路径被 URL 编码后含 `%`，
   被 ConfigParser 当作插值语法而报 `invalid interpolation syntax`。已改为经 `config.attributes` 传递，
   `env.py` 也相应改用 `create_engine` 而非 `engine_from_config`。两者都由测试捕获。

## 遗留问题与待协调（责任人）

> 其中仍未关闭的项（入口调用 `ensure_schema()`、数据库文件名确认、安装包迁移资源）
> 已连同 Phase 2 事项合并整理在 [`docs/COORDINATION_C.md`](COORDINATION_C.md)。

1. **数据库文件名确认**（A + D）：C 提议 `lifeos.sqlite3`，需 A 更新 `docs/DATA_MODEL.md`。
2. **Settings 字段确认**（D）：已联调验证，`data_dir: Path` 与 `app_version: str` 均符合约定，无需调整。
3. **入口需增加一次 `ensure_schema()` 调用 —— 需 A 配合，影响安装版可用性**：
   按架构文档约定，`create_database` 不跑迁移。但目标形态是分发 exe 给用户，用户没有命令行，
   因此必须由程序自己建表。实测确认：全新未迁移的数据库 `check_connection()` 返回 `True`
   （文件能连上，只是没有表），UI 会显示「已连接」，但任何设置读写都抛
   `OperationalError: no such table: app_settings`。
   C 已提供 `is_migrated()` 和 `ensure_schema()`，**未改动 `check_connection()` 的既有语义**。
   建议 A 在 `app.py` 的 `create_database` 之后加入：

   ```python
   database = create_database(settings)
   try:
       if not database.is_migrated():
           database.ensure_schema()
       database_status = database.check_connection()
       ...
   ```

   若 A 倾向另一种方案（如启动时提示用户而非自动迁移），C 无需改动模块内部即可配合。
4. **连接检查耗时**（A + B）：本地 SQLite 的 `check_connection()` 为毫秒级，暂不需要非阻塞方案；若后续数据量变大再评估。
5. `pyproject.toml` 未声明 `pytest` 的 `pythonpath`，故测试需 `-o pythonpath=src` 或先 `pip install -e .`；是否固化由 A 决定（属 A 的所有权文件，C 未改）。
6. 未验证真实 UI 联调与 `python -m lifeos` 端到端启动，因 B 的模块尚未提供。
   D 的配置与日志已合并并联调通过。
7. **打包配置尚未实际验证**（A / 负责打包的人）：`find_migrations_dir()` 的 frozen 分支是用
   `monkeypatch` 模拟 `sys.frozen` / `sys._MEIPASS` 测试的，**没有真正跑过 PyInstaller 打包**。
   真正出包时需确认 `--add-data "migrations;migrations"` 生效，并在干净的 Windows 机器上
   双击验证首次启动建库。这超出 C 的职责范围，但属于分发前必做项。
8. **单用户假设**：`app_settings` 主键只有 `key`。按当前「各自本地使用、数据各自独立」的形态，
   这是正确且足够的。若将来改为多人共用一份数据，所有业务表都需要加用户归属字段——届时属于
   数据模型层面的变更，需走迁移。
