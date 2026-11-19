"""Genuine 2-stem MDX/ONNX separation backend (priority 1 & 3, NOT Demucs --two-stems mix hack)."""

from __future__ import annotations

import logging
from pathlib import Path
import tempfile
from typing import Any, Optional
import wave

import numpy as np

from ai.backend import SeparationBackend
from ai.models import AIModelSpec
from ai.resource_guard import cleanup_temp_outputs, is_oom_exception, release_torch_and_memory
from core.config import AIConfig
from core.models import OOMRecoveryAction

logger = logging.getLogger(__name__)


class SeparationOOMError(RuntimeError):
    """Raised when GPU OOM persists after bounded recovery attempts."""

    def __init__(
        self,
        message: str,
        *,
        recovery_options: Optional[list[OOMRecoveryAction]] = None,
        tried_segments: Optional[list[int]] = None,
    ) -> None:
        super().__init__(message)
        self.recovery_options = recovery_options or [
            OOMRecoveryAction.REDUCE_SEGMENT,
            OOMRecoveryAction.LIGHTER_MODEL,
            OOMRecoveryAction.CPU_FALLBACK,
        ]
        self.tried_segments = tried_segments or []


def _write_pcm16_wav(path: Path, pcm_f32: np.ndarray, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wf:
        ch = 2 if pcm_f32.ndim == 2 and pcm_f32.shape[1] >= 2 else 1
        wf.setnchannels(ch)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        i16 = (np.clip(pcm_f32, -1.0, 1.0) * 32767.0).astype(np.int16)
        wf.writeframes(i16.tobytes())


def _read_wav_f32(path: Path, target_frames: Optional[int] = None) -> tuple[np.ndarray, int]:
    from audio.pcm_utils import decode_wave_bytes

    try:
        import soundfile as sf  # type: ignore[import-untyped]

        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
    except Exception:
        with wave.open(str(path), "rb") as wf:
            sr = int(wf.getframerate())
            ch = max(1, int(wf.getnchannels()))
            sw = int(wf.getsampwidth())
            raw = wf.readframes(wf.getnframes())
        arr = decode_wave_bytes(raw, sw, ch)

    if arr.size > 0 and not np.all(np.isfinite(arr)):
        arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)

    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.shape[1] == 1:
        arr = np.repeat(arr, 2, axis=1)
    elif arr.shape[1] > 2:
        arr = arr[:, :2]

    if target_frames is not None:
        if arr.shape[0] > target_frames:
            arr = arr[:target_frames]
        elif arr.shape[0] < target_frames:
            pad = np.zeros((target_frames - arr.shape[0], 2), dtype=np.float32)
            arr = np.vstack([arr, pad])
    return arr.astype(np.float32, copy=False), int(sr)


def _match_2stem_output(output_files: list[str | Path], expected_stems: tuple[str, ...]) -> dict[str, Path]:
    paths = [Path(p) for p in output_files]
    mapped: dict[str, Path] = {}
    for stem in expected_stems:
        s_low = stem.lower()
        for p in paths:
            name_low = p.name.lower()
            if s_low == "vocals" and ("vocal" in name_low):
                mapped[stem] = p
                break
            if s_low == "instrumental" and ("inst" in name_low or "no_vocal" in name_low or "accompaniment" in name_low):
                mapped[stem] = p
                break
    if len(mapped) < len(expected_stems) and len(paths) == len(expected_stems):
        for stem, p in zip(expected_stems, paths):
            mapped.setdefault(stem, p)
    return mapped


