import hashlib
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from PIL import Image

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",  # Canonicalize to .jpg even for image/jpeg or .jpeg
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

ALLOWED_EXTENSIONS = set(ALLOWED_IMAGE_TYPES.values())



THUMB_SIZE = (300, 300)

def get_thumb_path(img_path: Path, pic_root: Path, thumb_root: Path) -> Path:
    rel_path = img_path.relative_to(pic_root)
    # Make extension explicit (e.g., .jpg for all thumbnails)
    return thumb_root / rel_path.with_suffix(rel_path.suffix + ".jpg")

def ensure_thumbnail(img_path: Path, pic_root: Path, thumb_root: Path) -> Path:
    thumb_path = get_thumb_path(img_path, pic_root, thumb_root)
    if thumb_path.exists():
        return thumb_path

    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(img_path) as im:
        im.thumbnail(THUMB_SIZE)
        im.convert("RGB").save(thumb_path, "JPEG", quality=85)

    return thumb_path


def is_allowed_mime(mime: str) -> bool:
    return mime in ALLOWED_IMAGE_TYPES


def is_allowed_ext(ext: str) -> bool:
    return ext.lower() in ALLOWED_EXTENSIONS


def get_host_from_url(url: str) -> str:
    return urlparse(url).hostname or "unknown-host"


def get_storage_path(root: Path, client_ip: str) -> Path:
    safe_ip = client_ip.replace(":", "-")
    today = date.today().isoformat()
    return root / safe_ip / today


def sanitize_filename(original: str) -> str:
    base = os.path.basename(original)
    base = re.sub(r"[^\w\d_.()-]", "_", base)
    base = base.lower()
    stem, ext = os.path.splitext(base)
    return f"{stem}-{uuid4()}{ext}"


def file_hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
