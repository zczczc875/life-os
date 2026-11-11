"""LLM provider 抽象与响应数据结构。

本阶段不调用真实模型 API；这里只定义契约与数据模型。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, time


class ProviderError(RuntimeError):
    """Provider 处理失败时抛出，由调用方负责捕获。"""


@dataclass(frozen=True)
class ExtractedTask:
    """从消息中提取出的一条任务。"""

    title: str
    due_on: date | None = None
    due_time: time | None = None


@dataclass(frozen=True)
class TaskExtractionResponse:
    """结构化提取结果。"""

    tasks: list[ExtractedTask] = field(default_factory=list)


class LLMProvider(ABC):
    """任务提取的统一接口。"""

    @abstractmethod
    def extract_tasks(self, message: str) -> TaskExtractionResponse:
        """从 ``message`` 提取任务列表。

        空或空白输入返回空列表；处理失败抛出 :class:`ProviderError`。
        """
