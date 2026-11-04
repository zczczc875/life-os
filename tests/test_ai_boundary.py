"""Phase 2 AI 数据边界检查。

把「D 的 AI 模块不依赖数据库/任务服务/UI，不落盘，也不记录消息正文」变成可执行的约束，
而不是只写在文档里。测试只读取源码和内存对象，使用临时目录，不触碰正式数据。
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from lifeos.ai.mock_provider import MockLLMProvider
from lifeos.ai.provider import ExtractedTask, TaskExtractionResponse
from lifeos.config.settings import Settings

_AI_DIR = Path(__file__).resolve().parents[1] / "src" / "lifeos" / "ai"
_FORBIDDEN_PREFIXES = (
    "lifeos.infrastructure.database",
    "lifeos.tasks",
    "lifeos.ui",
)


def _imported_modules(path: Path) -> set[str]:
    """返回模块源码里 import 到的模块名（含 ``from ... import``）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_ai_package_does_not_import_database_tasks_or_ui():
    """数据边界：ai 包只依赖标准库与自身，不碰数据库、任务服务或 UI。"""
    for path in sorted(_AI_DIR.glob("*.py")):
        for module in _imported_modules(path):
            for prefix in _FORBIDDEN_PREFIXES:
                assert not module.startswith(prefix), f"{path.name} imports {module}"


def test_mock_provider_returns_draft_objects():
    """Mock 只产出草稿对象（ExtractedTask），不是已持久化的任务。"""
    response = MockLLMProvider().extract_tasks("Buy milk\nCall mom")
    assert isinstance(response, TaskExtractionResponse)
    assert all(isinstance(task, ExtractedTask) for task in response.tasks)
    assert [task.title for task in response.tasks] == ["Buy milk", "Call mom"]


def test_extract_tasks_has_no_filesystem_side_effect(tmp_path, monkeypatch):
    """调用 Provider 不创建任何文件或目录。"""
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.iterdir())

    MockLLMProvider().extract_tasks("Buy milk\nCall mom")

    assert sorted(tmp_path.iterdir()) == before


def test_extract_tasks_does_not_log_message_content(caplog):
    """提取过程不得把消息正文写进日志。"""
    message = "confidential-message-body"
    with caplog.at_level(logging.DEBUG):
        MockLLMProvider().extract_tasks(message)
    assert all(message not in record.getMessage() for record in caplog.records)


def test_settings_have_no_secret_fields():
    """配置里不应出现密钥类字段：Phase 2 不保存真实 API 凭据。"""
    suspicious = [
        name
        for name in Settings.model_fields
        if any(token in name.lower() for token in ("key", "secret", "token", "password"))
    ]
    assert suspicious == []
