


from io import BytesIO
import uuid
from PIL import Image, ImageOps
from pathlib import Path
from app.core.config import settings

PROFILE_PICS_DIR = Path(settings.PRODUCT_IMAGE_UPLOAD_DIRECTORY)


def process_product_image(content: bytes) -> str:
    with Image.open(BytesIO(content)) as original:
        img = ImageOps.exif_transpose(original)

        img = ImageOps.fit(img, (512, 512), method=Image.Resampling.LANCZOS)

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = PROFILE_PICS_DIR / filename

        PROFILE_PICS_DIR.mkdir(parents=True, exist_ok=True)

        img.save(filepath, "JPEG", quality=85, optimize=True)

    return f"{settings.PRODUCT_IMAGE_UPLOAD_DIRECTORY}/{filename}"