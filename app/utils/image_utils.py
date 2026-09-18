from io import BytesIO
import os
import uuid
from PIL import Image, ImageOps
from pathlib import Path
from app.core.config import settings


def process_image(content: bytes, directory: str, size: tuple[int, int]) -> str:
    """Crop/convert an uploaded image and write it to `directory`.

    Returns the public URL of the stored file. Settings are read on every call
    (rather than at import time) so tests can point the directory at a tmp path.
    """
    upload_dir = Path(directory)

    with Image.open(BytesIO(content)) as original:
        img = ImageOps.exif_transpose(original)

        img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = upload_dir / filename

        upload_dir.mkdir(parents=True, exist_ok=True)

        img.save(filepath, "JPEG", quality=85, optimize=True)

    return f"{directory}/{filename}"


def process_product_image(content: bytes) -> str:
    return process_image(content, settings.PRODUCT_IMAGE_UPLOAD_DIRECTORY, (512, 512))


def process_category_image(content: bytes) -> str:
    # 16:9 to match the aspect ratio of the category tiles in the frontend
    return process_image(content, settings.CATEGORY_IMAGE_UPLOAD_DIRECTORY, (800, 450))


def delete_image_file(url: str) -> None:
    """Best-effort removal of a previously stored image."""
    if url and os.path.exists(url):
        os.remove(url)
