"""Produce editable task drafts locally from pasted notices."""

from __future__ import annotations

import re
from datetime import date

from lifeos.ai.mock_provider import MockLLMProvider
from lifeos.ai.provider import ExtractedTask, LLMProvider, TaskExtractionResponse

_ISO_DAY = r"(?P<day>[0-9]{4}-[0-9]{2}-[0-9]{2})"
_TAGGED = re.compile(
    rf"(?:(?<![A-Za-z0-9_])DDL|截止(?:日期)?)\s*[:：]?\s*{_ISO_DAY}(?![0-9])",
    re.IGNORECASE,
)
_BEFORE = re.compile(rf"请[在于]\s*{_ISO_DAY}\s*前")


def _extract_deadline(draft: ExtractedTask) -> ExtractedTask:
    title = draft.title
    matches = [*_TAGGED.finditer(title), *_BEFORE.finditer(title)]
    if len(matches) != 1:
        return draft
    match = matches[0]
    if match.re is _TAGGED:
        if title[match.end() :].strip(" \t。.!！"):
            return draft
        title = title[: match.start()].rstrip(" \t:：,，;；")
        if not title:
            return draft
    try:
        deadline = date.fromisoformat(match["day"])
    except ValueError:
        return draft
    return ExtractedTask(title=title, due_on=deadline)


class LocalDraftProvider(LLMProvider):
    """Split nonempty lines into candidates and suggest explicit ISO deadlines."""

    def extract_tasks(self, message: str) -> TaskExtractionResponse:
        lines = MockLLMProvider().extract_tasks(message).tasks
        return TaskExtractionResponse(tasks=[_extract_deadline(draft) for draft in lines])
