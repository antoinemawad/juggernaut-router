#!/usr/bin/env python3
"""Build presentation PDF, HTML deck, and optional MP4 slide video.

This script intentionally avoids Python package dependencies so the deck can be
rebuilt on a clean machine. The PDF writer is minimal but valid for text slides.
"""

from __future__ import annotations

import argparse
import html
import os
from pathlib import Path
import shutil
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]
SLIDES = ROOT / "presentation" / "slides.md"
OUT_DIR = ROOT / "presentation"
BUILD_DIR = OUT_DIR / "build"
PDF_OUT = OUT_DIR / "juggernaut-router-presentation.pdf"
HTML_OUT = OUT_DIR / "juggernaut-router-video.html"
MP4_OUT = OUT_DIR / "juggernaut-router-video.mp4"


def parse_slides(path: Path) -> list[dict[str, object]]:
    raw_slides = path.read_text(encoding="utf-8").split("\n---\n")
    slides: list[dict[str, object]] = []
    for raw in raw_slides:
        lines = [line.rstrip() for line in raw.strip().splitlines()]
        title = "Slide"
        body: list[str] = []
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
            elif line:
                body.append(line)
        slides.append({"title": title, "body": body})
    return slides


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_lines(lines: list[str], width: int = 74) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if line.startswith("- "):
            prefix = "- "
            content = line[2:]
            chunks = textwrap.wrap(content, width=width - 2) or [""]
            wrapped.append(prefix + chunks[0])
            wrapped.extend("  " + chunk for chunk in chunks[1:])
        elif line and line[0].isdigit() and ". " in line[:4]:
            prefix, content = line.split(". ", 1)
            chunks = textwrap.wrap(content, width=width - len(prefix) - 2) or [""]
            wrapped.append(f"{prefix}. {chunks[0]}")
            wrapped.extend("   " + chunk for chunk in chunks[1:])
        else:
            wrapped.extend(textwrap.wrap(line, width=width) or [""])
    return wrapped


def make_pdf(slides: list[dict[str, object]], out: Path) -> None:
    objects: list[bytes] = []
    page_ids: list[int] = []

    def add_object(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    catalog_id = add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add_object(b"")
    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for slide in slides:
        title = str(slide["title"])
        body = wrap_lines(list(slide["body"]), width=74)
        commands = [
            "BT",
            "/F1 30 Tf",
            "72 738 Td",
            f"({pdf_escape(title)}) Tj",
            "/F1 15 Tf",
            "0 -42 Td",
        ]
        for line in body:
            commands.append(f"({pdf_escape(line)}) Tj")
            commands.append("0 -23 Td")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        content_id = add_object(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )
        page_id = add_object(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    objects[catalog_id - 1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    out.write_bytes(output)


def make_html(slides: list[dict[str, object]], out: Path) -> None:
    cards = []
    for idx, slide in enumerate(slides, start=1):
        body = "\n".join(f"<li>{html.escape(line[2:])}</li>" if line.startswith("- ") else f"<p>{html.escape(line)}</p>" for line in slide["body"])
        cards.append(
            f"""<section class="slide" data-index="{idx}">
  <p class="kicker">Juggernaut Router / {idx:02d}</p>
  <h1>{html.escape(str(slide["title"]))}</h1>
  <div class="body">{body}</div>
</section>"""
        )
    out.write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Juggernaut Router Video Presentation</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #0b1020; color: #f8fafc; }
    main { scroll-snap-type: y mandatory; height: 100vh; overflow-y: auto; }
    .slide { box-sizing: border-box; min-height: 100vh; padding: 9vh 9vw; scroll-snap-align: start; display: flex; flex-direction: column; justify-content: center; background: radial-gradient(circle at 85% 20%, rgba(34,197,94,.18), transparent 28%), #0b1020; }
    .kicker { color: #38bdf8; text-transform: uppercase; letter-spacing: .12em; font-size: 14px; font-weight: 700; }
    h1 { font-size: clamp(44px, 7vw, 88px); line-height: .96; margin: 0 0 32px; max-width: 980px; }
    .body { font-size: clamp(22px, 3vw, 36px); line-height: 1.35; max-width: 980px; }
    li { margin: 12px 0; }
    p { margin: 14px 0; }
    .controls { position: fixed; right: 20px; bottom: 16px; color: #94a3b8; font-size: 13px; }
  </style>
</head>
<body>
  <main>
""" + "\n".join(cards) + """
  </main>
  <div class="controls">Use arrow keys or scroll. Record this page for the video walkthrough.</div>
  <script>
    const slides = [...document.querySelectorAll('.slide')];
    let i = 0;
    function go(delta) {
      i = Math.max(0, Math.min(slides.length - 1, i + delta));
      slides[i].scrollIntoView({ behavior: 'smooth' });
    }
    addEventListener('keydown', (event) => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown' || event.key === ' ') go(1);
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') go(-1);
    });
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )


def find_font() -> str | None:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def make_video(slides: list[dict[str, object]], out: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found; skipped MP4 build")
        return
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    font = find_font()
    clips: list[Path] = []
    for idx, slide in enumerate(slides, start=1):
        lines = [str(slide["title"]), ""] + wrap_lines(list(slide["body"]), width=50)
        text_path = BUILD_DIR / f"slide_{idx:02d}.txt"
        text_path.write_text("\n".join(lines), encoding="utf-8")
        clip_path = BUILD_DIR / f"slide_{idx:02d}.mp4"
        drawtext = (
            f"drawtext=textfile={text_path}:fontcolor=white:fontsize=34:"
            "x=80:y=80:line_spacing=16:box=1:boxcolor=0x0b1020cc:boxborderw=28"
        )
        if font:
            drawtext = f"drawtext=fontfile={font}:textfile={text_path}:fontcolor=white:fontsize=34:x=80:y=80:line_spacing=16:box=1:boxcolor=0x0b1020cc:boxborderw=28"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x0b1020:s=1280x720:d=7",
                "-vf",
                drawtext,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        clips.append(clip_path)
    concat = BUILD_DIR / "concat.txt"
    concat.write_text("".join(f"file '{clip.resolve()}'\n" for clip in clips), encoding="utf-8")
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(out)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-video", action="store_true", help="Build PDF/HTML only.")
    args = parser.parse_args()

    slides = parse_slides(SLIDES)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_pdf(slides, PDF_OUT)
    make_html(slides, HTML_OUT)
    if not args.skip_video:
        make_video(slides, MP4_OUT)
    print(f"PDF: {PDF_OUT}")
    print(f"HTML video deck: {HTML_OUT}")
    if MP4_OUT.exists():
        print(f"MP4 video: {MP4_OUT}")


if __name__ == "__main__":
    main()
