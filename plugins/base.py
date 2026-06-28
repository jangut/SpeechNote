"""
插件抽象接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.event import EventBus
from core.sentence import Sentence
from core.events import Events


class BasePlugin(ABC):
    """
    插件抽象基类。
    """

    @abstractmethod
    def register(self, event_bus: EventBus) -> None:
        """
        注册事件。
        """
        event_bus.subscribe(
            Events.SENTENCE,
            self._on_sentence,
        )

        event_bus.subscribe(
            Events.ERROR,
            self._on_error,
        )
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        """
        启动插件。
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """
        停止插件。
        """
        raise NotImplementedError
