"""Pictures of your desk: one kept with each save, and one taken after a resume to dim
behind your note. JPEGs, small, and only ever on this PC (data/shots)."""
import base64
import io
import time
from pathlib import Path

from PIL import ImageGrab

import store

SHOTS = store.SHOTS_DIR


def grab(width=None, bbox=None):
    """The screen right now (bbox: one monitor's (left, top, right, bottom); default the main one),
    scaled down to `width` pixels across if given (opening the bar skips that: it's done later,
    only if you actually save)."""
    image = ImageGrab.grab(bbox=bbox, all_screens=bool(bbox))
    if width:
        image.thumbnail((width, width))
    return image


def keep(image, park_name):
    """Save the picture for a park; returns its file name ('' if there's no picture)."""
    if image is None:
        return ""
    SHOTS.mkdir(parents=True, exist_ok=True)
    name = f"{store.slug(park_name)}-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    image = image.copy()
    image.thumbnail((1280, 1280))
    image.convert("RGB").save(SHOTS / name, "JPEG", quality=78)
    return name


def data_url(image=None, file=""):
    """A picture as a data: URL the overlay page can show, from an image or a saved file name."""
    if file:
        path = SHOTS / file
        if not path.exists():
            return ""
        raw = Path(path).read_bytes()
    elif image is not None:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=70)
        raw = buffer.getvalue()
    else:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
