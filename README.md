# picup
Picture Upload with duplicate detection

Define these variables:

  PIC_ROOT = Path(os.getenv("PIC_ROOT", "pics"))
  DB_PATH = Path(os.getenv("DB_PATH", "image_hashes.db"))

Run:

  uvicorn main:app

Or during dev:

  uvicorn main:app --reload
