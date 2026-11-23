"""Resource-guarded 4-stem HTDemucs separation backend for RTX 5060 Ti 8GB VRAM."""

from __future__ import annotations

import logging
from math import gcd
from pathlib import Path
import tempfile
from typing import Any, Optional

import numpy as np
from scipy.signal import resample_poly

from ai.backend import SeparationBackend
from ai.models import AIModelSpec
from ai.resource_guard import cleanup_temp_outputs, is_oom_exception, release_torch_and_memory
from core.config import AIConfig
from core.models import OOMRecoveryAction

from .mdx_backend import SeparationOOMError, _read_wav_f32, _write_pcm16_wav

logger = logging.getLogger(__name__)


def _resample_chunk(pcm_f32: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or pcm_f32.shape[0] == 0:
        return pcm_f32.astype(np.float32, copy=False)
    g = gcd(int(src_rate), int(dst_rate))
    up = int(dst_rate) // g
    down = int(src_rate) // g
    return resample_poly(pcm_f32, up, down, axis=0).astype(np.float32, copy=False)


class DemucsSeparatorBackend(SeparationBackend):
    """HTDemucs 4-stem backend enforcing jobs=1, shifts=1, overlap=0.25, segment<=10s, and bounded OOM step-down."""

    def __init__(
        self,
        model_spec: AIModelSpec,
        *,
        use_gpu: bool = True,
        segment_seconds: Optional[int] = None,
        overlap: float = 0.25,
        ai_config: Optional[AIConfig] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        cfg = ai_config or AIConfig()
        raw_segment = cfg.demucs_default_segment_sec if segment_seconds is None else segment_seconds
        capped_segment = min(int(raw_segment), max(cfg.demucs_segment_ladder))
        super().__init__(
            model_spec,
            use_gpu=use_gpu,
            segment_seconds=capped_segment,
            overlap=float(overlap),
            ai_config=cfg,
        )
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "listenscope_ai"
        self._mode: str = "none"  # "demucs" or "audio_separator"
        self._model: Any = None
        self._torch: Any = None
        self._apply_model_fn: Any = None
        self._device: str = "cpu"
        self._separator: Any = None
        self._tmp_root: Optional[tempfile.TemporaryDirectory[str]] = None

    def _segment_ladder(self) -> list[float]:
        ladder = [float(s) for s in self.ai_config.demucs_segment_ladder if s <= self.segment_seconds]
        if not ladder:
            ladder = [float(min(self.ai_config.demucs_segment_ladder))]
        elif float(self.segment_seconds) not in ladder:
            ladder.insert(0, float(self.segment_seconds))

        # Respect HTDemucs checkpoint max_allowed_segment / model.segment to prevent ValueError
        max_seg: Optional[float] = None
        if self._mode == "demucs" and self._model is not None:
            for attr in ("max_allowed_segment", "segment"):
                val = getattr(self._model, attr, None)
                if isinstance(val, (int, float)) and val > 0:
                    max_seg = float(val) if max_seg is None else min(max_seg, float(val))

        eff: list[float] = []
        for s in sorted(set(ladder), reverse=True):
            clamped = min(s, max_seg) if max_seg is not None else s
            if not any(abs(clamped - prev) < 1e-4 for prev in eff):
                eff.append(clamped)
        return eff

    def load_model(self) -> None:
        if self._loaded:
            return

        # Prefer direct demucs Python API so weights stay loaded across streaming chunks without per-chunk reload
        try:
            import torch  # type: ignore[import-not-found]
            from demucs.apply import apply_model  # type: ignore[import-not-found]
            from demucs.pretrained import get_model  # type: ignore[import-not-found]

            if self.use_gpu and not torch.cuda.is_available():
                raise RuntimeError("请求 GPU HTDemucs 分轨，但当前 torch.cuda.is_available() 为 False。")

            model_name = self.model_spec.separator_filename.replace(".yaml", "")
            model = get_model(model_name)
            device = "cuda" if self.use_gpu else "cpu"
            model.to(device)
            model.eval()

            self._torch = torch
            self._apply_model_fn = apply_model
            self._model = model
            self._device = device
            self._mode = "demucs"
            self._loaded = True
            return
        except ImportError:
            logger.info("Direct `demucs` package unavailable, falling back to `audio-separator` Demucs loader.")
        except Exception as exc:
            self.unload_model()
            if is_oom_exception(exc):
                raise SeparationOOMError(
                    f"加载 HTDemucs 到显存时 OOM: {exc}",
                    recovery_options=[
                        OOMRecoveryAction.REDUCE_SEGMENT,
                        OOMRecoveryAction.LIGHTER_MODEL,
                        OOMRecoveryAction.CPU_FALLBACK,
                    ],
                ) from exc
            raise

        try:
            from audio_separator.separator import Separator  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "未安装 `demucs` 或 `audio-separator`。请在 AI Worker 环境安装: pip install demucs audio-separator[gpu]"
            ) from exc

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._tmp_root = tempfile.TemporaryDirectory(prefix="ls_demucs_", dir=self.output_dir)
        chunk_out_dir = Path(self._tmp_root.name) / "out"
        chunk_out_dir.mkdir(parents=True, exist_ok=True)
        import inspect

        sep_kwargs: dict[str, Any] = {
            "output_dir": str(chunk_out_dir),
            "output_format": "WAV",
            "use_soundfile": True,
            "use_autocast": bool(self.use_gpu),
            "demucs_params": {
                "segment_size": int(self.segment_seconds),
                "shifts": int(self.ai_config.demucs_shifts),  # Strict shifts=1
                "overlap": float(self.overlap),
                "segments_enabled": True,
            },
        }
        extra_keys: list[str] = []
        try:
            sig = inspect.signature(Separator.__init__)
            for k, v in (
                ("sample_rate", 48000),
                ("normalization_threshold", 1.0),
                ("amplification_threshold", 0.0),
            ):
                if k in sig.parameters:
                    sep_kwargs[k] = v
                    extra_keys.append(k)
        except Exception:
            pass
        try:
            self._separator = Separator(**sep_kwargs)
        except TypeError as type_exc:
            if not extra_keys:
                raise
            logger.warning(
                "Demucs Separator rejected optional kwargs %s (%s); falling back to legacy defaults",
                extra_keys,
                type_exc,
            )
            for k in extra_keys:
                sep_kwargs.pop(k, None)
            self._separator = Separator(**sep_kwargs)
        self._separator.load_model(model_filename=self.model_spec.separator_filename)
        self._mode = "audio_separator"
        self._loaded = True

    def separate_chunk(self, chunk_f32: np.ndarray, sample_rate: int) -> dict[str, np.ndarray]:
        if not self._loaded:
            raise RuntimeError("Demucs model is not loaded")

        ladder = self._segment_ladder()
        max_attempts = 1 + int(self.ai_config.max_oom_retries)
        tried_segments: list[int] = []
        last_oom: Optional[BaseException] = None

        for attempt_idx in range(min(max_attempts, len(ladder))):
            seg = ladder[attempt_idx]
            tried_segments.append(int(round(seg)))
            try:
                if self._mode == "demucs":
                    return self._separate_with_demucs(chunk_f32, sample_rate, segment_sec=seg)
                return self._separate_with_audio_separator(chunk_f32, sample_rate, segment_sec=int(round(seg)))
            except Exception as exc:
                release_torch_and_memory()
                if is_oom_exception(exc):
                    last_oom = exc
                    logger.warning("HTDemucs OOM at segment=%ss (attempt %s/%s)", seg, attempt_idx + 1, max_attempts)
                    continue
                raise

        raise SeparationOOMError(
            f"HTDemucs 显存不足 (OOM)，尝试 segment={tried_segments} 后仍超出限制: {last_oom}",
            recovery_options=[
                OOMRecoveryAction.REDUCE_SEGMENT,
                OOMRecoveryAction.LIGHTER_MODEL,
                OOMRecoveryAction.CPU_FALLBACK,
            ],
            tried_segments=tried_segments,
        )

    def _separate_with_demucs(
        self,
        chunk_f32: np.ndarray,
        sample_rate: int,
        *,
        segment_sec: float,
    ) -> dict[str, np.ndarray]:
        torch = self._torch
        model = self._model
        model_sr = int(getattr(model, "samplerate", 44100))

        canon = np.asarray(chunk_f32, dtype=np.float32)
        if canon.ndim == 1:
            canon = np.repeat(canon[:, None], 2, axis=1)
        elif canon.shape[1] == 1:
            canon = np.repeat(canon, 2, axis=1)
        elif canon.shape[1] > 2:
            canon = canon[:, :2]
        if canon.size > 0 and not np.all(np.isfinite(canon)):
            canon = np.nan_to_num(canon, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)

        target_frames = int(canon.shape[0])
        if target_frames <= 0:
            source_names = list(getattr(model, "sources", self.model_spec.stems))
            return {name: np.empty((0, 2), dtype=np.float32) for name in source_names}

        work = _resample_chunk(canon, sample_rate, model_sr)
        tensor = None
        sources = None
        try:
            mix = torch.from_numpy(np.ascontiguousarray(work.T, dtype=np.float32)).to(self._device, dtype=torch.float32)
            ref = mix.mean(0)
            ref_mean = ref.mean()
            ref_std = ref.std()
            is_non_silent = bool(float(ref_std.item()) >= 1e-8)
            mix_in = (mix - ref_mean) / (ref_std + 1e-8) if is_non_silent else mix
            tensor = mix_in.unsqueeze(0)
            with torch.inference_mode():
                # Upstream demucs.apply.apply_model does NOT accept `jobs=`; use shifts=1 and num_workers=0.
                sources = self._apply_model_fn(
                    model,
                    tensor,
                    shifts=int(self.ai_config.demucs_shifts),  # Strict shifts=1
                    split=True,
                    overlap=float(self.overlap),
                    segment=float(segment_sec),
                    num_workers=0,
                    progress=False,
                    device=self._device,
                )[0]
                if is_non_silent:
                    sources = sources * (ref_std + 1e-8) + ref_mean

            source_names = list(getattr(model, "sources", self.model_spec.stems))
            out: dict[str, np.ndarray] = {}
            for idx, name in enumerate(source_names):
                stem_np = sources[idx].detach().cpu().numpy().T.astype(np.float32, copy=False)
                restored = _resample_chunk(stem_np, model_sr, sample_rate)
                if restored.ndim == 1:
                    restored = np.repeat(restored[:, None], 2, axis=1)
                elif restored.shape[1] == 1:
                    restored = np.repeat(restored, 2, axis=1)
                elif restored.shape[1] > 2:
                    restored = restored[:, :2]
                if restored.shape[0] > target_frames:
                    restored = restored[:target_frames]
                elif restored.shape[0] < target_frames:
                    pad = np.zeros((target_frames - restored.shape[0], restored.shape[1]), dtype=np.float32)
                    restored = np.vstack([restored, pad])
                if restored.size > 0 and not np.all(np.isfinite(restored)):
                    restored = np.nan_to_num(restored, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)
                out[name] = restored
            return out
        finally:
            if tensor is not None:
                del tensor
            if sources is not None:
                del sources
            release_torch_and_memory()

    def _separate_with_audio_separator(
        self,
        chunk_f32: np.ndarray,
        sample_rate: int,
        *,
        segment_sec: int,
    ) -> dict[str, np.ndarray]:
        assert self._tmp_root is not None and self._separator is not None
        tmp_base = Path(self._tmp_root.name)
        in_wav = tmp_base / "chunk_in.wav"
        out_dir = tmp_base / "out"
        for leftover in out_dir.glob("*"):
            cleanup_temp_outputs(leftover)
        _write_pcm16_wav(in_wav, chunk_f32, sample_rate)
        target_frames = int(chunk_f32.shape[0])

        try:
            self._separator.arch_specific_params["Demucs"]["segment_size"] = int(segment_sec)
        except Exception:
            pass

        try:
            output_names = {
                "Vocals": "stem_vocals",
                "Drums": "stem_drums",
                "Bass": "stem_bass",
                "Other": "stem_other",
            }
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
            stems: dict[str, np.ndarray] = {}
            for stem in self.model_spec.stems:
                matched = next((p for p in resolved if stem.lower() in p.name.lower()), None)
                if matched is None or not matched.exists():
                    raise RuntimeError(f"Demucs 分块输出缺少 '{stem}': {resolved}")
                arr, out_sr = _read_wav_f32(matched)
                if out_sr != sample_rate:
                    arr = _resample_chunk(arr, out_sr, sample_rate)
                from .mdx_backend import _fit_frames
                stems[stem] = _fit_frames(arr, target_frames)
            return stems
        finally:
            in_wav.unlink(missing_ok=True)
            for leftover in out_dir.glob("*"):
                cleanup_temp_outputs(leftover)

    def unload_model(self) -> None:
        self._model = None
        self._apply_model_fn = None
        self._separator = None
        self._loaded = False
        self._mode = "none"
        if self._tmp_root is not None:
            try:
                self._tmp_root.cleanup()
            except Exception:
                pass
            self._tmp_root = None
        release_torch_and_memory()
