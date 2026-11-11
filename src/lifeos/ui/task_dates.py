"""Canonical deadline display and entry for task forms."""

from datetime import date, time

DUE_DATE_PLACEHOLDER = "YYYY-MM-DD 或 YYYY-MM-DD HH:mm（可留空）"


def format_deadline(due_on: date | None, due_time: time | None = None) -> str:
    """Display the local deadline to minute precision when it has a time."""
    if due_on is None:
        return ""
    if due_time is None:
        return due_on.isoformat()
    return f"{due_on.isoformat()} {due_time.isoformat(timespec='minutes')}"


def parse_optional_deadline(text: str) -> tuple[date | None, time | None]:
    """Read a blank, date-only, or minute-precision local deadline."""
    text = text.strip()
    if not text:
        return None, None
    date_text, separator, time_text = text.partition(" ")
    try:
        due_on = date.fromisoformat(date_text)
        due_time = time.fromisoformat(time_text) if separator else None
        if (due_time is None or due_time.tzinfo is None) and format_deadline(
            due_on, due_time
        ) == text:
            return due_on, due_time
    except ValueError:
        pass
    raise ValueError("截止时间请输入有效的 YYYY-MM-DD 或 YYYY-MM-DD HH:mm，或留空。")
