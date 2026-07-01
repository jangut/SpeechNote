"""
工程统一事件定义。

整个工程禁止直接使用字符串事件名称，
统一引用 Events.xxx。
"""

from enum import Enum


class Events(str, Enum):
    """系统事件。"""

    START = "start"
    STOP = "stop"

    AUDIO = "audio"
    SENTENCE = "sentence"

    ERROR = "error"
