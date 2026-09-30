#!/bin/sh
# Render build step (runs from the repo root). CPU-only torch first: the default PyPI wheel drags in
# ~3GB of CUDA libraries that Render never uses.
set -e
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r backend/requirements.txt
python -m spacy download en_core_web_sm
python scripts/download_weights.py
