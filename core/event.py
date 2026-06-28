"""
事件总线。

所有业务模块之间只能通过 EventBus 通信。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from core.events import Events


@dataclass(slots=True)
class Event:
    """
    事件对象。

    Attributes
    ----------
    type:
        事件类型。
    data:
        事件数据。
    """

    type: Events
    data: Any = None


EventHandler = Callable[[Event], None]


class EventBus:
    """
    发布 / 订阅事件总线。

    提供三个公开接口：

    - subscribe()
    - unsubscribe()
    - emit()
    """

    def __init__(self) -> None:
        self._subscribers: dict[Events, list[EventHandler]] = defaultdict(list)

    def subscribe(
        self,
        event_type: Events,
        handler: EventHandler,
    ) -> None:
        """
        订阅事件。
        """
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: Events,
        handler: EventHandler,
    ) -> None:
        """
        取消订阅。
        """
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    def emit(self, event: Event) -> None:
        """
        发布事件。
        """
        for handler in self._subscribers[event.type]:
            handler(event)