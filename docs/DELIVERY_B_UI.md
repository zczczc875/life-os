# B：Phase 2 任务界面交付说明

分支 `feat/phase2-ui`，基线 `feat/phase1-architecture`。范围仅限 `src/lifeos/ui/` 及其测试，未改动数据库、配置、AI 和入口。

## 修改文件

| 文件 | 说明 |
| --- | --- |
| `src/lifeos/ui/task_panel.py` | 新增。任务输入、列表、完成操作和错误提示；只依赖注入的服务。 |
| `src/lifeos/ui/main_window.py` | 主窗口内嵌任务面板；构造函数新增可选的 `task_service` 关键字参数。 |
| `tests/test_ui_tasks.py` | 新增。使用服务替身覆盖 B 的验收项（不访问数据库）。 |
| `docs/DELIVERY_B_UI.md` | 本文件。 |

## 实现要点

- **窗口兼容**：`MainWindow(app_version, database_status, task_service=None)`。原有两参数调用方式不变；未注入服务时任务区禁用并显示“任务服务尚未接入，暂不可用”，入口组装仍由 A 负责。
- **只依赖服务**：`TaskPanel` 通过局部 `TaskService` 协议描述 `create_task` / `list_tasks` / `complete_task`，不导入 `lifeos.tasks`、Repository 或 ORM 类型；服务尚未合入时 UI 也能导入和测试。
- **空标题**：UI 先 `strip()`，空标题不发请求、不写库，提示“任务标题不能为空”。
- **错误映射**（与 `docs/PHASE2_TASKS.md` 的异常基类一致）：`LookupError` → 任务不存在；`ValueError` → 使用服务给出的文案；`RuntimeError` → 任务保存失败。未知异常在读取时提示“任务加载失败”，界面不会崩溃。
- **服务即真源**：创建或完成成功后重新 `list_tasks()` 渲染，避免 UI 与持久化状态分叉；写入失败时同样重读，复选框回退到实际状态。
- **已完成不可回退**：已完成条目去掉 `ItemIsUserCheckable`，以勾选态、删除线和灰色文字呈现。重新打开任务不在本阶段范围。
- 列表顺序完全沿用服务返回顺序，UI 不自行排序。

## 启动与测试命令

```powershell
python -m alembic upgrade head
python -m lifeos                 # 入口注入服务后可见任务区
python -m pytest tests/test_ui.py tests/test_ui_tasks.py -q
python -m pytest                 # 全量
ruff check .
ruff format --check .
```

## 实际结果

| 项目 | 结果 |
| --- | --- |
| `pytest tests/test_ui.py tests/test_ui_tasks.py -q` | 22 passed（原有 5 项 UI 测试 + 新增 17 项） |
| `ruff check .` | 通过 |
| `ruff format --check .` | 通过（44 个文件已格式化） |
| 全量 `pytest` | **未执行**：当前机器无网络，可用的 PySide6 环境缺少 SQLAlchemy、Alembic、pydantic-settings，无法收集数据库和集成测试。待在联网环境或已安装依赖的 venv 中执行。 |
| 视觉检查 | 通过真实 Windows 平台渲染截图核对：待完成项复选框、已完成项删除线灰字、空标题红色提示均正常。 |

## 待协调与遗留

- **A**：入口需把任务服务注入 `MainWindow`（`task_service=`）；在此之前桌面版任务区为禁用状态。
- **A/B**：`Task.status` 目前按字符串 `pending` / `completed` 判断；若 A 改为字符串枚举，需要同步 `TaskPanel._build_item`（`str(status)` 归一化更稳妥），请确认后我再改。
- **A/B**：`Task.created_at` / `completed_at` 目前不在界面展示；如需“完成时间”提示，请确认展示格式。
- **C**：缺表或迁移未执行时的提示文案由服务层给出，UI 只透传 `RuntimeError` 的通用文案；若要区分“请先执行迁移”，需要服务层提供明确异常。
- 暗色主题对比度问题仍存在（Phase 1 遗留），本次沿用固定色值，未做主题适配。
- 日志重复初始化问题按用户要求暂缓。
