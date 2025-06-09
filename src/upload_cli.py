#!/usr/bin/env python3
import argparse
import os

import filetype
import httpx

allowed_mime_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def is_image(file_path: str) -> bool:
    kind = filetype.guess(file_path)
    return kind is not None and kind.mime in allowed_mime_types

def guess_mime(file_path: str) -> str:
    kind = filetype.guess(file_path)
    return kind.mime

def upload_file(file_path: str, server_url: str) -> httpx.Response:
    """Upload a file to the FastAPI /upload-file endpoint using httpx."""
    file_name = os.path.basename(file_path)
    mime = guess_mime(file_path)

    with open(file_path, "rb") as f:
        files = {'file': (file_name, f, mime)}
        with httpx.Client() as client:
            response = client.post(f"{server_url.rstrip('/')}/upload-file", files=files)
    return response


def collect_files(path: str, recursive: bool) -> list[str]:
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "site-packages", "node_modules", ".idea", ".vscode"}
    """Get all file paths under a directory (optionally recursive), or just return the file."""
    if os.path.isfile(path):
        return [path]
    elif os.path.isdir(path):
        collected = []
        if recursive:
            for root, _, files in os.walk(path):
                if any(skip in root.split(os.sep) for skip in skip_dirs):
                    continue
                for file in files:
                    full_path = os.path.join(root, file)
                    if os.path.isfile(full_path):
                        collected.append(full_path)
        else:
            for file in os.listdir(path):
                full_path = os.path.join(path, file)
                if os.path.isfile(full_path):
                    collected.append(full_path)
        return collected
    else:
        raise ValueError(f"Not a file or directory: {path}")

def main():
    parser = argparse.ArgumentParser(description="Upload images to FastAPI server")
    parser.add_argument("paths", nargs="+", help="File(s) or directory/ies to upload from")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into directories")
    parser.add_argument("--server", default="http://localhost:8000", help="FastAPI base URL")
    args = parser.parse_args()
    args.server = args.server.rstrip('/')

    all_files = []

    for path in args.paths:
        try:
            files = collect_files(path, args.recursive)
            all_files.extend(files)
        except ValueError as e:
            print(f"⚠️ {e}")

    if not all_files:
        print("No files found.")
        return

    for file_path in all_files:
        if not is_image(file_path):
            print(f"⏭️ Skipping non-image: {file_path}")
            continue

        print(f"📤 Uploading: {file_path}")
        try:
            resp = upload_file(file_path, args.server)
            status = f"{resp.status_code} {resp.reason_phrase}"
            if resp.status_code < 400:
                print(f"✅ Response: {status}")
            else:
                print(f"❌ Response: {status}")
                print(resp.text)
        except httpx.HTTPError as e:
            print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    main()
