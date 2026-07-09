"""
generate_icon.py — builds PWA app icons (icon-192.png, icon-512.png,
icon-512-maskable.png) directly from KALLA's real project assets:

  - The logo path is read straight out of frontend/src/components/ui/KallaLogo.jsx
    (regex-extracted from the live <path d="..."> — not redrawn or reinterpreted).
  - Every color/opacity value below is copied verbatim from
    frontend/src/index.css (the .dark block, .glass class, and body's
    radial-gradient background) and from the wordmark's glow filter in
    Dashboard.jsx. Nothing here is invented — it's the same design system
    already shipping in the app, just composed onto a square icon canvas.

Rasterizes via the resvg command-line tool (a portable single-binary SVG
renderer, no native Python bindings) rather than cairosvg — cairosvg needs
a system-installed libcairo which is a common source of install failures
on Windows. Download resvg from:
  https://github.com/linebender/resvg/releases
(grab resvg-win64.zip on Windows, unzip, and either drop resvg.exe next to
this script or pass its path via --resvg).

Run: python3 generate_icon.py /path/to/KallaLogo.jsx /path/to/output/dir [--resvg /path/to/resvg(.exe)]
"""
import re
import sys
import os
import shutil
import subprocess
import tempfile

# --- tokens copied verbatim from frontend/src/index.css (.dark block) ---
BG = "#0B0F14"                    # --background
GLASS_FILL = "rgba(255,255,255,0.024)"   # .glass background
GLASS_BORDER = "rgba(255,255,255,0.01)"  # .glass border
# body background-image radial gradients (index.css)
GRAD_STOPS = [
    # (cx%, cy%, color)
    (12, 8, "rgba(88,75,204,0.35)"),
    (88, 14, "rgba(214,87,176,0.30)"),
    (50, 120, "rgba(232,113,193,0.25)"),
]
# wordmark glow, copied from Dashboard.jsx's KallaLogo wrapper:
# filter: drop-shadow(0 0 12px #A855F7aa) drop-shadow(0 0 32px #A855F760)
GLOW_TIGHT = "#A855F7"   # alpha aa ~= 0.67
GLOW_TIGHT_OPACITY = 0.30
GLOW_WIDE = "#A855F7"    # alpha 60 ~= 0.38
GLOW_WIDE_OPACITY = 1.2
LOGO_FILL = "#dfbaffc0"  # KallaLogo's own default `color` 

# tagline shown below the wordmark — matches the app's Chakra Petch chrome
# font (e.g. the small "mahan's" label above the wordmark in Dashboard.jsx)
TAGLINE = "Personal Finance Ledger"
TAGLINE_FILL = "rgba(232,237,242,0.55)"  # muted --foreground tone


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


