"""ListenScope AI separation model registry, worker subprocess, resource guard, and job manager."""

from .backend import MockSeparationBackend, SeparationBackend, build_separation_backend
from .job_manager import AIJobManager
from .models import MODEL_REGISTRY, AIModelSpec, get_default_model_for_mode, list_models
from .resource_guard import cleanup_temp_outputs, inspect_wav_header, stream_chunked_separation

__all__ = [
    "AIJobManager",
    "AIModelSpec",
    "MODEL_REGISTRY",
    "MockSeparationBackend",
    "SeparationBackend",
    "build_separation_backend",
    "cleanup_temp_outputs",
    "get_default_model_for_mode",
    "inspect_wav_header",
    "list_models",
    "stream_chunked_separation",
]
