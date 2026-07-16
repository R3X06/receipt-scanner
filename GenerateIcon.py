"""
generate_icon.py — builds PWA app icons (icon-192.png, icon-512.png,
icon-512-maskable.png) from KALLA's real project assets.

  - The wordmark path is read straight out of
    frontend/src/components/ui/KallaLogo.jsx (regex-extracted from the live
    <path d="...">, not redrawn), then CROPPED to just the leading "K" glyph
    via a nested-<svg> viewBox window (K_CROP below). The full path is kept
    verbatim; the window simply clips everything but the K.
  - Every color/opacity is copied verbatim from frontend/src/index.css
    (.dark, .glass, body's radial-gradient wash) and the wordmark glow filter
    in Dashboard.jsx. The receipt motif reuses those same tokens.

The K sits as the hero over a receipt motif (torn zigzag bottom edge, dashed
perforation, faint text rows) on the app's dark glass tile — the "receipt vibe"
background requested, built from the shipping design system.

Rasterizes via the resvg CLI (portable single binary; avoids the libcairo
install pain cairosvg has on Windows). Download from:
  https://github.com/linebender/resvg/releases  (resvg-win64.zip on Windows)
Drop resvg.exe next to this script or pass --resvg <path>.

Run: python3 generate_icon.py /path/to/KallaLogo.jsx /path/to/output/dir [--resvg /path/to/resvg(.exe)]
"""
import re
import random
import sys
import os
import shutil
import subprocess
import tempfile

# --- tokens copied verbatim from frontend/src/index.css (.dark block) ---
BG = "#0B0F14"                            # --background
GLASS_FILL = "rgba(255,255,255,0.024)"   # .glass background
GLASS_BORDER = "rgba(255,255,255,0.01)"  # .glass border
# body background-image radial gradients (index.css)
GRAD_STOPS = [
    (12, 8, "rgba(88,75,204,0.35)"),
    (88, 14, "rgba(214,87,176,0.30)"),
    (50, 120, "rgba(232,113,193,0.25)"),
]
# wordmark glow, copied from Dashboard.jsx's KallaLogo wrapper:
# filter: drop-shadow(0 0 12px #A855F7aa) drop-shadow(0 0 32px #A855F760)
GLOW_TIGHT = "#A855F7"
GLOW_TIGHT_OPACITY = 0.30
GLOW_WIDE = "#A855F7"
GLOW_WIDE_OPACITY = 1.2
LOGO_FILL = "#dfbaffc0"                   # KallaLogo's own default `color`
ACCENT = "#A855F7"                        # purple accent for receipt details

# The "K" glyph's bounding box within KallaLogo.jsx's coordinate space
# (viewBox "246 132 1037 153"). Measured by rendering the wordmark 1:1 and
# column-scanning for the first letter's ink extent. Re-measure if the
# wordmark art in KallaLogo.jsx ever changes.
K_CROP = (254.0, 140.0, 298.0, 136.0)     # x, y, w, h


def extract_logo(kalla_logo_path):
    """Pull viewBox and path `d` straight out of the real KallaLogo.jsx file."""
    with open(kalla_logo_path) as f:
        content = f.read()
    vb_match = re.search(r'viewBox="([^"]+)"', content)
    d_match = re.search(r'd="([^"]+)"', content)
    if not vb_match or not d_match:
        raise ValueError("Could not find viewBox/path d= in KallaLogo.jsx — file shape changed?")
    vb = [float(v) for v in vb_match.group(1).split()]
    return vb, d_match.group(1)


def _dot_run(x0, y, width, dr, gap, color, opacity):
    """A single dot-matrix run (one printed line of text)."""
    n = int(width // gap)
    return "".join(
        f'<circle cx="{x0 + i*gap:.1f}" cy="{y:.1f}" r="{dr:.2f}" fill="{color}" opacity="{opacity}"/>'
        for i in range(n + 1))


def _barcode(x0, y, width, height, color, opacity, seed=7):
    """A receipt barcode: vertical bars of varying widths with gaps."""
    rng = random.Random(seed)
    unit = width / 90.0
    bars, x = [], x0
    while x < x0 + width:
        w = rng.choice([1, 1, 2, 3]) * unit
        if rng.random() < 0.72:
            bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w,0.6):.1f}" '
                        f'height="{height:.1f}" fill="{color}" opacity="{opacity}"/>')
        x += w + unit
    return "".join(bars)


def _receipt_motif(size):
    """Borderless receipt 'print' — a header, right-priced line-items, an accent
    total, and a barcode — all low-opacity so it reads as faint printed paper
    behind the K. No frame, no dashes. Tones from the app's tokens / accent."""
    white = "#ffffff"
    mL, mR = size * 0.14, size * 0.86          # print margins (no border)
    dr, gap = size * 0.006, size * 0.017

    def item(y, item_w, price_w, op=0.09, col=white):
        """A receipt line: left 'item' run + right-aligned 'price' run."""
        return (_dot_run(mL, y, size * item_w, dr, gap, col, op)
                + _dot_run(mR - size * price_w, y, size * price_w, dr, gap, col, op))

    return f'''
    {_dot_run(size*0.5 - size*0.11, size*0.115, size*0.22, dr, gap, white, 0.10)}
    {_dot_run(size*0.5 - size*0.065, size*0.150, size*0.13, dr, gap, white, 0.06)}
    {item(size*0.225, 0.26, 0.10)}
    {item(size*0.275, 0.22, 0.09, op=0.08)}
    {item(size*0.660, 0.28, 0.10)}
    {item(size*0.710, 0.20, 0.08, op=0.08)}
    {item(size*0.780, 0.15, 0.13, op=0.24, col=ACCENT)}
    {_barcode(mL, size*0.845, mR - mL, size*0.042, white, 0.12)}'''


