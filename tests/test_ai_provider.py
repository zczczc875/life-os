"""AI provider 契约与 Mock 实现测试。"""

from __future__ import annotations

import pytest

from lifeos.ai.mock_provider import MockLLMProvider
from lifeos.ai.provider import (
    ExtractedTask,
    LLMProvider,
    ProviderError,
    TaskExtractionResponse,
)


@pytest.fixture
def provider() -> MockLLMProvider:
    return MockLLMProvider()


def test_blank_message_returns_no_tasks(provider):
    assert provider.extract_tasks("") == TaskExtractionResponse(tasks=[])
    assert provider.extract_tasks("   \n  \n ") == TaskExtractionResponse(tasks=[])


def test_single_line_returns_one_task(provider):
    response = provider.extract_tasks("Buy milk")
    assert response.tasks == [ExtractedTask(title="Buy milk")]


def test_multiple_lines_return_tasks_in_order(provider):
    response = provider.extract_tasks("Buy milk\nCall mom\nPay rent")
    assert [task.title for task in response.tasks] == ["Buy milk", "Call mom", "Pay rent"]


def test_list_markers_are_stripped(provider):
    response = provider.extract_tasks("1. Buy milk\n- Call mom\n* Pay rent")
    assert [task.title for task in response.tasks] == ["Buy milk", "Call mom", "Pay rent"]


def test_mock_is_deterministic(provider):
    message = "A\nB\nC"
    assert provider.extract_tasks(message) == provider.extract_tasks(message)


def test_failing_provider_raises_provider_error():
    class FailingProvider(LLMProvider):
        def extract_tasks(self, message: str) -> TaskExtractionResponse:
            raise ProviderError("boom")

    with pytest.raises(ProviderError, match="boom"):
        FailingProvider().extract_tasks("anything")
