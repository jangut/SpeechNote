"""
Markdown 插件。

将识别结果写入 Markdown 文件。
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

from core.event import Event, EventBus
from core.events import Events
from core.logger import get_logger
from plugins.base import BasePlugin


class MarkdownPlugin(BasePlugin):
    """
    Markdown 插件。

    将识别到的文本写入 Markdown 文件。
    """

    def __init__(self, output_dir: str | Path) -> None:
        self._logger = get_logger()
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._file: Path | None = None

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

    def start(self) -> None:
        """
        启动插件。
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._file = self._output_dir / f"notes_{timestamp}.md"
        self._file.write_text(f"# SpeechNote 笔记\n\n", encoding="utf-8")
        self._logger.info("MarkdownPlugin started: %s", self._file)

    def stop(self) -> None:
        """
        停止插件。
        """
        if self._file:
            self._file = None
        self._logger.info("MarkdownPlugin stopped.")

    def _on_sentence(self, event: Event) -> None:
        """
        处理识别结果事件。
        """
        if self._file is None:
            return

        sentence = event.data
        line = f"- {sentence.text}\n"
        with self._file.open("a", encoding="utf-8") as f:
            f.write(line)

    def _on_error(self, event: Event) -> None:
        """
        处理错误事件。
        """
        self._logger.error("Error event: %s", event.data)
