# Training (the compute bucket)

Everything the GPU is for, written and syntax-checked but **not run**. Run these on Colab or Kaggle, then bring the files back.

| Notebook | Needs | Produces | Time |
|---|---|---|---|
| `01_build_dataset.ipynb` | CPU, ~5 GB Drive | `reunite_dataset.zip`, `dataset_card.json` | ~20 min |
| `02_finetune_yolo.ipynb` | GPU (a T4 is enough) | `detector.pt`, `detector_metrics.json` | 30 to 60 min |
| `03_attribute_heads.ipynb` | GPU helps | `heads.pt`, `heads_metrics.json` (with the zero-shot baseline to beat) | ~10 min |
| `04_metric_learning.ipynb` (stretch) | GPU helps, 50+ real pairs with photos | `projection.pt` | ~5 min |

Order: `01` then `02` then `03`. Before `01`, add your own photos for weak classes (ID cards, keys, earbuds, wallets, chargers, power banks have no public source); the notebook prints how many boxes each class has and flags the thin ones.

Bring the outputs back and install them (this validates class lists and file shapes first, and copies nothing if any check fails):

```bash
python training/export.py --detector detector.pt --detector-metrics detector_metrics.json --skip-load \
    --heads heads.pt --heads-metrics heads_metrics.json --dataset-card dataset_card.json
python -m eval.run_eval --pairs real          # the before/after table for the pitch
```

The backend loads `backend/weights/{detector,heads,projection}.pt` and `calibration.json` at startup and logs the path each stage took. The calibration is different: it needs no GPU, and `python -m eval.run_eval --pairs real --write-weights` fits and installs it from your real pairs.

`_build_notebooks.py` regenerates the notebooks (JSON reviews badly, so the source is that file).
