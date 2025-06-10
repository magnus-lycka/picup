import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import aiofiles
import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image
import imagehash
from io import BytesIO

from db import HashDB
from utils import (ALLOWED_IMAGE_TYPES, ensure_thumbnail, file_hash_bytes,
                   get_host_from_url, get_storage_path, is_allowed_ext,
                   is_allowed_mime, sanitize_filename)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("lifespan... before yield")
    await scan_files()
    yield
    print("lifespan... before yield")


# Configuration from environment
PIC_ROOT = Path(os.getenv("PIC_ROOT", "~/Pictures")).expanduser()
DB_PATH = Path(os.getenv("DB_PATH", "image_hashes.db")).expanduser()
THUMB_ROOT = Path(os.getenv("THUMB_ROOT", ".thumbs"))
THUMB_ROOT.mkdir(parents=True, exist_ok=True)

PIC_ROOT.mkdir(parents=True, exist_ok=True)
hash_db = HashDB(DB_PATH)

app = FastAPI(lifespan=lifespan)


def render_form(message: str = "", image_url: str = "", is_error: bool = False) -> str:
    bg_color = "#ffdddd" if is_error else "#ddffdd" if message else "transparent"
    message_block = f"""
        <div style='background:{bg_color}; padding:1em; border-radius:5px; margin-top:1em;'>
            <h3>{message}</h3>
            {f"<a href='/browse/{image_url}'><img src='/files/{image_url}' style='max-width:400px'></a>" if image_url else ""}
        </div>
    """ if message else ""

    return f"""
    <html>
    <head><title>Upload Image</title></head>
    <body>
        <a href="/browse">Browse Images</a>
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


def build_nav_links(current_path: Path, base_url: str = "/browse") -> dict:
    parts = list(current_path.parts)
    parent = current_path.parent if current_path != Path() else None
    breadcrumbs = [("root", f"{base_url}/")]

    for i in range(len(parts)):
        part_path = Path(*parts[:i+1])
        breadcrumbs.append((parts[i], f"{base_url}/{part_path.as_posix()}"))

    return {
        "current": str(current_path),
        "parent": f"{base_url}/{parent.as_posix()}" if parent else None,
        "root": f"{base_url}/",
        "upload": "/",
        "breadcrumbs": breadcrumbs
    }


def nav_links_html(nav: dict, prev: str = None, next_: str = None) -> str:
    links = [
        f"<a href='{nav['upload']}'>Upload Form</a>"]
    if prev:
        links.append(f"<a href='{prev}'>Previous</a>")
    if next_:
        links.append(f"<a href='{next_}'>Next</a>")

    breadcrumbs = " / ".join(f"<a href='{link}'>{name}</a>" for name, link in nav["breadcrumbs"])
    return f"<div style='margin-bottom:10px'><strong>Path:</strong> {breadcrumbs}</div>" + \
           "<div style='margin-bottom:20px'>" + " | ".join(links) + "</div>"


@app.get("/browse/{path:path}", response_class=HTMLResponse)
@app.get("/browse", response_class=HTMLResponse)
async def browse_path(path: str = ""):
    target_path = (PIC_ROOT / path).resolve()
    if not target_path.exists() or not str(target_path).startswith(str(PIC_ROOT.resolve())):
        raise HTTPException(status_code=404, detail="Not found")

    rel_path = Path(path)
    nav = build_nav_links(rel_path)

    if target_path.is_dir():
        # List directories and files
        entries = sorted(target_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]

        content = f"<h2>Directory: /{rel_path}</h2>"
        content += nav_links_html(nav)

        if dirs:
            content += "<h3>Subdirectories:</h3><ul>"
            for d in dirs:
                p = rel_path / d.name
                content += f"<li><a href='/browse/{quote(p.as_posix())}'>{d.name}</a></li>"
            content += "</ul>"

        if files:
            content += "<h3>Files:</h3><div style='display:flex; flex-wrap:wrap;'>"
            for f in files:
                p = rel_path / f.name
                thumb_url = f"/thumbs/{quote(p.as_posix())}"
                file_url = f"/browse/{quote(p.as_posix())}"
                content += (
                    f"<div style='margin:5px; text-align:center'>"
                    f"<a href='{file_url}'><img src='{thumb_url}' style='max-width:150px; max-height:150px; display:block; margin:auto'></a>"
                    f"</div>"
                )
            content += "</div>"
        return HTMLResponse(f"<html><body>{content}</body></html>")

    elif target_path.is_file():
        # Single file view
        parent_dir = target_path.parent
        siblings = sorted(parent_dir.iterdir(), key=lambda p: p.name)
        index = [p.name for p in siblings].index(target_path.name)
        prev_link = next_link = None

        if index > 0:
            prev_rel = rel_path.parent / siblings[index - 1].name
            prev_link = f"/browse/{quote(prev_rel.as_posix())}"
        if index < len(siblings) - 1:
            next_rel = rel_path.parent / siblings[index + 1].name
            next_link = f"/browse/{quote(next_rel.as_posix())}"

        image_path = f"/files/{quote(rel_path.as_posix())}"

        content = f"<h2>Viewing: /{rel_path}</h2>"
        content += nav_links_html(nav, prev_link, next_link)
        content += f"<div><img src='{image_path}' style='max-width:100%; max-height:90vh'></div>"
        content += "<div style='margin-top:1em'>"
        content += f"<a href='/similar/{rel_path}'>🔍 Find similar images</a>"
        content += "</div>"
        

        return HTMLResponse(f"<html><body>{content}</body></html>")

    raise HTTPException(status_code=400, detail="Unsupported path")


@app.get("/thumbs/{path:path}")
async def get_thumbnail(path: str):
    img_path = (PIC_ROOT / path).resolve()
    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    thumb_path = ensure_thumbnail(img_path, PIC_ROOT, THUMB_ROOT)
    return FileResponse(thumb_path)


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
            return HTMLResponse(render_form("Image exists:", existing, is_error=True), status_code=409)
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
    with Image.open(BytesIO(content)) as im:
        phash = str(imagehash.phash(im))
    hash_db.add(file_hash, rel_path, phash)
    
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(render_form("Image stored:", rel_path))
    return JSONResponse({"status": "stored", "path": rel_path})


@app.post("/upload-url")
async def upload_url(request: Request, url: str = Form(...)):
    accept_html = "text/html" in request.headers.get("accept", "")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as e:
        if accept_html:
            return HTMLResponse(render_form(f"Failed to fetch URL: {e}", is_error=True), status_code=400)
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    content_type = response.headers.get("content-type", "")
    if not is_allowed_mime(content_type):
        if accept_html:
            return HTMLResponse(render_form(f"Unsupported content type: {content_type}", is_error=True), status_code=400)
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {content_type}")

    ext = ALLOWED_IMAGE_TYPES[content_type]
    content = response.content
    file_hash = file_hash_bytes(content)
    existing = hash_db.get(file_hash)

    if existing:
        if accept_html:
            return HTMLResponse(render_form("Image exists:", existing, is_error=True), status_code=409)
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
    with Image.open(BytesIO(content)) as im:
        phash = str(imagehash.phash(im))
    hash_db.add(file_hash, rel_path, phash)

    if accept_html:
        return HTMLResponse(render_form("Image stored:", rel_path))
    return JSONResponse({"status": "stored", "path": rel_path})


@app.get("/files/{full_path:path}")
async def get_file(full_path: str):
    file_path = PIC_ROOT / full_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.get("/similar/{path:path}", response_class=HTMLResponse)
async def find_similar_to(path: str):
    img_path = (PIC_ROOT / path).resolve()
    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    rel_path = str(Path(path))
    phash_str = hash_db.get_phash_by_path(rel_path)
    if not phash_str:
        raise HTTPException(status_code=404, detail="No perceptual hash available for this image")

    query_hash = imagehash.hex_to_hash(phash_str)

    results = []
    for other_phash_str, other_rel in hash_db.get_all_phashes():
        if other_rel == rel_path:
            continue
        dist = query_hash - imagehash.hex_to_hash(other_phash_str)
        if dist <= 10:  # adjustable threshold
            results.append((dist, other_rel))

    results.sort()

    content = f"<h2>Similar to: /{rel_path}</h2><div style='margin-bottom:1em'><a href='/browse/{rel_path}'>Back to image</a></div>"
    for dist, match_path in results:
        content += f"<div style='margin:10px'><strong>Distance {dist}</strong><br><a href='/browse/{match_path}'><img src='/thumbs/{match_path}' style='max-height:150px'></a><br>{match_path}</div>"

    return HTMLResponse(f"<html><body>{content}</body></html>")



async def scan_files():
    print("🔍 Scanning for unregistered image files...")
    count_added = 0
    count_found = 0
    for file in PIC_ROOT.rglob("*"):
        count_found += 1
        print(f"\r{count_found}", sep='', end=' ', flush=True)
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
                        with Image.open(BytesIO(content)) as im:
                            phash = str(imagehash.phash(im))
                        hash_db.add(hash_val, rel_path, phash)
                        count_added += 1
            except Exception as e:
                print(f"⚠️ Error reading {file}: {e}")
    print(f"✅ Scan complete. {count_added} new entries added.")
