from datetime import datetime
import random
import string


def generate_sku() -> str:
    """
    Generate SKU like: ITEM-20260830-A7K9
    Format: [CATEGORY]-[YYYYMMDD]-[RANDOM]
    """
    timestamp = datetime.now().strftime("%Y%m%d")
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"ITEM-{timestamp}-{random_suffix}"
