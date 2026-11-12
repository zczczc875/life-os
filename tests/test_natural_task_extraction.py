from datetime import date, time

import pytest

from lifeos.ai.local_provider import LocalDraftProvider
from lifeos.ai.provider import ExtractedTask


@pytest.fixture
def parser():
    return LocalDraftProvider(today=date(2026, 11, 11))


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("准备项目汇报", ExtractedTask("准备项目汇报")),
        ("核对报名截止日期", ExtractedTask("核对报名截止日期")),
        ("请家长签字", ExtractedTask("家长签字")),
        ("整理这周五的会议纪要", ExtractedTask("整理这周五的会议纪要")),
        ("整理明天后的会议纪要", ExtractedTask("整理明天后的会议纪要")),
        ("支付1,200元", ExtractedTask("支付1,200元")),
        ("交报告 DDL: 2026-12-18", ExtractedTask("交报告", date(2026, 12, 18))),
        (
            "提交报告 2026.12.18 18:00",
            ExtractedTask("提交报告", date(2026, 12, 18), time(18)),
        ),
        (
            "2026年12月18日17:30前提交实验报告",
            ExtractedTask("提交实验报告", date(2026, 12, 18), time(17, 30)),
        ),
        (
            "各位同学请在明天下午五点半前提交报告",
            ExtractedTask("提交报告", date(2026, 11, 12), time(17, 30)),
        ),
        (
            "明天下午5点20分前提交报告",
            ExtractedTask("提交报告", date(2026, 11, 12), time(17, 20)),
        ),
        ("交报告，明晚8点", ExtractedTask("交报告", date(2026, 11, 12), time(20))),
        (
            "请于12月20日晚8点前提交报告",
            ExtractedTask("提交报告", date(2026, 12, 20), time(20)),
        ),
        (
            "【周末安排】报名表提交：周五 17:30",
            ExtractedTask("提交报名表", date(2026, 11, 13), time(17, 30)),
        ),
        ("交报告截止到明天", ExtractedTask("交报告", date(2026, 11, 12))),
        ("提交报告（截止：明天）", ExtractedTask("提交报告", date(2026, 11, 12))),
        ("下周一交报告", ExtractedTask("交报告", date(2026, 11, 16))),
        ("12 月 22 日前上传附件", ExtractedTask("上传附件", date(2026, 12, 22))),
    ],
)
def test_quick_entry_cleans_the_title_and_extracts_only_an_identifiable_deadline(
    parser, entry, expected
):
    assert parser.parse_quick_task(entry) == expected


@pytest.mark.parametrize(
    ("entry", "feedback"),
    [
        ("交表 DDL: 2026-02-29", "截止时间无效"),
        ("明天上午17点交表", "截止时间无效"),
        ("下午5点前交表", "补充截止日期"),
        ("提交截止", "无法识别截止时间"),
        ("提交报告 明天下午5点后", "无法识别截止时间"),
        ("提交报告 明天下午5点左右", "无法识别截止时间"),
        ("提交报告 2026-12-18 17:30:45", "截止时间无效"),
        ("提交报告 2026-12-18 17:30 UTC", "截止时间无效"),
        ("提交报告 2026-12-18 17:30+08:00", "截止时间无效"),
        ("明天下午5点20提交报告", "截止时间无效"),
        ("交报告 DDL: 周五或下周一", "多个可能的截止时间"),
        ("请于12月20日至22日之间提交报告", "多个可能的截止时间"),
        ("请交实验报告，并填写问卷", "从通知导入"),
    ],
)
def test_quick_entry_reports_when_it_cannot_choose_a_single_deadline_or_task(
    parser, entry, feedback
):
    with pytest.raises(ValueError, match=feedback):
        parser.parse_quick_task(entry)


