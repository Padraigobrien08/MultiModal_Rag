#!/usr/bin/env python3
"""Generate the demo-mode screenshot fixtures under demo/frames/.

These are *mock* product screenshots for a fictional "Acme" SaaS — they exist so
the no-API-key demo can render cited steps with visuals without shipping real
customer video frames. The PNGs are committed; you only need to re-run this if
you want to change what the demo shows.

    python demo/generate_frames.py

Requires Pillow (already a transitive dev dependency; `pip install pillow`).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).parent / "frames"

W, H = 1024, 576
BG = (10, 12, 11)
PANEL = (20, 23, 22)
SIDEBAR = (16, 18, 17)
BORDER = (38, 42, 40)
TEXT = (222, 226, 224)
MUTED = (128, 134, 130)
GREEN = (0, 255, 136)
GREEN_DIM = (0, 90, 52)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a system sans-serif, falling back to Pillow's bitmap default."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def render(filename: str, breadcrumb: str, menu: list[str], active: str,
           heading: str, highlight_label: str, caption: str) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_title = _font(22, bold=True)
    f_body = _font(18)
    f_small = _font(15)
    f_chip = _font(13, bold=True)

    # ── window chrome ──────────────────────────────────────────────────────
    d.rectangle([0, 0, W, 44], fill=PANEL)
    d.line([0, 44, W, 44], fill=BORDER)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([24 + i * 22, 16, 36 + i * 22, 28], fill=c)
    d.text((110, 14), breadcrumb, font=f_small, fill=MUTED)

    # ── sidebar ────────────────────────────────────────────────────────────
    d.rectangle([0, 45, 232, H], fill=SIDEBAR)
    d.line([232, 45, 232, H], fill=BORDER)
    d.text((28, 70), "ACME", font=f_title, fill=GREEN)
    y = 130
    for item in menu:
        is_active = item == active
        if is_active:
            _rounded(d, [16, y - 8, 216, y + 26], 8, fill=(24, 40, 32))
            d.rectangle([16, y - 8, 20, y + 26], fill=GREEN)
        d.text((36, y), item, font=f_body, fill=(TEXT if is_active else MUTED))
        y += 48

    # ── main panel ─────────────────────────────────────────────────────────
    d.text((272, 78), heading, font=f_title, fill=TEXT)
    _rounded(d, [272, 128, W - 40, H - 120], 14, fill=PANEL, outline=BORDER, width=1)

    # a couple of muted "rows"
    for i in range(2):
        ry = 158 + i * 52
        d.text((296, ry), "•", font=f_body, fill=MUTED)
        d.line([320, ry + 12, W - 90, ry + 12], fill=BORDER, width=8)

    # highlighted call-to-action element
    hy = 158 + 2 * 52 + 12
    _rounded(d, [296, hy, 296 + 300, hy + 46], 10, fill=GREEN, outline=None)
    d.text((316, hy + 12), highlight_label, font=f_body, fill=(6, 12, 9))
    # pointer ring to draw the eye
    _rounded(d, [290, hy - 6, 296 + 306, hy + 52], 12, outline=GREEN_DIM, width=2)

    d.text((296, hy + 78), caption, font=f_small, fill=MUTED)

    # ── DEMO watermark chip (so a screenshot is never mistaken for prod) ────
    chip_w, chip_h = 118, 30
    cx, cy = W - chip_w - 24, 58
    _rounded(d, [cx, cy, cx + chip_w, cy + chip_h], 15, fill=(24, 40, 32), outline=GREEN_DIM, width=1)
    d.text((cx + 16, cy + 7), "DEMO DATA", font=f_chip, fill=GREEN)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(OUT_DIR / filename, "PNG")
    print(f"wrote {OUT_DIR / filename}")


FRAMES = [
    # ── API key ──
    dict(filename="api-key-01.png", breadcrumb="Acme › Settings › Developer",
         menu=["Overview", "Team", "Billing", "Settings"], active="Settings",
         heading="Settings — Developer", highlight_label="Open Developer tab",
         caption="Settings live in the left rail. Developer holds API access."),
    dict(filename="api-key-02.png", breadcrumb="Acme › Settings › Developer › API Keys",
         menu=["Overview", "Team", "Billing", "Settings"], active="Settings",
         heading="API Keys", highlight_label="Generate API key",
         caption="Copy the key once — it is shown a single time."),
    # ── invite member ──
    dict(filename="invite-01.png", breadcrumb="Acme › Team › Members",
         menu=["Overview", "Team", "Billing", "Settings"], active="Team",
         heading="Team — Members", highlight_label="Invite member",
         caption="Members lists everyone with workspace access."),
    dict(filename="invite-02.png", breadcrumb="Acme › Team › Members › Invite",
         menu=["Overview", "Team", "Billing", "Settings"], active="Team",
         heading="Invite a teammate", highlight_label="Send invitation",
         caption="Enter an email and pick a role, then send."),
    # ── refund ──
    dict(filename="refund-01.png", breadcrumb="Acme › Billing › Transactions",
         menu=["Overview", "Team", "Billing", "Settings"], active="Billing",
         heading="Billing — Transactions", highlight_label="Open a transaction",
         caption="Each charge links to its refundable transaction."),
    dict(filename="refund-02.png", breadcrumb="Acme › Billing › Transactions › Refund",
         menu=["Overview", "Team", "Billing", "Settings"], active="Billing",
         heading="Issue a refund", highlight_label="Refund this charge",
         caption="Refunds return to the original payment method."),
]


def main() -> None:
    for frame in FRAMES:
        render(**frame)


if __name__ == "__main__":
    main()
