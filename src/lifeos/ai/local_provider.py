"""Extract actionable tasks and their local deadlines from user-supplied text."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, time, timedelta
from typing import TYPE_CHECKING

from lifeos.ai.provider import ExtractedTask, LLMProvider, TaskExtractionResponse

if TYPE_CHECKING:
    from collections.abc import Iterator

_NUMBER = r"(?:[0-9]{1,2}|[〇零一二两三四五六七八九十]{1,3})"
_CLOCK = (
    rf"(?:(?P<period>凌晨|早上|上午|中午|下午|傍晚|晚上|晚间|夜里|早|晚)\s*)?"
    rf"(?P<hour>{_NUMBER})\s*(?::(?P<minute>[0-9]{{1,2}})(?![0-9])"
    rf"|[点时](?:\s*(?:(?P<half>半)|(?P<chinese_minute>{_NUMBER})\s*分))?)"
)
_DATE = (
    r"(?<![0-9])(?:"
    r"(?P<iso>[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2})(?![0-9])"
    rf"|(?:(?P<year>[0-9]{{4}})\s*年\s*)?(?P<month>{_NUMBER})\s*月\s*"
    rf"(?P<day>{_NUMBER})(?:\s*[日号]|(?![0-9]))"
    r"|(?P<relative>今天|今日|今早|今晚|明天|明日|明早|明晚|大后天|后天)"
    r"|(?P<week>下|本|这)?(?:周|星期|礼拜)(?P<weekday>[一二三四五六日天])"
    r")"
)
_DEADLINE = re.compile(rf"{_DATE}(?:[ \t]*(?:T(?=[0-9]))?{_CLOCK})?")
_CHAT_TIMESTAMP = re.compile(
    r"^[ \t]*[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2}[ T][0-9]{1,2}:[0-9]{2}"
    r"(?::[0-9]{2})?[ \t]*\r?$",
    re.MULTILINE,
)
_CLOCK_ONLY = re.compile(_CLOCK)
_ENGLISH_TAG = r"(?<![A-Za-z0-9_])(?:DDL|deadline|due(?:\s+on)?)(?![A-Za-z0-9_])"
_TAG = rf"(?:{_ENGLISH_TAG}|截止(?:日期|时间)?|最晚|最迟|截至)"
_TAG_END = re.compile(rf"{_TAG}\s*(?:为|是|到|至|定在)?\s*[:：]?\s*$", re.IGNORECASE)
_EXPLICIT_TAG = re.compile(
    rf"{_ENGLISH_TAG}|{_TAG}\s*(?:[:：]|(?:为|是|到|至|定在)\s*|待定|\d)", re.IGNORECASE
)
_TAG_START = re.compile(rf"^(?:{_TAG})", re.IGNORECASE)
_AT_END = re.compile(r"(?:请\s*)?[在于]\s*$")
_BEFORE_START = re.compile(r"^\s*(?:之前|以前|前)(?![的些])")
_AFTER_START = re.compile(r"^\s*(?:之后|以后|左右|后)(?![的些])")
_FOLLOWING_TAG = re.compile(r"^\s*(?:截止|到期)\s*(?:[:：]\s*|(?=$))")
_RANGE = r"(?:或(?:者)?|还是|与|到|至|[-~～–])"
_RANGE_BETWEEN = re.compile(rf"^\s*(?:[,，]\s*)?{_RANGE}\s*$")
_SHORT_RANGE = re.compile(rf"^\s*{_RANGE}\s*{_NUMBER}\s*[日号]")
_UNSUPPORTED_CLOCK_SUFFIX = re.compile(r"^(?::[0-9]|[秒刻]|[+\-][0-9]|Z\b|UTC\b|GMT\b)")
_UNCLEAR_DAY = re.compile(r"(?:本月底|月底|月末|年底|下月初|下个月|这几天|近日|下周)\s*(?:之前|前)")
_DEADLINE_WITHOUT_DATE = re.compile(
    r"^(?:(?:提交|报名|交表|缴费)\s*)?(?:截止|最晚|最迟|截至)(?:日期|时间)?$"
)
_UNCERTAIN_PREFIX = re.compile(rf"^(?:(?:之前|以前|前|之后|以后|左右|后|{_RANGE})\s*)+")
_NUMBERED_BULLET = r"\(?[0-9一二三四五六七八九十]+(?:[)、）]|\.(?![0-9]))"
_BULLET = re.compile(rf"^\s*(?:[-*•·]\s*|{_NUMBERED_BULLET}\s*)")
_JOINED_ACTION = r"(?:提交|交|填写|完成|缴费|上传|报名|发|打印|准备|于|在|请)"
_JOINER = rf"(?:并且|以及|同时|并(?=\s*{_JOINED_ACTION}))"
_PARTS = re.compile(
    rf"\r?\n|[。！？；;!?]|\.(?=\s|$)(?<![0-9]\.)"
    rf"|(?:[，]|(?<![0-9]),|,(?![0-9]))(?!\s*(?:或(?:者)?|还是|{_JOINER}))"
    rf"|\s+(?={_NUMBERED_BULLET})"
)
_NOTICE_PREFIX = re.compile(r"^\s*(?:通知(?:如下)?|公告|温馨提示)\s*[:：]\s*")
_BRACKETED_HEADING = re.compile(r"^\s*【[^】\r\n]{1,40}】\s*(?=\S)")
_CLEAN_PREFIX = re.compile(
    r"^(?:(?:各位(?:同学|组员|成员)?|大家|全体(?:同学|成员)|"
    r"请(?:大家|各位(?:同学|组员|成员)?|同学们|全体(?:同学|成员)?)?|"
    r"务必|记得|别忘了|需要|还需|须|麻烦(?:大家)?|然后|另外|另请|接着|同时|并且|并|以及)\s*)+"
)
_NEGATIVE = re.compile(r"^(?:不要|无需|不用|禁止|不得|勿|免于|不必|暂停)")
_DISPOSAL_ACTION = re.compile(
    r"^(?:把|将)(.+?)(提交|上交|补交|发(?:送)?|上传|打印|交|填写|填|带上|完成|带|修改|更新)(.*)$"
)
_ACTOR_ACTION = re.compile(r"^(?:家长|负责人|老师|组长|班委)(?:签字|签名|确认|审核|提交|填写)")
_ACTION = re.compile(
    r"^(?:提交|上交|交付|交给|交|补交|递交|填报|填写|填|报名(?!表|费|材料|资格|信息)|登记|注册|预约|"
    r"完成|做|写|撰写|整理|制作|修改|确认|复核|审核|校对|核对|复习|阅读|"
    r"准备|上传|下载|发送|转发|发给|发|回复|答复|反馈|打印|复印|扫描|签字|"
    r"签名|签到|签收|领取|收集|取|参加|出席|开会|开组会|集合|到场|联系|"
    r"通知|报送|缴纳|缴费|支付|付款|购买|买|预订|带上|带|携带|检查|更新|"
    r"返还|归还|归档|办理|处理|安装|测试|部署|备份|复测|"
    r"(?:submit|upload|send|complete|finish|pay|buy|bring|call|register|review|print)\b)",
    re.IGNORECASE,
)
_METADATA = re.compile(
    r"^(?:通知(?:如下|正文|[:：])|公告|温馨提示|提醒事项|联系方式|"
    r"(?:报名|提交|下载|缴费|通知|注册|参加|上传|发放|反馈|付款|签到|领取)"
    r"(?:链接|方式|说明|入口|要求|流程|须知|通知|时间|地址|对象|地点|已结束|已截止|已完成)|"
    r"时间[:：]|地点[:：]|链接[:：]|https?://)"
)
_END_ACTION = re.compile(r"^(.{2,30}?)(补交|提交|上交|上传|报送|回复|填写|完成)$")
_SHARED_BEFORE = re.compile(r"以下|下列|如下")
_SHARED_AFTER = re.compile(r"以上|上述|统一|一律|均(?:需|在|于|为)|全部|都(?:要|在|需)")
_SECTION_TITLE = re.compile(
    r"^(?:完成|办理|处理|提交|上传|准备|携带|填写|上交|安排)?"
    r"(?:(?:以下|下列|上述|以上)(?:[一二两三四五六七八九十0-9]+(?:项|件|条)?)?"
    r"(?:事项|事|任务|材料|资料|文件|内容|工作|要求)?(?:如下|统一|全部|一律)?"
    r"|如下|统一|全部|一律)$"
)
_SECTION_VERB = re.compile(r"^(提交|上传|准备|携带|填写|上交)(?:以下|下列)")
_NEW_SECTION = re.compile(r"^\s*(?:另外|另请|另有|其他事项|补充通知)")
_CONJUNCTION = re.compile(rf"(?:[，,]\s*)?{_JOINER}\s*")
_DIGITS = "〇一二三四五六七八九"
_RELATIVE_DAYS = {
    "今天": 0,
    "今日": 0,
    "今早": 0,
    "今晚": 0,
    "明天": 1,
    "明日": 1,
    "明早": 1,
    "明晚": 1,
    "后天": 2,
    "大后天": 3,
}
_TRIM = " \t\n，,。.!！?？:：;；、-—"
_WIDTH = str.maketrans("０１２３４５６７８９：－　", "0123456789:- ")
_INVALID = "截止时间无效，请检查日期和时刻。"
_AMBIGUOUS = "有多个可能的截止时间，请只保留一个。"
_NO_DATE = "请补充截止日期，例如「明天下午5点」。"
_UNCLEAR = "无法识别截止时间，请写明日期，例如「明天」或「2026-12-18 17:30」。"


@dataclass(frozen=True)
class _Phrase:
    title: str
    due_on: date | None = None
    due_time: time | None = None
    issue: str = ""
    original: str = ""

    def draft(self) -> ExtractedTask:
        return ExtractedTask(
            self.original if self.issue else self.title, self.due_on, self.due_time
        )


def _number(value: str) -> int:
    if value.isascii():
        return int(value)
    value = value.replace("零", "〇").replace("两", "二")
    if "十" in value:
        tens, units = value.split("十")
        return (_DIGITS.index(tens) if tens else 1) * 10 + (_DIGITS.index(units) if units else 0)
    return int("".join(str(_DIGITS.index(digit)) for digit in value))


def _day_from(match: re.Match[str], today: date) -> date:
    if match["iso"]:
        year, month, day = map(int, re.split(r"[-/.]", match["iso"]))
        return date(year, month, day)
    if match["month"]:
        return date(
            int(match["year"] or today.year), _number(match["month"]), _number(match["day"])
        )
    if match["relative"]:
        return today + timedelta(days=_RELATIVE_DAYS[match["relative"]])
    weekday = "一二三四五六日".index(match["weekday"].replace("天", "日"))
    if match["week"] is None:
        return today + timedelta(days=(weekday - today.weekday()) % 7)
    week_start = today - timedelta(days=today.weekday())
    return week_start + timedelta(days=weekday + (7 if match["week"] == "下" else 0))


def _time_from(match: re.Match[str]) -> time | None:
    if match["hour"] is None:
        return None
    hour = _number(match["hour"])
    minute = 30 if match["half"] else _number(match["minute"] or match["chinese_minute"] or "0")
    period = match["period"]
    if not period and "relative" in match.re.groupindex:
        relative = match["relative"] or ""
        period = "晚上" if relative.endswith("晚") else "上午" if relative.endswith("早") else ""
    if period in {"凌晨", "早上", "早", "上午"} and hour > 12:
        raise ValueError("Inconsistent clock period")
    is_pm = period in {"下午", "傍晚", "晚上", "晚间", "晚", "夜里"}
    if (is_pm and 1 <= hour < 12) or (period == "中午" and 1 <= hour <= 2):
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0
    return time(hour, minute)


def _clean_title(text: str) -> str:
    text = text.strip(_TRIM)
    text = re.sub(r"(?<=[(（])\s*(?=[)）])", "", text).replace("()", "").replace("（）", "")
    text = re.sub(r"\s+", " ", _BULLET.sub("", text)).strip(_TRIM)
    text = _CLEAN_PREFIX.sub("", text).strip(_TRIM)
    if disposal := _DISPOSAL_ACTION.fullmatch(text):
        text = disposal[2] + disposal[1].strip() + disposal[3]
    elif not _ACTION.match(text) and (end_action := _END_ACTION.fullmatch(text)):
        text = end_action[2] + end_action[1].strip()
    return text


def _is_action(title: str) -> bool:
    return (
        bool(_ACTION.match(title) or _ACTOR_ACTION.match(title))
        and not _METADATA.match(title)
        and not _SECTION_TITLE.fullmatch(title)
    )


def _has_explicit_time(text: str) -> bool:
    return any(
        not text[: clock.start()].strip(_TRIM)
        or not text[clock.end() :].strip(_TRIM)
        or _BEFORE_START.match(text[clock.end() :])
        or _AT_END.search(text[: clock.start()])
        for clock in _CLOCK_ONLY.finditer(text)
    )


def _phrase(text: str, today: date, *, quick: bool = False) -> _Phrase:
    text = _BRACKETED_HEADING.sub("", _NOTICE_PREFIX.sub("", _BULLET.sub("", text.strip())))
    original_title = _clean_title(text)
    if _NEGATIVE.match(original_title):
        return _Phrase(original_title)
    if _DEADLINE_WITHOUT_DATE.fullmatch(original_title):
        return _Phrase("", issue=_UNCLEAR, original=original_title)

    spans: list[tuple[int, int]] = []
    deadlines: set[tuple[date, time | None]] = set()
    issue = ""
    for match in _DEADLINE.finditer(text):
        before, after = text[: match.start()], text[match.end() :]
        tag = _TAG_END.search(before)
        if (
            tag
            and tag.start()
            and not _EXPLICIT_TAG.search(tag[0])
            and tag[0].strip() in {"截止日期", "截止时间"}
            and before[tag.start() - 1] not in _TRIM
        ):
            tag = None
        at = _AT_END.search(before)
        before_limit = _BEFORE_START.match(after)
        following_tag = _FOLLOWING_TAG.match(after)
        leading = not _clean_title(before)
        trailing = not after.strip(_TRIM)
        alternative = bool(spans and _RANGE_BETWEEN.fullmatch(text[spans[-1][1] : match.start()]))
        prefix_has_range = bool(
            not tag and _DEADLINE.search(before) and re.search(rf"{_RANGE}\s*$", before)
        )
        if not (
            tag
            or at
            or before_limit
            or following_tag
            or leading
            or alternative
            or trailing
            and (quick or _is_action(_clean_title(before)))
        ):
            continue

        if _UNSUPPORTED_CLOCK_SUFFIX.match(after):
            issue = _INVALID
        elif alternative or prefix_has_range or _SHORT_RANGE.match(after):
            issue = _AMBIGUOUS
        elif _AFTER_START.match(after):
            issue = _UNCLEAR
        try:
            deadlines.add((_day_from(match, today), _time_from(match)))
        except (ValueError, OverflowError):
            issue = _INVALID
        prefix = tag or at
        suffix = before_limit or following_tag
        spans.append(
            (
                prefix.start() if prefix else match.start(),
                match.end() + (suffix.end() if suffix else 0),
            )
        )

    title_parts: list[str] = []
    offset = 0
    for start, end in spans:
        title_parts.append(text[offset:start])
        offset = end
    title_parts.append(text[offset:])
    title = _clean_title(" ".join(title_parts))
    if len(deadlines) > 1:
        issue = _AMBIGUOUS
    if _EXPLICIT_TAG.search(title) or _UNCLEAR_DAY.search(title):
        issue = issue or _UNCLEAR
    if not spans and _has_explicit_time(text):
        issue = _NO_DATE
    if issue:
        if clock := _CLOCK_ONLY.match(title):
            title = title[clock.end() :].strip(_TRIM)
        title = _clean_title(_UNCERTAIN_PREFIX.sub("", title))
        return _Phrase(title, issue=issue, original=original_title)
    if deadlines:
        due_on, due_time = next(iter(deadlines))
        return _Phrase(title, due_on, due_time)
    return _Phrase(title)


def _notice_parts(text: str, today: date) -> Iterator[tuple[str, _Phrase]]:
    for segment in _PARTS.split(text):
        if not segment.strip():
            continue
        inherited: _Phrase | None = None
        while True:
            for connector in _CONJUNCTION.finditer(segment):
                first, rest = segment[: connector.start()], segment[connector.end() :]
                left = _phrase(first, today)
                if not (_is_action(left.title) and _is_action(_phrase(rest, today).title)):
                    continue
                if left.due_on is not None and not left.issue:
                    leading = _DEADLINE.search(first)
                    # A limit before the first verb can apply to the joined instructions.
                    if leading and _BEFORE_START.match(first[leading.end() :]):
                        inherited = left
                elif not left.issue and inherited is not None:
                    left = replace(left, due_on=inherited.due_on, due_time=inherited.due_time)
                yield first, left
                segment = rest
                break
            else:
                phrase = _phrase(segment, today)
                if not phrase.issue and phrase.due_on is None and inherited is not None:
                    phrase = replace(phrase, due_on=inherited.due_on, due_time=inherited.due_time)
                yield segment, phrase
                break


class LocalDraftProvider(LLMProvider):
    """Recognize common notice phrasing without a network or a model."""

    def __init__(self, *, today: date | None = None) -> None:
        self._today = today

    def parse_quick_task(self, text: str) -> ExtractedTask:
        """Parse one quick entry, retaining plain titles when there is no deadline."""
        today = self._today or date.today()
        text = text.translate(_WIDTH).strip()
        candidates = sum(_is_action(phrase.title) for _, phrase in _notice_parts(text, today))
        if candidates > 1:
            raise ValueError("一次添加一项任务。多项任务请使用「从通知导入」。")
        phrase = _phrase(text, today, quick=True)
        if phrase.issue:
            raise ValueError(phrase.issue)
        if not phrase.title:
            raise ValueError("任务标题不能为空")
        return phrase.draft()

    def extract_tasks(self, message: str) -> TaskExtractionResponse:
        today = self._today or date.today()
        drafts: list[ExtractedTask] = []
        waiting: list[int] = []
        pending: _Phrase | None = None
        shared: _Phrase | None = None
        section_verb = ""
        section_list = False
        section_bullets = False
        # A standalone numeric timestamp can be copied chat metadata.
        text = _CHAT_TIMESTAMP.sub("", message.translate(_WIDTH))
        for raw, phrase in _notice_parts(text, today):
            bullet = bool(_BULLET.match(raw))
            if _NEW_SECTION.match(raw) or (
                section_bullets and not bullet and _is_action(phrase.title)
            ):
                shared = None
                waiting.clear()
                section_verb = ""
                section_list = section_bullets = False
            if section_list and bullet:
                section_bullets = True
            shared_before = bool(_SHARED_BEFORE.search(raw))
            shared_after = bool(_SHARED_AFTER.search(raw))
            is_header = bool(_SECTION_TITLE.fullmatch(phrase.title))
            is_deadline = not phrase.title or bool(
                phrase.issue and (_TAG_START.match(phrase.original) or shared_after)
            )
            if is_header or is_deadline:
                if is_header and shared_before:
                    shared = phrase if phrase.due_on else None
                    pending = None
                    waiting.clear()
                    section_list = True
                    section_bullets = False
                    verb = _SECTION_VERB.match(phrase.title)
                    section_verb = verb[1] if verb else ""
                elif len(waiting) == 1 or (waiting and (shared_after or section_list)):
                    for index in waiting:
                        draft = drafts[index]
                        if phrase.due_on is not None:
                            drafts[index] = replace(
                                draft, due_on=phrase.due_on, due_time=phrase.due_time
                            )
                        elif phrase.issue:
                            drafts[index] = replace(
                                draft, title=f"{draft.title}（{phrase.original}）"
                            )
                    waiting.clear()
                elif not waiting and phrase.due_on is not None:
                    if shared_after:
                        shared = phrase
                    else:
                        pending = phrase
                continue

            if _METADATA.match(phrase.title):
                pending = None
                continue
            if not _is_action(phrase.title):
                if not (section_verb and bullet and not phrase.issue):
                    continue
                phrase = replace(phrase, title=section_verb + phrase.title)

            if not phrase.issue and phrase.due_on is None and (deadline := pending or shared):
                phrase = replace(phrase, due_on=deadline.due_on, due_time=deadline.due_time)
            pending = None
            if phrase.due_on is None and not phrase.issue:
                waiting.append(len(drafts))
            else:
                waiting.clear()
            drafts.append(phrase.draft())
        return TaskExtractionResponse(tasks=drafts)
