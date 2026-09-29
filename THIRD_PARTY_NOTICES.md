# Third-party notices

Reunite uses the following. Licenses are those of the upstream projects at the time of writing; check them before you distribute.

## Models and data

| Component | License | Use |
|---|---|---|
| Ultralytics YOLO11n | **AGPL-3.0** (Ultralytics also sells an enterprise license) | object detection. If you distribute Reunite or run it as a network service for others, the AGPL applies to code that uses it; get the enterprise license or swap the detector |
| OpenAI CLIP ViT-B/32 weights, via `open_clip_torch` | MIT | image and text embeddings, zero-shot categories |
| `sentence-transformers/all-MiniLM-L6-v2` | Apache-2.0 | text similarity |
| RapidOCR (PaddleOCR models, ONNX) | Apache-2.0 | reading brand text and roll numbers |
| spaCy | MIT | tokenization and the EntityRuler over our gazetteers |
| Open Images V7 (validation photos used for seed and synthetic evaluation, and by the training notebooks) | annotations CC BY 4.0; images CC BY 2.0 (per image; see the source ids in `data/seed/photos.csv`) | demo photos; not redistributed in this repo |
| Natural Earth II shaded relief (the Earth texture in `prototype/globe-hero`) | public domain | landing-page globe |

## Libraries

FastAPI, Starlette, Pydantic, SQLAlchemy, Alembic, psycopg, uvicorn, PyJWT, pywebpush (MPL-2.0), NumPy, scikit-learn, OpenCV, Pillow, rapidfuzz (MIT), PyTorch (BSD-3), pgvector (PostgreSQL license, optional). Front-end: CesiumJS (Apache-2.0; the ops view), three.js (MIT; the landing globe), Vite (MIT).

## Reserved for the ops view

* **CesiumJS** (Apache-2.0), used for the 3D campus view in the front end.
* Shader attribution for the optional night-vision and thermal modes is reserved here. If they are ported from `bilawalsidhu/gods-eye-view` (MIT), add its copyright and permission notice on this line before shipping: `TODO(attribution): gods-eye-view, MIT`.