def test_notice_extracts_actions_across_lines_and_in_one_sentence(parser):
    result = parser.extract_tasks(
        "各位同学好，下面是本周安排。\n"
        "请提交报名表。\n"
        "截止时间为 2026 年 12 月 20 日下午 6 点。\n"
        "请在 12 月 22 日前上传附件；别忘了打印回执。\n"
        "不要在明天前提交其他附件。报名已结束。\n"
        "地点：教学楼101。谢谢配合！"
    )
    assert result.tasks == [
        ExtractedTask("提交报名表", date(2026, 12, 20), time(18)),
        ExtractedTask("上传附件", date(2026, 12, 22)),
        ExtractedTask("打印回执"),
    ]


def test_notice_applies_explicitly_shared_deadline_to_documents_in_scope(parser):
    result = parser.extract_tasks(
        "通知：以下材料请在周五17:30前提交：\n"
        "1. 实验报告\n"
        "2. 原始数据\n"
        "表格下载链接见群文件。\n"
        "另外，请复习第五章。"
    )
    assert result.tasks == [
        ExtractedTask("提交实验报告", date(2026, 11, 13), time(17, 30)),
        ExtractedTask("提交原始数据", date(2026, 11, 13), time(17, 30)),
        ExtractedTask("复习第五章"),
    ]


def test_notice_applies_shared_deadline_after_a_list(parser):
    assert parser.extract_tasks("提交报告；填写问卷。以上事项统一截止时间：周五18:00。").tasks == [
        ExtractedTask("提交报告", date(2026, 11, 13), time(18)),
        ExtractedTask("填写问卷", date(2026, 11, 13), time(18)),
    ]


def test_notice_ignores_a_bare_chat_timestamp_but_keeps_a_labeled_deadline(parser):
    assert parser.extract_tasks(
        "2026-11-11 10:28\n请提交实验报告。\n请填写问卷。\n2026-11-11 10:30\n截止时间：明天17:30。"
    ).tasks == [
        ExtractedTask("提交实验报告"),
        ExtractedTask("填写问卷"),
    ]
    assert parser.extract_tasks(
        "2026-11-11 10:28\n请提交实验报告。\n截止时间：明天17:30。"
    ).tasks == [
        ExtractedTask("提交实验报告", date(2026, 11, 12), time(17, 30)),
    ]
    assert parser.extract_tasks("2026-12-18 17:30，提交实验报告。").tasks == [
        ExtractedTask("提交实验报告", date(2026, 12, 18), time(17, 30)),
    ]


def test_notice_splits_three_joined_actions_and_keeps_leading_deadline(parser):
    result = parser.extract_tasks("请于明天下午五点前提交报告，并上传附件并填写表格。")
    assert result.tasks == [
        ExtractedTask("提交报告", date(2026, 11, 12), time(17)),
        ExtractedTask("上传附件", date(2026, 11, 12), time(17)),
        ExtractedTask("填写表格", date(2026, 11, 12), time(17)),
    ]


def test_notice_does_not_guess_ambiguous_deadline(parser):
    result = parser.extract_tasks(
        "提交实验报告。\n截止：明天或后天。\n周五或下周一提交登记表。提交链接：https://example.test"
    )
    assert result.tasks == [
        ExtractedTask("提交实验报告（截止:明天或后天）"),
        ExtractedTask("周五或下周一提交登记表"),
    ]


@pytest.mark.parametrize(
    "entry",
    [
        "提交报告 明天下午5点后",
        "2026-12-18 17:30:45前提交报告",
        "明天下午5点20提交报告",
    ],
)
def test_notice_keeps_original_text_when_deadline_needs_review(parser, entry):
    assert parser.extract_tasks(entry).tasks == [ExtractedTask(entry)]


def test_relative_date_crosses_year_boundary():
    parser = LocalDraftProvider(today=date(2026, 12, 31))
    assert parser.parse_quick_task("明天早上八点交表") == ExtractedTask(
        "交表", date(2027, 1, 1), time(8)
    )


def test_notice_without_action_has_no_drafts(parser):
    assert parser.extract_tasks("温馨提示：说明会周五举行。下周一 18:00。\n谢谢。").tasks == []
