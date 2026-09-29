"""CLIP ViT-B/32 image and text encoders sharing one 512-dimension space. That shared space is what
lets a text-only lost report match a photo-only found report."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

from ...config import get_settings
from .. import registry
from ..embed_util import hash_embed, normalize

DIM = 512


@lru_cache
def _clip():
    registry.setup_cache_dirs()
    import open_clip
    import torch

    dev = registry.device()
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
    model = model.to(dev).eval()
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    registry.note("clip", f"open_clip ViT-B/32 (openai) on {dev}")
    return model, preprocess, tokenizer, torch, dev


@lru_cache
def _adapter() -> np.ndarray | None:
    """Optional `weights/projection.pt` from training/04 (stretch): a residual adapter, image = normalize(x + x @ delta).
    It only touches image embeddings, so text and cross-modal similarity keep the raw CLIP geometry."""
    path = get_settings().weights_path / "projection.pt"
    if not path.exists():
        return None
    import torch

    blob = torch.load(path, map_location="cpu")
    registry.note("projection", "trained projection.pt (image adapter)")
    return blob["delta"].float().numpy()


def embed_images(images: list[Image.Image]) -> np.ndarray:
    """(n, 512) float32, L2-normalized."""
    if not images:
        return np.zeros((0, DIM), dtype=np.float32)
    if get_settings().light_ml:
        registry.note("clip", "light (pixel statistics, no cross-modal signal)")
        return np.stack([_light_image(im) for im in images])

    def run():
        model, preprocess, _, torch, dev = _clip()
        batch = torch.stack([preprocess(im.convert("RGB")) for im in images]).to(dev)
        with torch.no_grad():
            return model.encode_image(batch).float().cpu().numpy()

    raw = normalize(registry.call_ml(run))
    delta = _adapter()
    return normalize(raw + raw @ delta) if delta is not None else raw


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    if get_settings().light_ml:
        return np.stack([hash_embed(t, DIM) for t in texts])

    def run():
        model, _, tokenizer, torch, dev = _clip()
        with torch.no_grad():
            return model.encode_text(tokenizer(texts).to(dev)).float().cpu().numpy()

    return normalize(registry.call_ml(run))


def _light_image(im: Image.Image) -> np.ndarray:
    small = np.asarray(im.convert("RGB").resize((8, 8)), dtype=np.float32).reshape(-1) / 255.0  # 192 values
    rng = np.random.default_rng(7)  # fixed projection so it is deterministic across runs
    proj = rng.standard_normal((small.size, DIM)).astype(np.float32)
    return normalize((small - small.mean()) @ proj)