class MDXSeparatorBackend(SeparationBackend):
    """Wraps `audio-separator` for true 2-stem MDX-ONNX (or explicit opt-in RoFormer) models.

    Runs inside the isolated AIWorkerProcess; enforces batch_size=1 and conservative segment_size.
    """

    def __init__(
        self,
        model_spec: AIModelSpec,
        *,
        use_gpu: bool = True,
        segment_seconds: Optional[int] = None,
        overlap: float = 0.25,
        ai_config: Optional[AIConfig] = None,
        output_dir: Optional[Path] = None,
        model_file_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(
            model_spec,
            use_gpu=use_gpu,
            segment_seconds=segment_seconds,
            overlap=overlap,
            ai_config=ai_config,
        )
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "listenscope_ai"
        self.model_file_dir = model_file_dir
        self._separator: Any = None
        self._tmp_root: Optional[tempfile.TemporaryDirectory[str]] = None

    def load_model(self) -> None:
        if self._loaded and self._separator is not None:
            return

        use_dml_plan_a = False
        if self.use_gpu or (self.ai_config.igpu_directml_2stem and self.model_spec.architecture == "MDX-ONNX"):
            try:
                import onnxruntime as ort  # type: ignore[import-not-found]

                if hasattr(ort, "preload_dlls"):
                    try:
                        ort.preload_dlls()
                    except Exception as exc:
                        logger.debug("onnxruntime.preload_dlls() warning: %s", exc)
                providers = list(ort.get_available_providers())
                if (
                    self.ai_config.igpu_directml_2stem
                    and self.model_spec.architecture == "MDX-ONNX"
                    and "DmlExecutionProvider" in providers
                ):
                    use_dml_plan_a = True
                    logger.info(
                        "[Hybrid Plan A] Routing 2-Stem MDX-ONNX to DirectML iGPU (device_id=%d).",
                        int(self.ai_config.igpu_directml_device_id),
                    )
                elif self.use_gpu and "CUDAExecutionProvider" not in providers:
                    raise RuntimeError(
                        f"请求 GPU MDX 推理，但 ONNX Runtime 缺少 CUDAExecutionProvider (available={providers})。"
                    )
            except ImportError as exc:
                raise RuntimeError("未安装 onnxruntime-gpu / onnxruntime-directml，无法运行 GPU MDX-ONNX 模型。") from exc
        self._using_directml = use_dml_plan_a

        try:
            from audio_separator.separator import Separator  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "未安装 `audio-separator`。请在 AI Worker 环境中安装: pip install audio-separator[gpu]"
            ) from exc

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._tmp_root = tempfile.TemporaryDirectory(prefix="ls_mdx_", dir=self.output_dir)
        chunk_out_dir = Path(self._tmp_root.name) / "out"
        chunk_out_dir.mkdir(parents=True, exist_ok=True)

        seg_size = int(self.segment_seconds or self.ai_config.mdx_segment_size)
        if self.model_spec.architecture == "MDX-ONNX":
            seg_size = max(128, min(seg_size, 512))

        kwargs: dict[str, Any] = {
            "output_dir": str(chunk_out_dir),
            "output_format": "WAV",
            "use_soundfile": True,
            "use_autocast": bool(self.use_gpu),
            "mdx_params": {
                "hop_length": 1024,
                "segment_size": seg_size,
                "overlap": float(self.overlap),
                "batch_size": int(self.ai_config.mdx_batch_size),
                "enable_denoise": False,
            },
        }
        if self.model_file_dir is not None:
            kwargs["model_file_dir"] = str(self.model_file_dir)
        if self.model_spec.architecture == "RoFormer":
            kwargs["mdxc_params"] = {
                "segment_size": max(64, seg_size),
                "override_model_segment_size": False,
                "batch_size": 1,
                "overlap": 4,
                "pitch_shift": 0,
            }

        if self._using_directml:
            import inspect
            try:
                sig = inspect.signature(Separator.__init__)
                if "use_directml" in sig.parameters:
                    kwargs["use_directml"] = True
            except Exception:
                pass
        try:
            separator = Separator(**kwargs)
            separator.load_model(model_filename=self.model_spec.separator_filename)
            self._separator = separator
            self._loaded = True
        except Exception as exc:
            self.unload_model()
            if is_oom_exception(exc):
                raise SeparationOOMError(
                    f"加载 {self.model_spec.display_name} 时发生 OOM: {exc}",
                    recovery_options=[
                        OOMRecoveryAction.REDUCE_SEGMENT,
                        OOMRecoveryAction.LIGHTER_MODEL,
                        OOMRecoveryAction.CPU_FALLBACK,
                    ],
                ) from exc
            raise

    def separate_chunk(self, chunk_f32: np.ndarray, sample_rate: int) -> dict[str, np.ndarray]:
        if not self._loaded or self._separator is None or self._tmp_root is None:
            raise RuntimeError("MDX model is not loaded")

        tmp_base = Path(self._tmp_root.name)
        in_wav = tmp_base / "chunk_in.wav"
        out_dir = tmp_base / "out"
        for leftover in out_dir.glob("*"):
            cleanup_temp_outputs(leftover)

        _write_pcm16_wav(in_wav, chunk_f32, sample_rate)
        target_frames = int(chunk_f32.shape[0])

        try:
            output_names = (
                {"Vocals": "stem_vocals", "Instrumental": "stem_instrumental"}
                if self.model_spec.stem_mode == "2stem"
                else None
            )
            out_files = self._separator.separate(str(in_wav), output_names)
            resolved: list[Path] = []
            for f in out_files:
                fp = Path(f)
                if fp.exists():
                    resolved.append(fp)
                elif (out_dir / fp).exists():
                    resolved.append(out_dir / fp)
                else:
                    resolved.append(out_dir / fp.name)

            mapped = _match_2stem_output(resolved, self.model_spec.stems)
            stems: dict[str, np.ndarray] = {}
            for stem_name in self.model_spec.stems:
                if stem_name not in mapped or not mapped[stem_name].exists():
                    raise RuntimeError(f"MDX 分块分离缺少输出音轨 '{stem_name}' (输出: {resolved})")
                arr, _ = _read_wav_f32(mapped[stem_name], target_frames=target_frames)
                stems[stem_name] = arr
            return stems
        except Exception as exc:
            release_torch_and_memory()
            if is_oom_exception(exc):
                raise SeparationOOMError(
                    f"MDX 推理阶段显存不足 (OOM): {exc}",
                    recovery_options=[
                        OOMRecoveryAction.REDUCE_SEGMENT,
                        OOMRecoveryAction.LIGHTER_MODEL,
                        OOMRecoveryAction.CPU_FALLBACK,
                    ],
                ) from exc
            raise
        finally:
            in_wav.unlink(missing_ok=True)
            for leftover in out_dir.glob("*"):
                cleanup_temp_outputs(leftover)

    def unload_model(self) -> None:
        self._separator = None
        self._loaded = False
        if self._tmp_root is not None:
            try:
                self._tmp_root.cleanup()
            except Exception:
                pass
            self._tmp_root = None
        release_torch_and_memory()
