# Evaluation

Every number in the pitch comes from a report in `eval/reports/`. This folder holds the harness, the synthetic pair generator, and the guide for photographing the real pairs.

```bash
python -m eval.synthetic_pairs               # once: build ~110 synthetic pairs from data/seed/photos
python -m eval.run_eval --pairs synthetic    # P@1/5/10, MRR, mAP, ECE, reliability, per-category, ablation
python -m eval.check_manifest                # validate your real pairs
python -m eval.run_eval --pairs real         # the numbers you can quote
```

Reports are `eval/reports/<date>-<synthetic|real>.json` (rendered by the admin Eval page) and a `.md` summary, plus the fitted `*.calibration.json`. Extraction results are cached in `.cache/eval/`, so reruns after a scoring change take seconds.

## Read the synthetic numbers correctly

Synthetic pairs are **optimistic**. Both views come from one public photo (augmented differently) and the text is generated from the same labels the matcher is scored on. They prove the pipeline runs and show which evidence matters (the ablation table), not how it performs on campus. Every report built from them says so. Quote only `real` reports.

## What is measured

* **P@1, P@5, P@10** are success@k: the true match is in the top k of the ranked list. Each lost report has exactly one true found report, so precision@k as a fraction of k would just be success@k divided by k.
* **Recall@5 / @10** is candidate generation on its own: is the true match in the top k by embedding similarity, before reranking?
* **MRR and mAP** are equal here (one relevant item per query).
* **ECE and the reliability diagram** are on a held-out 30% of pair ids, after fitting a logistic calibration on the other 70% (hard negatives = the top-ranked wrong candidates). The report also gives the ECE of the uncalibrated hand-set scores on the same pairs.
* **Ablation** masks feature groups: image only, text only, + attributes (category, color, brand, marks), + text-to-photo, + location and time.
* Targets: P@1 of at least 0.60 and P@5 of at least 0.85.

Flags: `--pairs synthetic|real|both`, `--seed`, `--pool-size N` (candidates per query, default all), `--no-calibrate`, `--limit N`, `--write-weights` (installs the fitted calibration into `backend/weights/`; do this only from real pairs).

## Photographing real pairs (the part only you can do)

Aim for **150 to 300 pairs**. Fewer works, but each pair then moves P@1 by 1/n.

A pair is one object, seen twice, the way the two reports would really see it:

1. **The lost side.** The owner writes what they would type into the report (do not look at a photo while writing), and optionally photographs the object at home or in their bag.
2. **Move it.** Someone else puts the object somewhere else on campus, in a different zone, on a different surface, in different light.
3. **The found side.** The "finder" photographs it from a different angle, and writes a short found note. Finders say less than owners: skip the colour, forget the brand.
4. **Times.** The lost row carries a window (`start/end`, when they last had it), the found row one moment. The found moment must not be before the window starts.

Mix on purpose, because reality is mixed:

| | Lost side | Found side |
|---|---|---|
| photo and text | about 60% | about 45% |
| text only | about 25% | about 15% |
| photo only | about 15% | about 40% |

Include **look-alikes**: two or three black laptops, several steel bottles, similar backpacks. If every pair is a different kind of object, P@1 will look great and mean nothing. Cover as many of the 18 categories as you can, and use a **dummy ID card** (never a real one) for `id_card`.

Privacy: no faces, no screens with messages, no real names or numbers in photos. Get consent for objects that are not yours. The photos never leave this repo unless you move them.

Files: images go in `eval/pairs/real/imgs/` and are named `<pair>_<side>.jpg`. The manifest is `eval/pairs/manifest.csv`, image paths relative to it:

```
pair_id,side,image,text,zone,timestamp,category
R001,lost,real/imgs/R001_lost.jpg,"black Dell laptop, dent on the lid",z_library,2026-09-21T09:00:00Z/2026-09-21T13:00:00Z,laptop
R001,found,real/imgs/R001_found.jpg,found a black laptop,z_gate,2026-09-21T15:20:00Z,laptop
```

`category` is optional (it only labels the per-category table); zone ids are in `config/campus/zones.geojson`. Run `python -m eval.check_manifest` after each batch; it catches missing files, unknown zones, a found time before the lost window, and pairs with only one side.

After the first real run, `--write-weights` installs the calibration, and once trained weights arrive from the compute bucket, rerun for the before/after table.
