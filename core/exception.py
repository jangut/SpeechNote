"""
SpeechNote 异常定义。
"""


class SpeechNoteError(Exception):
    """
    SpeechNote 基础异常。

    所有自定义异常均继承此类。
    """


class ConfigError(SpeechNoteError):
    """配置错误。"""


class RecorderError(SpeechNoteError):
    """录音模块错误。"""


class RecognizerError(SpeechNoteError):
    """识别模块错误。"""


class PluginError(SpeechNoteError):
    """插件错误。"""