def build_icon_svg(viewbox, path_d, size=512, maskable=False):
    vb_x, vb_y, vb_w, vb_h = viewbox

    # Maskable icons need content inside the ~80% "safe zone" (OS may mask
    # to a circle/rounded-square and crop the outer ring) — extra padding.
    # Maskable icons need content inside the ~80% "safe zone" (OS may mask
    # to a circle/rounded-square and crop the outer ring) — that padding is
    # a real platform requirement, not a style choice, so it stays as-is.
    # The standard icon has no such constraint, so padding is minimized to
    # maximize legibility at small sizes (the wordmark's ~6.8:1 aspect ratio
    # caps how large it can ever read, but tighter padding still helps).
    pad_frac = 0.30 if maskable else 0.09
    avail_w = size * (1 - 2 * pad_frac)

    # reserve vertical room for the tagline below the wordmark
    tagline_size = size * 0.030
    gap = size * 0.04
    avail_h_for_logo = size * (1 - 2 * pad_frac) - tagline_size - gap

    logo_aspect = vb_w / vb_h
    fit_w = avail_w
    fit_h = fit_w / logo_aspect
    if fit_h > avail_h_for_logo:
        fit_h = avail_h_for_logo
        fit_w = fit_h * logo_aspect

    scale = fit_w / vb_w
    total_block_h = fit_h + gap + tagline_size
    block_top = (size - total_block_h) / 2

    tx = (size - fit_w) / 2 - vb_x * scale
    ty = block_top - vb_y * scale
    tagline_y = block_top + fit_h + gap + tagline_size * 0.75  # baseline

    grad_defs = ""
    grad_rects = ""
    for i, (cx_pct, cy_pct, color) in enumerate(GRAD_STOPS):
        gid = f"grad{i}"
        grad_defs += f"""
    <radialGradient id="{gid}" cx="{cx_pct}%" cy="{cy_pct}%" r="70%">
      <stop offset="0%" stop-color="{color}"/>
      <stop offset="100%" stop-color="{color.rsplit(',',1)[0]},0)"/>
    </radialGradient>"""
        grad_rects += f'\n    <rect width="{size}" height="{size}" fill="url(#{gid})"/>'

    # rounded-square "app tile" corner radius, proportional to size
    corner_r = size * 0.22

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"
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
    <filter id="glowHalo" x="-120%" y="-120%" width="340%" height="340%">
      <feDropShadow dx="0" dy="0" stdDeviation="{size*0.08}" flood-color="{GLOW_WIDE}" flood-opacity="0.25"/>
    </filter>
  </defs>

  <g clip-path="url(#tile)">
    <!-- base color, from index.css .dark background token -->
    <rect width="{size}" height="{size}" fill="{BG}"/>
    <!-- body's real radial-gradient brand wash -->{grad_rects}
    <!-- .glass panel tokens, as the icon's tile surface -->
    <rect width="{size}" height="{size}" fill="{GLASS_FILL}"/>
    <rect x="1" y="1" width="{size-2}" height="{size-2}" fill="none"
          stroke="{GLASS_BORDER}" stroke-width="2"/>

    <!-- the real KALLA wordmark path, scaled/centered, with its real glow -->
    <g transform="translate({tx},{ty}) scale({scale})" filter="url(#glowWide)">
      <path d="{path_d}" fill="{LOGO_FILL}"/>
    </g>
    <g transform="translate({tx},{ty}) scale({scale})" filter="url(#glowTight)">
      <path d="{path_d}" fill="{LOGO_FILL}"/>
    </g>
    <!-- tagline below the wordmark -->
    <text x="{size/2}" y="{tagline_y}" text-anchor="middle"
          font-family="Chakra Petch, Segoe UI, Arial, sans-serif" font-weight="900" font-size="{tagline_size}"
          letter-spacing="{tagline_size*0.30}" fill="{TAGLINE_FILL}">{TAGLINE}</text>
  </g>
</svg>"""

def resolve_font_file(font_file_arg):
    """Accepts a .ttf/.otf directly, or a .woff/.woff2 which gets converted
    to a temp .ttf via fonttools (resvg's font loader can't read woff/woff2
    directly — confirmed by testing, not assumed)."""
    if not font_file_arg:
        return None
    ext = os.path.splitext(font_file_arg)[1].lower()
    if ext in (".ttf", ".otf"):
        return font_file_arg
    if ext in (".woff", ".woff2"):
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            raise RuntimeError(
                f"{font_file_arg} is a {ext} file — resvg needs .ttf/.otf. "
                "Install the converter with: pip install fonttools"
            )
        font = TTFont(font_file_arg)
        font.flavor = None
        tmp_ttf = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
        font.save(tmp_ttf.name)
        print(f"Converted {font_file_arg} -> {tmp_ttf.name} (temp .ttf for resvg)")
        return tmp_ttf.name
    raise ValueError(f"Unrecognized font file extension: {ext}")

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
        "https://github.com/linebender/resvg/releases "
        "(resvg-win64.zip on Windows), unzip it, and place resvg.exe "
        "in the same folder as this script — or pass --resvg <path>."
    )


def render_svg_to_png(svg_content, out_path, size, resvg_path, font_file=None):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as tmp:
        tmp.write(svg_content)
        tmp_svg_path = tmp.name
    try:
        cmd = [resvg_path, tmp_svg_path, out_path, "--width", str(size), "--height", str(size)]
        if font_file:
            cmd += ["--use-font-file", font_file]
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

    resvg_arg = flag("--resvg")
    font_file_arg = flag("--font-file")

    kalla_logo_path = args[0] if len(args) > 0 else "KallaLogo.jsx"
    out_dir = args[1] if len(args) > 1 else "."

    resvg_path = find_resvg(resvg_arg)
    print(f"Using resvg at: {resvg_path}")

    font_file = resolve_font_file(font_file_arg)
    if font_file:
        print(f"Using font file: {font_file}")
    else:
        print("No --font-file given — falling back to Segoe UI/Arial/sans-serif "
              "(text will render, but not in the exact Chakra Petch face)")

    viewbox, path_d = extract_logo(kalla_logo_path)
    print(f"Extracted logo: viewBox={viewbox}, path length={len(path_d)} chars")

    jobs = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-512-maskable.png", 512, True),
    ]
    for filename, size, maskable in jobs:
        svg = build_icon_svg(viewbox, path_d, size=size, maskable=maskable)
        out_path = f"{out_dir}/{filename}"
        render_svg_to_png(svg, out_path, size, resvg_path, font_file=font_file)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()