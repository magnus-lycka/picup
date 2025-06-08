from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pathlib import Path
import aiofiles
import httpx
import os
from uuid import uuid4

from utils import (
    get_storage_path,
    sanitize_filename,
    file_hash_bytes,
    ALLOWED_IMAGE_TYPES,
    ALLOWED_EXTENSIONS,
    is_allowed_mime,
    is_allowed_ext,
    get_host_from_url,
)
from db import HashDB


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("lifespan... before yield")
    await scan_files()
    yield
    print("lifespan... before yield")


# Configuration from environment
PIC_ROOT = Path(os.getenv("PIC_ROOT", "pics"))
DB_PATH = Path(os.getenv("DB_PATH", "image_hashes.db"))

PIC_ROOT.mkdir(parents=True, exist_ok=True)
hash_db = HashDB(DB_PATH)

app = FastAPI(lifespan=lifespan)


def render_form(message: str = "", image_url: str = "", is_error: bool = False) -> str:
    bg_color = "#ffdddd" if is_error else "#ddffdd" if message else "transparent"
    message_block = f"""
        <div style='background:{bg_color}; padding:1em; border-radius:5px; margin-top:1em;'>
            <h3>{message}</h3>
            {f"<img src='/files/{image_url}' style='max-width:400px'>" if image_url else ""}
        </div>
    """ if message else ""

    return f"""
    <html>
    <head><title>Upload Image</title></head>
    <body>
        <h1>Upload Image</h1>
        <form action="/upload-file" enctype="multipart/form-data" method="post">
            <input name="file" type="file">
            <input type="submit" value="Upload File">
        </form>
        <br>
        <h2>Or provide a URL</h2>
        <form action="/upload-url" method="post">
            <input name="url" type="text" size="60" placeholder="https://example.com/image.jpg">
            <input type="submit" value="Fetch and Upload">
        </form>
        {message_block}
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def upload_form():
    return render_form()


@app.post("/upload-file")
async def upload_file(request: Request, file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if not is_allowed_mime(content_type):
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(render_form(f"Unsupported content type: {content_type}", is_error=True), status_code=400)
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {content_type}")

    content = await file.read()
    file_hash = file_hash_bytes(content)
    existing = hash_db.get(file_hash)

    if existing:
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(render_form("Image exists:", existing), status_code=409)
        return JSONResponse({"error": "Image already exists", "path": existing}, status_code=409)

    ext = ALLOWED_IMAGE_TYPES[content_type]
    client_ip = request.client.host or "unknown"
    target_dir = get_storage_path(PIC_ROOT, client_ip)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(file.filename)
    safe_name = Path(safe_name).stem + ext  # normalize extension
    full_path = target_dir / safe_name

    async with aiofiles.open(full_path, "wb") as f:
        await f.write(content)

    rel_path = str(full_path.relative_to(PIC_ROOT))
    hash_db.add(file_hash, rel_path)

    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(render_form("Image stored:", rel_path))
    return JSONResponse({"status": "stored", "path": rel_path})


@app.post("/upload-url")
async def upload_url(request: Request, url: str = Form(...)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    content_type = response.headers.get("content-type", "")
    if not is_allowed_mime(content_type):
        raise HTTPException(
            status_code=400, detail=f"Unsupported content type: {content_type}"
        )
    ext = ALLOWED_IMAGE_TYPES[content_type]

    content = response.content
    file_hash = file_hash_bytes(content)
    existing = hash_db.get(file_hash)

    if existing:
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(render_form("Image exists:", existing), status_code=409)
        return JSONResponse(
            {"error": "Image already exists", "path": existing}, status_code=409
        )

    host = get_host_from_url(url)
    target_dir = get_storage_path(PIC_ROOT, host)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"url-upload-{uuid4()}{ext}"
    full_path = target_dir / safe_name
    async with aiofiles.open(full_path, "wb") as f:
        await f.write(content)

    rel_path = str(full_path.relative_to(PIC_ROOT))
    hash_db.add(file_hash, rel_path)

    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(render_form("Image stored:", rel_path))
    return JSONResponse({"status": "stored", "path": rel_path})


@app.get("/files/{full_path:path}")
async def get_file(full_path: str):
    file_path = PIC_ROOT / full_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


async def scan_files():
    print("🔍 Scanning for unregistered image files...")
    count_added = 0
    for file in PIC_ROOT.rglob("*"):
        print('.', sep='', end='', flush=True)
        if file.is_file():
            if not is_allowed_ext(file.suffix):
                continue
            rel_path = str(file.relative_to(PIC_ROOT))
            try:
                async with aiofiles.open(file, "rb") as f:
                    content = await f.read()
                    hash_val = file_hash_bytes(content)
                    if found_path := hash_db.get(hash_val):
                        if found_path != rel_path:
                            print(f"\n{rel_path} is identical to {found_path}")
                    else:
                        hash_db.add(hash_val, rel_path)
                        count_added += 1
            except Exception as e:
                print(f"⚠️ Error reading {file}: {e}")
    print(f"✅ Scan complete. {count_added} new entries added.")
