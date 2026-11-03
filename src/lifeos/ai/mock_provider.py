"""确定性 Mock provider；不调用真实模型。"""

from __future__ import annotations

import re

from lifeos.ai.provider import (
    ExtractedTask,
    LLMProvider,
    TaskExtractionResponse,
)

_LINE_SPLIT = re.compile(r"[\r\n]+")
_LIST_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+\s*[.)、])\s*")


def _clean_title(line: str) -> str:
    return _LIST_PREFIX.sub("", line).strip()


class MockLLMProvider(LLMProvider):
    """把消息按行拆成任务，行为确定、可重复调用。

    - 空白输入 -> 空任务列表
    - 非空输入 -> 每个非空行一条任务，去掉常见的列表序号/项目符号
    """

    def extract_tasks(self, message: str) -> TaskExtractionResponse:
        text = (message or "").strip()
        if not text:
            return TaskExtractionResponse(tasks=[])

        titles = [_clean_title(line) for line in _LINE_SPLIT.split(text)]
        return TaskExtractionResponse(tasks=[ExtractedTask(title=t) for t in titles if t])
