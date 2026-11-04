# Phase 2：AI 数据边界检查与草稿确认接口建议

负责人：D。分支：`feat/phase2-ai-boundary`。范围：检查现有 AI Mock 与数据边界，提出「用户确认任务草稿」的接口建议；本阶段**不接真实模型 API**。

## 1. 现状检查

### 1.1 Provider 与 Mock

- `lifeos.ai.provider` 只定义契约：`LLMProvider.extract_tasks(message: str) -> TaskExtractionResponse`、`ExtractedTask(title: str)`、`ProviderError`。
- `lifeos.ai.mock_provider.MockLLMProvider` 是纯函数式实现：按行拆分、去掉列表序号/项目符号、空白输入返回空列表，行为确定、可重复调用。
- 两者都不读取配置、不打开数据库、不写日志、不联网。`ExtractedTask` 只是**待确认的草稿标题**，不是已持久化的任务。

### 1.2 数据边界

- `lifeos.ai` 不依赖 `lifeos.infrastructure.database`、`lifeos.tasks`、`lifeos.ui`；该边界由 `tests/test_ai_boundary.py` 的 AST 检查固定。
- Provider 只返回结果，不创建、不持久化任务；任务持久化由 A 的 `TaskService` 和 C 的 Repository 负责。

### 1.3 配置与隐私

- `Settings` 没有 `key` / `secret` / `token` / `password` 类字段，本阶段不写入真实凭据。
- Mock 不记录消息正文；日志初始化也不输出正文。二者均由 `tests/test_ai_boundary.py` 验证。

### 1.4 已知遗留（不在本次处理）

- 同一进程切换数据目录后重新初始化日志，旧处理器仍可能写入旧目录（见 `docs/DELIVERY_PHASE1.md`）。按用户要求暂缓。
- 真实 AI 接入前的发送范围、用户确认与密钥管理，按 `docs/SECURITY.md` 另行设计，本阶段不做。

## 2. 草稿确认流程建议

### 2.1 目标流程

```text
用户输入自由文本
      │
      ▼
Provider.extract_tasks(message)      ← D：只产出草稿，不持久化
      │  TaskExtractionResponse(tasks=[ExtractedTask...])
      ▼
草稿列表（展示、可编辑/勾选）         ← B
      │  用户确认
      ▼
TaskService.create_task(title)       ← A：持久化为 pending 任务
      │
      ▼
任务列表 / 完成状态                  ← B（数据来自 A 的服务）
```

### 2.2 职责边界

| 环节 | 负责人 | 约束 |
| --- | --- | --- |
| 生成草稿 | D | 只返回 `ExtractedTask` 列表；不写库、不写日志正文、不联网 |
| 展示与确认 | B | 只依赖 Provider 返回和任务服务；不直接执行 SQL、不导入 Repository |
| 持久化 | A / C | 只在用户确认后调用 `create_task`；空标题不写库 |

### 2.3 建议的接口细节

- **草稿语义**：`ExtractedTask.title` 是草稿标题；确认前不分配 `id`、不写 `created_at`。
- **规范化**：进入 `create_task` 前统一 `title.strip()`；规范化后为空的草稿应被跳过（不写库、不报错）。
- **去重（可选）**：同一批草稿内按标题大小写不敏感去重，避免一次确认产生重复任务；是否采用由 A 决定。
- **幂等**：重复确认同一条草稿不应重复建任务；建议 UI 在确认成功后移除该草稿，服务层不额外去重。
- **错误**：`create_task` 抛 `TaskValidationError`（空标题）或 `TaskStorageError`（持久化失败）时，UI 提示并保留草稿供重试。

### 2.4 建议的最小接口（由 A 决定是否落地到 `lifeos.tasks`）

```python
# 供 B 使用；是否新增类型由 A 决定
@dataclass(frozen=True)
class TaskDraft:
    title: str

    @property
    def confirmable(self) -> bool:
        return bool(self.title.strip())


def drafts_from(response: TaskExtractionResponse) -> list[TaskDraft]:
    """把 Provider 结果转成待确认草稿；不持久化。"""
```

说明：`TaskDraft` 只是对 `ExtractedTask` 的语义包装（草稿 vs 已持久化任务）；若 A 不新增类型，直接复用 `ExtractedTask` 并约定「草稿」语义同样成立。

### 2.5 待 A / B / C 确认的问题

1. **空标题草稿**：UI 静默跳过，还是提示「已跳过 N 条空草稿」？建议后者，便于用户理解。
2. **批内去重**：是否需要？由 A 决定。
3. **溯源**：是否为草稿保留原始消息 id？Phase 2 不持久化，建议以后再加。
4. **真实接入**：按 `docs/SECURITY.md`，接入云端 AI 前须明确发送范围、用户确认和密钥管理；本阶段不接。

## 3. 检查项与验证

以下检查均已实现为 `tests/test_ai_boundary.py` 中的测试：

| 检查项 | 测试 |
| --- | --- |
| `lifeos.ai` 不依赖 database / tasks / ui | `test_ai_package_does_not_import_database_tasks_or_ui` |
| Mock 只产出草稿对象 | `test_mock_provider_returns_draft_objects` |
| 调用 Provider 无文件系统副作用 | `test_extract_tasks_has_no_filesystem_side_effect` |
| 不把消息正文写入日志 | `test_extract_tasks_does_not_log_message_content` |
| `Settings` 无密钥类字段 | `test_settings_have_no_secret_fields` |

### 测试结果

在 `feat/phase2-ai-boundary` 分支运行（Windows / Python 3.12.10，`.venv`）：

```text
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
```

结果：全量 `pytest` 通过，`ruff check .` 与 `ruff format --check .` 通过。具体数字见 PR 描述与提交信息。
