"""Category and material from a CLIP embedding. Trained MLP heads (`weights/heads.pt`) win when
present; otherwise zero-shot prompts, averaged over a few templates."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from ... import taxonomy
from ...config import get_settings
from .. import registry
from ..embed_util import normalize
from . import embedder

TEMPLATES = ["a photo of a {}.", "a photo of a lost {}.", "a {} lying on a table.", "a close-up photo of a {}."]
PHRASES = {
    "id_card": "student ID card",
    "power_bank": "power bank",
    "earbuds": "pair of wireless earbuds",
    "headphones": "pair of headphones",
    "keys": "bunch of keys",
    "spectacles": "pair of eyeglasses",
    "backpack": "backpack",
    "bottle": "water bottle",
    "charger": "phone charger",
    "notebook": "paper notebook",
    "watch": "wrist watch",
}
LOGIT_SCALE = 100.0


def _phrase(category: str) -> str:
    return PHRASES.get(category, category.replace("_", " "))


@lru_cache
def _zero_shot(names: tuple[str, ...], phrases: tuple[str, ...]) -> np.ndarray:
    rows = []
    for phrase in phrases:
        rows.append(normalize(embedder.embed_texts([t.format(phrase) for t in TEMPLATES]).mean(axis=0)))
    return np.stack(rows)


@lru_cache
def _heads():
    path = get_settings().weights_path / "heads.pt"
    if not path.exists():
        return None
    import torch

    blob = torch.load(path, map_location="cpu")
    registry.note("attribute_heads", "trained heads.pt")
    return blob


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / e.sum()


def _predict_head(emb: np.ndarray, head: str) -> list[tuple[str, float]] | None:
    blob = _heads()
    if not blob or head not in blob:
        return None
    import torch

    spec = blob[head]
    net = torch.nn.Sequential(
        torch.nn.Linear(spec["in_dim"], spec["hidden"]), torch.nn.ReLU(), torch.nn.Linear(spec["hidden"], len(spec["classes"]))
    )
    net.load_state_dict(spec["state_dict"])
    with torch.no_grad():
        p = torch.softmax(net(torch.from_numpy(emb[None]).float()), -1)[0].numpy()
    return sorted(zip(spec["classes"], p.tolist()), key=lambda t: -t[1])


def predict_category(emb: np.ndarray) -> list[tuple[str, float]]:
    """Ranked [(category, probability)] over the 18 categories."""
    trained = _predict_head(emb, "category")
    if trained:
        return trained
    names = tuple(taxonomy.category_names())
    text = _zero_shot(names, tuple(_phrase(c) for c in names))
    if not get_settings().light_ml:
        registry.note("attribute_heads", "CLIP zero-shot prompts")
    p = _softmax(LOGIT_SCALE * text @ emb)
    return sorted(zip(names, p.tolist()), key=lambda t: -t[1])


def predict_material(emb: np.ndarray) -> list[tuple[str, float]]:
    trained = _predict_head(emb, "material")
    if trained:
        return trained
    names = tuple(taxonomy.materials())
    text = _zero_shot(names, tuple(f"{m} object" if m != "fabric" else "fabric or cloth object" for m in names))
    p = _softmax(LOGIT_SCALE * text @ emb)
    return sorted(zip(names, p.tolist()), key=lambda t: -t[1])
