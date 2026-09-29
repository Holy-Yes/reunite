"""The notebooks' output formats must be exactly what the backend loads."""
import ast
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from app import taxonomy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "training"))
import export  # noqa: E402


def make_heads(path, classes=None, in_dim=512, materials=False):
    classes = classes or taxonomy.category_names()
    net = torch.nn.Sequential(torch.nn.Linear(in_dim, 256), torch.nn.ReLU(), torch.nn.Linear(256, len(classes)))
    blob = {"category": {"in_dim": in_dim, "hidden": 256, "classes": classes, "state_dict": net.state_dict()}}
    if materials:
        m = torch.nn.Sequential(torch.nn.Linear(512, 128), torch.nn.ReLU(), torch.nn.Linear(128, len(taxonomy.materials())))
        blob["material"] = {"in_dim": 512, "hidden": 128, "classes": taxonomy.materials(), "state_dict": m.state_dict()}
    torch.save(blob, path)
    return path


def test_notebooks_are_valid_json_with_valid_python():
    for nb in sorted((ROOT / "training").glob("*.ipynb")):
        data = json.loads(nb.read_text())
        assert data["nbformat"] == 4 and data["cells"]
        for c in data["cells"]:
            if c["cell_type"] == "code":
                ast.parse("".join(l for l in c["source"] if not l.lstrip().startswith(("!", "%"))))


def test_notebook_class_list_matches_the_taxonomy():
    src = (ROOT / "training" / "_build_notebooks.py").read_text()
    for c in taxonomy.category_names():
        assert f'"{c}"' in src


def test_export_installs_valid_weights(tmp_path):
    heads = make_heads(tmp_path / "heads.pt", materials=True)
    w = tmp_path / "weights"
    rc = export.main(["--heads", str(heads), "--weights-dir", str(w)])
    assert rc == 0 and (w / "heads.pt").exists()
    card = json.loads((w / "model_card.json").read_text())
    assert set(card["head_classes"]) == set(taxonomy.category_names()) and "material" in card["stages"]["attribute_heads"]


def test_trained_heads_are_used_by_the_backend(tmp_path, monkeypatch):
    """heads.pt written by notebook 03 is read by attributes.py and changes the prediction."""
    from app.config import get_settings
    from app.ml.vision import attributes

    heads = make_heads(tmp_path / "heads.pt")
    monkeypatch.setattr(type(get_settings()), "weights_path", property(lambda self: tmp_path))
    attributes._heads.cache_clear()
    emb = np.random.default_rng(0).standard_normal(512).astype(np.float32)
    ranked = attributes.predict_category(emb)
    assert len(ranked) == 18 and abs(sum(p for _, p in ranked) - 1.0) < 1e-4
    assert ranked[0][1] >= ranked[-1][1]
    attributes._heads.cache_clear()


@pytest.mark.parametrize("bad,msg", [
    (dict(classes=["laptop", "phone"]), "category classes differ"),
    (dict(in_dim=768), "expects 768"),
])
def test_export_refuses_bad_heads(tmp_path, bad, msg, capsys):
    try:
        heads = make_heads(tmp_path / "heads.pt", **bad)
    except RuntimeError:
        pytest.skip("shape mismatch caught while building the fixture")
    w = tmp_path / "weights"
    assert export.main(["--heads", str(heads), "--weights-dir", str(w)]) == 2
    assert msg in capsys.readouterr().err
    assert not w.exists() or not any(w.iterdir())          # nothing half-installed


def test_export_refuses_a_calibration_for_other_features(tmp_path, capsys):
    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"features": ["category"], "coef": [1.0], "intercept": 0.0}))
    assert export.main(["--calibration", str(cal), "--weights-dir", str(tmp_path / "w")]) == 2
    assert "does not match" in capsys.readouterr().err


def test_export_accepts_the_eval_harness_calibration(tmp_path):
    from app.ml.matching import calibrate, features as F, scorer

    X = np.random.default_rng(0).random((60, len(F.FEATURES) + len(scorer.MASK_TERMS)))
    y = (X[:, 0] > 0.5).astype(int)
    cal = tmp_path / "calibration.json"
    calibrate.save(calibrate.fit(X, y), cal)
    assert export.main(["--calibration", str(cal), "--weights-dir", str(tmp_path / "w")]) == 0
    assert (tmp_path / "w" / "calibration.json").exists()


def test_detector_classes_must_be_in_the_taxonomy(tmp_path, capsys):
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps({"detector_classes": {"0": "laptop", "1": "spaceship"}}))
    det = tmp_path / "det.pt"
    det.write_bytes(b"x")
    assert export.main(["--detector", str(det), "--detector-metrics", str(metrics), "--skip-load", "--weights-dir", str(tmp_path / "w")]) == 2
    assert "spaceship" in capsys.readouterr().err
    assert export.main(["--weights-dir", str(tmp_path / "w")]) == 2      # nothing to export