def build_icon_svg(viewbox, path_d, size=512, maskable=False):
    kx, ky, kw, kh = K_CROP
    k_aspect = kw / kh

    # content scale: maskable pulls the K + receipt into the ~safe zone; the
    # dark tile always fills edge to edge so no background gap shows under a mask.
    content_scale = 0.72 if maskable else 1.0
    corner_r = 0 if maskable else size * 0.22   # full-bleed for maskable, tile for standard

    # size the K to a share of the tile width (it's ~2.2:1, so this keeps it
    # comfortably inside the receipt panel with margin on both sides)
    k_w = size * 0.80
    k_h = k_w / k_aspect
    k_x0 = (size - k_w) / 2
    k_y0 = (size - k_h) / 2

    # radial-gradient brand wash (index.css body)
    grad_defs, grad_rects = "", ""
    for i, (cx, cy, color) in enumerate(GRAD_STOPS):
        gid = f"grad{i}"
        grad_defs += f'''
    <radialGradient id="{gid}" cx="{cx}%" cy="{cy}%" r="70%">
      <stop offset="0%" stop-color="{color}"/>
      <stop offset="100%" stop-color="{color.rsplit(',',1)[0]},0)"/>
    </radialGradient>'''
        grad_rects += f'\n    <rect width="{size}" height="{size}" fill="url(#{gid})"/>'

    # the cropped K: a nested <svg> whose viewBox is the K's bbox, so only the K
    # shows; the full wordmark path is untouched.
    k_window = (f'<svg x="{k_x0:.2f}" y="{k_y0:.2f}" width="{k_w:.2f}" height="{k_h:.2f}" '
                f'viewBox="{kx} {ky} {kw} {kh}"><path d="{path_d}" fill="{LOGO_FILL}"/></svg>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"
     viewBox="0 0 {size} {size}">
  <defs>{grad_defs}
    <clipPath id="tile">
      <rect width="{size}" height="{size}" rx="{corner_r}" ry="{corner_r}"/>
    </clipPath>
    <filter id="glowTight" x="-50%" y="-50%" width="200%" height="200%">
      <feDropShadow dx="0" dy="0" stdDeviation="{size*0.012}" flood-color="{GLOW_TIGHT}" flood-opacity="{GLOW_TIGHT_OPACITY}"/>
    </filter>
    <filter id="glowWide" x="-80%" y="-80%" width="260%" height="260%">
      <feDropShadow dx="0" dy="0" stdDeviation="{size*0.035}" flood-color="{GLOW_WIDE}" flood-opacity="{GLOW_WIDE_OPACITY}"/>
    </filter>
  </defs>

  <g clip-path="url(#tile)">
    <rect width="{size}" height="{size}" fill="{BG}"/>{grad_rects}
    <rect width="{size}" height="{size}" fill="{GLASS_FILL}"/>
    <rect x="1" y="1" width="{size-2}" height="{size-2}" fill="none"
          stroke="{GLASS_BORDER}" stroke-width="2"/>

    <g transform="translate({size/2},{size/2}) scale({content_scale}) translate({-size/2},{-size/2})">
      {_receipt_motif(size)}
      <g filter="url(#glowWide)">{k_window}</g>
      <g filter="url(#glowTight)">{k_window}</g>
    </g>
  </g>
</svg>'''


def find_resvg(explicit_path=None):
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        raise FileNotFoundError(f"--resvg path given but not found: {explicit_path}")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for candidate in ("resvg.exe", "resvg"):
        local = os.path.join(script_dir, candidate)
        if os.path.isfile(local):
            return local
    on_path = shutil.which("resvg") or shutil.which("resvg.exe")
    if on_path:
        return on_path
    raise FileNotFoundError(
        "Couldn't find resvg. Download it from "
        "https://github.com/linebender/resvg/releases (resvg-win64.zip on "
        "Windows), unzip it, and place resvg.exe next to this script — or pass "
        "--resvg <path>."
    )


def render_svg_to_png(svg_content, out_path, size, resvg_path):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as tmp:
        tmp.write(svg_content)
        tmp_svg_path = tmp.name
    try:
        cmd = [resvg_path, tmp_svg_path, out_path, "--width", str(size), "--height", str(size)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"resvg failed:\n{result.stderr}")
        if result.stderr:
            print(f"  (resvg warnings: {result.stderr.strip()})")
    finally:
        os.unlink(tmp_svg_path)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    def flag(name):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None

    resvg_path = find_resvg(flag("--resvg"))
    print(f"Using resvg at: {resvg_path}")

    kalla_logo_path = args[0] if len(args) > 0 else "KallaLogo.jsx"
    out_dir = args[1] if len(args) > 1 else "."

    viewbox, path_d = extract_logo(kalla_logo_path)
    print(f"Extracted wordmark: viewBox={viewbox}, path length={len(path_d)} chars")
    print(f"Cropping to K at {K_CROP} (aspect {K_CROP[2]/K_CROP[3]:.2f}:1)")

    for filename, size, maskable in [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-512-maskable.png", 512, True),
    ]:
        svg = build_icon_svg(viewbox, path_d, size=size, maskable=maskable)
        out_path = f"{out_dir}/{filename}"
        render_svg_to_png(svg, out_path, size, resvg_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()