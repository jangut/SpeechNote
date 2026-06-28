"""
应用程序入口。

Application 是整个工程唯一知道所有对象的人，
负责对象创建、依赖注入、生命周期管理。

禁止在此编写业务逻辑。
"""

from __future__ import annotations

from core.logger import configure_logger, get_logger

from config import Config


class Application:
    """SpeechNote 应用程序。"""


    def __init__(self) -> None:
        self._config = Config()
        self._logger = get_logger()
        
    def initialize(self) -> None:
        """初始化应用程序。"""

        configure_logger()

        self._logger.info(
            "%s v%s initializing...",
            self._config.app_name,
            self._config.version,
        )

    def run(self) -> None:
        """启动应用程序。"""
        self.initialize()

        self._logger.info("Application started.")

        try:
            #
            # 后续：
            # Recorder
            # EventBus
            # ASRWorker
            # Plugins
            #
            pass

        except KeyboardInterrupt:
            self._logger.info("Keyboard interrupt received.")

        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """关闭应用程序。"""
        self._logger.info("Application stopped.")