"""Uploads: strip EXIF, resize, make the blurred public copy (or a solid plate for redacted ID cards)."""
from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..config import get_settings
from ..errors import ApiError
from ..models import ItemImage

MAX_BYTES = 10 * 1024 * 1024
MAX_SIDE = 1600
PUBLIC_WIDTH = 480
BLUR_RADIUS = 14  # heavy but recognisable: shape and colour survive, text and marks do not


def media_root() -> Path:
    root = get_settings().media_path
    for sub in ("incoming", "original", "public"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def validate_upload(data: bytes) -> None:
    if not data:
        raise ApiError(422, "invalid_image", "That file is empty.")
    if len(data) > MAX_BYTES:
        raise ApiError(413, "image_too_large", "Photos must be under 10 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception as e:  # noqa: BLE001
        raise ApiError(422, "invalid_image", "That doesn't look like a photo we can read.") from e


def open_upload(data: bytes) -> Image.Image:
    """Decode, apply the EXIF rotation, and drop all metadata (location, device, time)."""
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        clean = Image.new("RGB", im.size)
        clean.paste(im)
    return clean


def stash_incoming(data: bytes) -> tuple[str, str]:
    """Write raw upload bytes to incoming/ and return (relative path, sha256). The ingest job finishes the work."""
    validate_upload(data)
    name = f"{uuid.uuid4().hex}.bin"
    (media_root() / "incoming" / name).write_bytes(data)
    return f"incoming/{name}", hashlib.sha256(data).hexdigest()


def blurred(im: Image.Image) -> Image.Image:
    w = PUBLIC_WIDTH
    h = max(int(im.height * w / im.width), 1)
    small = im.resize((w, h), Image.LANCZOS)
    return small.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))


def redaction_plate(size: tuple[int, int] = (PUBLIC_WIDTH, PUBLIC_WIDTH * 3 // 4)) -> Image.Image:
    plate = Image.new("RGB", size, "#F5F3F0")
    d = ImageDraw.Draw(plate)
    d.text((size[0] // 2, size[1] // 2), "ID card. Name and number hidden.", fill="#3A3A3A", anchor="mm")
    return plate


def process_image(row: ItemImage, redact: bool = False) -> None:
    """Turn an `incoming/` upload into `original/{id}.jpg` and `public/{id}.jpg`, and fill width, height and sha."""
    root = media_root()
    src = root / row.path
    if row.path.startswith("incoming/") and src.exists():
        data = src.read_bytes()
        im = open_upload(data)
        rel = f"original/{row.id}.jpg"
        im.save(root / rel, "JPEG", quality=90)
        src.unlink(missing_ok=True)
        row.path = rel
        row.width, row.height = im.size
    else:
        im = Image.open(root / row.path).convert("RGB")
    write_public(row, im, redact)


def write_public(row: ItemImage, im: Image.Image, redact: bool) -> None:
    rel = f"public/{row.id}.jpg"
    (redaction_plate() if redact else blurred(im)).save(media_root() / rel, "JPEG", quality=80)
    row.public_path = rel


def load_original(row: ItemImage) -> Image.Image:
    return Image.open(media_root() / row.path).convert("RGB")


def delete_files(row: ItemImage) -> None:
    for rel in (row.path, row.public_path):
        if rel:
            (media_root() / rel).unlink(missing_ok=True)
