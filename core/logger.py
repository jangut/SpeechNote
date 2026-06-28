"""
SpeechNote 日志模块。

整个工程统一从这里获取 Logger。

禁止任何业务模块直接 import logging。
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "SpeechNote"


def configure_logger() -> None:
    """初始化全局 Logger。"""

    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
    )
    logger.addHandler(handler)

    logger.propagate = False


def get_logger() -> logging.Logger:
    """获取全局 Logger。"""
    return logging.getLogger(_LOGGER_NAME)
