import os
import pickle
from pathlib import Path

import faiss
import numpy as np
import torch
from PIL import Image
from tqdm import tqdm
from transformers import CLIPModel, CLIPProcessor
from utils import catch_pil_warnings

# Config
PIC_ROOT = Path(os.getenv("PIC_ROOT", "~/Pictures")).expanduser()
INDEX_PATH = Path("clip_index.faiss")
META_PATH = Path("clip_metadata.pkl")

# Load CLIP model
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)


# Image transform
def preprocess_image(image_path):
    with catch_pil_warnings(image_path.name):
       image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    return {k: v.to(device) for k, v in inputs.items()}


# Index setup
vectors = []
paths = []

print(f"🔍 Scanning {PIC_ROOT} for images...")
for image_path in tqdm(list(PIC_ROOT.rglob("*"))):
    if not image_path.is_file():
        continue
    try:
        inputs = preprocess_image(image_path)
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
            image_features /= image_features.norm(dim=-1, keepdim=True)
        vectors.append(image_features.cpu().numpy().astype("float32"))
        paths.append(str(image_path.relative_to(PIC_ROOT)))
    except Exception as e:
        print(f"⚠️ Skipped {image_path.name}: {e}")

if not vectors:
    print("❌ No valid images found.")
    exit(1)

print(f"🧠 Building FAISS index for {len(vectors)} images...")
index = faiss.IndexFlatIP(
    512
)  # cosine similarity via inner product on normalized vectors
index.add(np.vstack(vectors))

# Save
faiss.write_index(index, str(INDEX_PATH))
with open(META_PATH, "wb") as f:
    pickle.dump(paths, f)

print("✅ Indexing complete.")
