from pathlib import Path
from PIL import Image, PngImagePlugin

root = Path(".")  # при необходимости укажите папку с PNG
paths = list(root.rglob("*.png"))

for p in paths:
    img = Image.open(p)
    # Пустые метаданные => без iCCP и прочего мусора
    meta = PngImagePlugin.PngInfo()
    # Сохраняем с исходным режимом и альфой
    img.save(p, pnginfo=meta, optimize=True)
    print("fixed:", p)
