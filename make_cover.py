"""Generate the podcast cover art. Run once; commit the PNG.

Kept out of the daily workflow deliberately — the runner shouldn't need Pillow
just to redraw a static image. Re-run by hand if you change the wording.
"""
import os

from PIL import Image, ImageDraw, ImageFont

SIZE = 1600
BG = (22, 24, 29)
CREAM = (244, 241, 234)
ACCENT = (224, 139, 95)
MUTED = (154, 160, 168)

TITLE = ("DAILY", "WRAP")
SUBTITLE = "WORLD  ·  MARKETS  ·  TECHNOLOGY"
FOOTER = "WEEKDAY MORNINGS"

FONT_DIRS = [r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"]
SERIF = ["georgiab.ttf", "timesbd.ttf", "DejaVuSerif-Bold.ttf", "Georgia Bold.ttf"]
SANS = ["seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"]


def find_font(candidates, size):
    for d in FONT_DIRS:
        for name in candidates:
            path = os.path.join(d, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def centered(draw, text, font, y, fill, tracking=0):
    if tracking:
        widths = [draw.textlength(c, font=font) for c in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = (SIZE - total) / 2
        for c, w in zip(text, widths):
            draw.text((x, y), c, font=font, fill=fill)
            x += w + tracking
        return
    w = draw.textlength(text, font=font)
    draw.text(((SIZE - w) / 2, y), text, font=font, fill=fill)


def main():
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)

    # Subtle inset frame — gives the tile an edge at small sizes.
    d.rectangle([70, 70, SIZE - 70, SIZE - 70], outline=(44, 48, 56), width=3)

    title_font = find_font(SERIF, 300)
    sub_font = find_font(SANS, 46)
    foot_font = find_font(SANS, 40)

    centered(d, TITLE[0], title_font, 470, CREAM)
    centered(d, TITLE[1], title_font, 790, ACCENT)

    d.line([(SIZE / 2 - 190, 1145), (SIZE / 2 + 190, 1145)], fill=(74, 80, 90), width=3)
    centered(d, SUBTITLE, sub_font, 1200, MUTED, tracking=3)
    centered(d, FOOTER, foot_font, 300, ACCENT, tracking=8)

    img.save("cover.png", "PNG", optimize=True)
    print(f"wrote cover.png ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
