"""
录音器抽象接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


from abc import ABC, abstractmethod


class BaseRecorder(ABC):
    """
    录音器抽象基类。
    """

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """
        当前是否正在录音。
        """
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        """
        开始录音。
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """
        停止录音。
        """
        raise NotImplementedError