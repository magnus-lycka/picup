import hashlib
import os
import re
import warnings
from contextlib import contextmanager
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


THUMB_SIZE = (250, 250)


@contextmanager
def catch_pil_warnings(filename: str):
    with warnings.catch_warnings(record=True) as wlist:
        warnings.simplefilter("always", Image.DecompressionBombWarning)
        warnings.simplefilter("always", UserWarning)

        yield  # Run your Pillow code inside here

        for w in wlist:
            print(
                f"⚠️ Warning while processing {filename}: {w.message} ({w.category.__name__})"
            )


def get_thumb_path(img_path: Path, pic_root: Path, thumb_root: Path) -> Path:
    rel_path = img_path.relative_to(pic_root)
    return thumb_root / rel_path.with_suffix(rel_path.suffix + ".png")


def ensure_thumbnail(img_path: Path, pic_root: Path, thumb_root: Path) -> Path:
    thumb_path = get_thumb_path(img_path, pic_root, thumb_root)
    if thumb_path.exists():
        return thumb_path

    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    with catch_pil_warnings(img_path.name):
        with Image.open(img_path) as im:
            im.thumbnail(THUMB_SIZE)
            im.save(thumb_path, "PNG", optimize=True)

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
