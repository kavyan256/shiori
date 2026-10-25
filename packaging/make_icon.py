"""Draw Shiori's icon (the blue 'S' from the tray) as a multi-size .ico for Shiori.exe."""
from pathlib import Path

from PIL import Image, ImageDraw

img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rounded_rectangle((16, 16, 240, 240), radius=60, fill="#7aa2f7")
draw.text((128, 132), "S", fill="#15171c", font_size=150, anchor="mm")
out = Path(__file__).parent / "shiori.ico"
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon:", out)
