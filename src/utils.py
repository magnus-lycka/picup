import hashlib
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",  # Canonicalize to .jpg even for image/jpeg or .jpeg
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

ALLOWED_EXTENSIONS = set(ALLOWED_IMAGE_TYPES.values())


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
