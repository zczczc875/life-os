"""Date entry shared by the task form and notification drafts."""

from datetime import date

DUE_DATE_PLACEHOLDER = "YYYY-MM-DD（可留空）"


def parse_optional_due_date(text: str) -> date | None:
    """Accept a blank field or a calendar date in YYYY-MM-DD format."""
    text = text.strip()
    if not text:
        return None
    try:
        due_on = date.fromisoformat(text)
        if due_on.isoformat() == text:
            return due_on
    except ValueError:
        pass
    raise ValueError("截止日期请输入有效的 YYYY-MM-DD，或留空。")
