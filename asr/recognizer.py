"""
语音识别器实现。

双后端 ONNX / PyTorch 自动降级：
- ONNX (funasr_onnx)：推荐，无 PyTorch 依赖
- PyTorch (funasr)：后备，需要 torch
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from asr.base import BaseRecognizer
from core.logger import get_logger
from core.sentence import Sentence


class FakeRecognizer(BaseRecognizer):
    """Fake 语音识别器，固定返回「你好，世界」。"""

    def __init__(self) -> None:
        self._logger = get_logger()
        self._loaded = False

    def load_model(self) -> None:
        self._loaded = True
        self._logger.info("FakeRecognizer model loaded.")

    def recognize(self) -> Sentence:
        return Sentence(raw_text="你好，世界", text="你好，世界", is_final=True)

    def release(self) -> None:
        self._loaded = False
        self._logger.info("FakeRecognizer released.")


class SenseVoiceRecognizer(BaseRecognizer):
    "基于 SenseVoice 的语音识别器。"

    def __init__(
        self,
        model_dir: str | Path,
        device: str = "cpu",
        quantize: bool = True,
    ) -> None:
        self._logger = get_logger()
        self._model_dir = model_dir
        self._device = device
        self._quantize = quantize
        self._backend: str | None = None
        self._model = None

    # ── 加载（ONNX 优先 → PyTorch 降级）────────────────────────────────

    def load_model(self) -> None:
        "加载模型，ONNX 优先，PyTorch 降级。"
        if self._load_onnx():
            return
        self._logger.info("funasr_onnx 不可用，降级为 PyTorch 后端")
        self._load_pytorch()

    def _load_onnx(self) -> bool:
        "通过 funasr_onnx（ONNX Runtime）加载。"
        try:
            from funasr_onnx import SenseVoiceSmall
        except ImportError:
            return False
        self._logger.info("Loading SenseVoice ONNX model...")
        try:
            self._model = SenseVoiceSmall(
            str(self._model_dir), batch_size=1, quantize=self._quantize,
            )
        except Exception:
            self._logger.exception("ONNX model creation failed")
            return False
        self._backend = "onnx"
        self._logger.info("SenseVoice ONNX model loaded")
        return True

    def _load_pytorch(self) -> None:
        "通过 funasr（PyTorch）加载。"
        from funasr import AutoModel
        self._logger.info("Loading SenseVoice PyTorch model...")
        self._model = AutoModel(
            model=str(self._model_dir),
            device=self._device,
            disable_update=True,
        )
        self._backend = "pytorch"
        self._logger.info("SenseVoice PyTorch model loaded")

    # ── 推理 ──────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        "去除 SenseVoice 标签（语言、情感、事件等）。"
        return re.sub(r"<\|.*?\|>", "", text).strip()

    def recognize(self, audio: np.ndarray) -> Sentence:
        "语音识别，自动选择后端推理方式。"
        assert self._model is not None

        if audio.ndim == 2:
            audio = audio.squeeze(axis=1)

        if self._backend == "onnx":
            result = self._model(audio, textnorm="withitn")
            if isinstance(result, list):
                text = result[0]
            elif isinstance(result, dict):
                text = result.get("text", result.get("preds", ""))
            else:
                text = str(result)
        else:
            result = self._model.generate(input=audio, disable_pbar=True)
            text = result[0]["text"]

        text = self._clean_text(text)
        return Sentence(
            raw_text=text, text=text, is_final=True, confidence=1.0,
        )

    def release(self) -> None:
        "释放模型资源。"
        self._model = None
        backend = self._backend or "none"
        self._backend = None
        self._logger.info("SenseVoice model released (backend=%s)", backend)
