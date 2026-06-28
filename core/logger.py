"""
SpeechNote 日志模块。

整个工程统一从这里获取 Logger。

禁止任何业务模块直接 import logging。
"""

from __future__ import annotations

import logging
from typing import Final

_LOGGER_NAME = "SpeechNote"



def configure_logger() -> None:
    """初始化全局 Logger。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )


def get_logger() -> logging.Logger:
    """获取全局 Logger。"""
    return logging.getLogger(_LOGGER_NAME)