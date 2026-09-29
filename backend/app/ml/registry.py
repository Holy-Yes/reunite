"""Lazy model loading, device choice, and a record of which path each stage took.

Everything heavy is imported inside functions so `ML_MODE=light` (tests, CI) never pays for torch.
Model files live under the project (`.cache/`), not in the user's home, so the external volume holds them.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from ..config import ROOT, get_settings

log = logging.getLogger("reunite.ml")

_status: dict[str, str] = {}
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ml")


def setup_cache_dirs() -> None:
    limit_threads()
    cache = ROOT / ".cache"
    for var, sub in (("HF_HOME", "hf"), ("TORCH_HOME", "torch"), ("YOLO_CONFIG_DIR", "ultralytics")):
        os.environ.setdefault(var, str(cache / sub))


def limit_threads() -> None:
    """Keep the math libraries from each grabbing every core: on a busy laptop that made everything slower."""
    n = int(os.environ.get("ML_THREADS", "2"))
    try:
        import torch

        torch.set_num_threads(n)
    except Exception:  # noqa: BLE001
        pass
    try:
        import cv2

        cv2.setNumThreads(n)
    except Exception:  # noqa: BLE001
        pass


def note(stage: str, path: str) -> None:
    """Record (and log once) which implementation a stage is using, e.g. detector -> 'yolo11n (coco)'."""
    if _status.get(stage) != path:
        _status[stage] = path
        log.info("ml stage %s using %s", stage, path)


def status() -> dict[str, str]:
    return dict(_status)


def device() -> str:
    want = get_settings().device.lower()
    if want != "auto":
        return want
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def run_ml(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
    """Model calls go through one thread so memory stays flat on an 8 GB machine."""
    return _executor.submit(fn, *args, **kwargs)


def call_ml(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return run_ml(fn, *args, **kwargs).result()
