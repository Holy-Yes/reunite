# Eval report 2026-09-26-synthetic

**Pair set: SYNTHETIC pairs (optimistic).** 112 lost reports, each ranked against the whole found pool.

## Headline

| Metric | Value | Target |
|---|---|---|
| Precision@1 | 0.848 | 0.6 (meets target) |
| Precision@5 | 0.964 | 0.85 (meets target) |
| Precision@10 | 1.000 | |
| Recall@5 (candidate generation) | 0.893 | |
| MRR | 0.900 | |
| mAP | 0.900 | (equals MRR: one true match per query) |
| ECE (calibrated, held-out 30%) | 0.1078 | lower is better |

Uncalibrated (hand-set weights read as probabilities) ECE on the same held-out pairs: 0.3265.

## Ablation (which evidence carries the ranking)

| Feature set | P@1 | P@5 |
|---|---|---|
| image only | 0.339 | 0.696 |
| text only | 0.429 | 0.804 |
| + attributes | 0.679 | 0.946 |
| + text-to-photo | 0.670 | 0.946 |
| + location and time | 0.848 | 0.964 |

## Per category

| Category | P@1 | P@5 | n |
|---|---|---|---|
| backpack | 0.80 | 0.90 | 10 |
| book | 1.00 | 1.00 | 7 |
| bottle | 0.90 | 1.00 | 10 |
| calculator | 0.62 | 1.00 | 8 |
| charger | 1.00 | 1.00 | 3 |
| earbuds | 0.50 | 0.75 | 4 |
| headphones | 0.90 | 1.00 | 10 |
| id_card | 0.75 | 1.00 | 4 |
| keys | 0.75 | 1.00 | 4 |
| laptop | 1.00 | 1.00 | 10 |
| notebook | 1.00 | 1.00 | 3 |
| phone | 0.90 | 1.00 | 10 |
| power_bank | 1.00 | 1.00 | 3 |
| spectacles | 0.67 | 0.83 | 6 |
| tablet | 1.00 | 1.00 | 5 |
| umbrella | 1.00 | 1.00 | 2 |
| wallet | 1.00 | 1.00 | 3 |
| watch | 0.70 | 0.90 | 10 |

## Reliability (10 bins, held-out)

| Bin | Confidence | Accuracy | n |
|---|---|---|---|
| 0 | 0.02 | 0.00 | 307 |
| 1 | 0.15 | 0.00 | 50 |
| 2 | 0.23 | 0.00 | 20 |
| 3 | 0.34 | 0.00 | 18 |
| 4 | 0.46 | 0.00 | 10 |
| 5 | 0.56 | 0.06 | 17 |
| 6 | 0.65 | 0.00 | 7 |
| 7 | 0.74 | 0.38 | 8 |
| 8 | 0.85 | 0.33 | 9 |
| 9 | 0.96 | 0.96 | 28 |

## Notes

Synthetic pairs are OPTIMISTIC: both views come from one public photo and the text is generated from the same labels. Do not present these numbers as real-world performance.

Stages: `{"detector": "yolo11n (COCO) + CLIP zero-shot for other classes", "clip": "open_clip ViT-B/32 (openai) on mps", "attribute_heads": "CLIP zero-shot prompts", "ocr": "rapidocr-onnxruntime", "text_embedder": "MiniLM-L6 on mps"}`
