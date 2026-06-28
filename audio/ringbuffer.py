"""
线程安全环形缓冲区。

当前版本内部基于 queue.Queue 实现，
对外统一提供 RingBuffer 接口。

后续可无缝替换为真正的 Circular Buffer，
无需修改业务代码。
"""

from __future__ import annotations

from queue import Empty, Queue
from typing import Generic, TypeVar

T = TypeVar("T")


class RingBuffer(Generic[T]):
    """
    线程安全缓冲区。

    Parameters
    ----------
    maxsize
        最大缓存数量。
        0 表示无限容量。
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: Queue[T] = Queue(maxsize=maxsize)

    def push(self, item: T) -> None:
        """
        放入一个元素。

        Parameters
        ----------
        item
            待放入的数据。
        """
        self._queue.put(item)

    def pop(
        self,
        block: bool = True,
        timeout: float | None = None,
    ) -> T:
        """
        取出一个元素。

        Parameters
        ----------
        block
            是否阻塞等待。

        timeout
            超时时间（秒）。

        Returns
        -------
        T
            取出的元素。

        Raises
        ------
        queue.Empty
            当 block=False 或等待超时时抛出。
        """
        return self._queue.get(block=block, timeout=timeout)

    def clear(self) -> None:
        """
        清空缓冲区。
        """
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Empty:
                break

    def empty(self) -> bool:
        """
        判断缓冲区是否为空。
        """
        return self._queue.empty()

    @property
    def size(self) -> int:
        """
        当前缓冲区元素数量。
        """
        return self._queue.qsize()