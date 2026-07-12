#!/usr/bin/env python3
"""Build the event presentation PDF, HTML deck, and MP4.

No third-party Python packages are required. ffmpeg is used only for the MP4.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path
import shutil
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "presentation"
SLIDE_SOURCE = PRESENTATION / "event_deck.md"
BUILD_DIR = PRESENTATION / ".build"
PDF = PRESENTATION / "juggernaut-router-amd-track1.pdf"
HTML = PRESENTATION / "juggernaut-router-amd-track1.html"
MP4 = PRESENTATION / "juggernaut-router-amd-track1.mp4"


def parse_slides() -> list[tuple[str, list[str]]]:
    slides: list[tuple[str, list[str]]] = []
    for raw in SLIDE_SOURCE.read_text(encoding="utf-8").split("\n---\n"):
        title = "Slide"
        body: list[str] = []
        for line in raw.strip().splitlines():
            line = line.rstrip()
            if line.startswith("# "):
                title = line[2:].strip()
            elif line:
                body.append(line)
        slides.append((title, body))
    return slides


def escape_pdf(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap(lines: list[str], width: int) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line.startswith("- "):
            pieces = textwrap.wrap(line[2:], width=width - 2) or [""]
            out.append("- " + pieces[0])
            out.extend("  " + piece for piece in pieces[1:])
        elif line and line[0].isdigit() and ". " in line[:4]:
            prefix, rest = line.split(". ", 1)
            pieces = textwrap.wrap(rest, width=width - len(prefix) - 2) or [""]
            out.append(f"{prefix}. {pieces[0]}")
            out.extend("   " + piece for piece in pieces[1:])
        else:
            out.extend(textwrap.wrap(line, width=width) or [""])
    return out


def build_pdf(slides: list[tuple[str, list[str]]]) -> None:
    objects: list[bytes] = []

    def add(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    catalog = add(b"")
    pages = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []

    for title, body in slides:
        commands = ["BT", "/F1 28 Tf", "60 738 Td", f"({escape_pdf(title)}) Tj", "/F1 14 Tf", "0 -40 Td"]
        for line in wrap(body, 78):
            commands.append(f"({escape_pdf(line)}) Tj")
            commands.append("0 -21 Td")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        content = add(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
        page = add(
            (
                f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page)

    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages} 0 R >>".encode("ascii")
    objects[pages - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{page} 0 R' for page in page_ids)}] /Count {len(page_ids)} >>".encode("ascii")

    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{idx} 0 obj\n".encode("ascii"))
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    PDF.write_bytes(data)


def build_html(slides: list[tuple[str, list[str]]]) -> None:
    sections = []
    for index, (title, body) in enumerate(slides, start=1):
        items = []
        for line in body:
            if line.startswith("- "):
                items.append(f"<li>{html.escape(line[2:])}</li>")
            else:
                items.append(f"<p>{html.escape(line)}</p>")
        sections.append(
            f"""<section class="slide">
  <p class="eyebrow">AMD Developer Hackathon Track 1 / {index:02d}</p>
  <h1>{html.escape(title)}</h1>
  <div class="content">{''.join(items)}</div>
</section>"""
        )
    HTML.write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Juggernaut Router AMD Track 1</title>
  <style>
    :root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #eef2ff; background: #0a0f1f; }
    body { margin: 0; }
    main { height: 100vh; overflow-y: auto; scroll-snap-type: y mandatory; }
    .slide { box-sizing: border-box; min-height: 100vh; padding: 8vh 8vw; display: flex; flex-direction: column; justify-content: center; scroll-snap-align: start; background: linear-gradient(135deg, #0a0f1f 0%, #111827 54%, #052e2b 100%); }
    .eyebrow { margin: 0 0 18px; color: #67e8f9; font-size: 14px; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; }
    h1 { max-width: 1050px; margin: 0 0 30px; font-size: clamp(42px, 7vw, 88px); line-height: .96; }
    .content { max-width: 980px; font-size: clamp(21px, 2.7vw, 34px); line-height: 1.35; color: #dbeafe; }
    li { margin: 12px 0; }
    p { margin: 14px 0; }
    .hint { position: fixed; right: 18px; bottom: 14px; color: #94a3b8; font-size: 13px; }
  </style>
</head>
<body>
  <main>
""" + "\n".join(sections) + """
  </main>
  <div class="hint">Arrow keys or scroll</div>
  <script>
    const slides = [...document.querySelectorAll('.slide')];
    let index = 0;
    function move(delta) {
      index = Math.max(0, Math.min(slides.length - 1, index + delta));
      slides[index].scrollIntoView({ behavior: 'smooth' });
    }
    addEventListener('keydown', (event) => {
      if (['ArrowRight', 'ArrowDown', ' '].includes(event.key)) move(1);
      if (['ArrowLeft', 'ArrowUp'].includes(event.key)) move(-1);
    });
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )


def font_file() -> str | None:
    for path in [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if Path(path).exists():
            return path
    return None


def build_video(slides: list[tuple[str, list[str]]]) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found; skipped MP4")
        return
    BUILD_DIR.mkdir(exist_ok=True)
    font = font_file()
    clips: list[Path] = []
    for index, (title, body) in enumerate(slides, start=1):
        text = "\n".join([title, ""] + wrap(body, 50))
        text_file = BUILD_DIR / f"slide_{index:02d}.txt"
        text_file.write_text(text, encoding="utf-8")
        clip = BUILD_DIR / f"slide_{index:02d}.mp4"
        draw = f"drawtext=textfile={text_file}:fontcolor=white:fontsize=33:x=72:y=70:line_spacing=15:box=1:boxcolor=0x0a0f1fcc:boxborderw=26"
        if font:
            draw = f"drawtext=fontfile={font}:textfile={text_file}:fontcolor=white:fontsize=33:x=72:y=70:line_spacing=15:box=1:boxcolor=0x0a0f1fcc:boxborderw=26"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x0a0f1f:s=1280x720:d=7",
                "-vf",
                draw,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        clips.append(clip)
    concat = BUILD_DIR / "concat.txt"
    concat.write_text("".join(f"file '{clip.resolve()}'\n" for clip in clips), encoding="utf-8")
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(MP4)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-video", action="store_true")
    args = parser.parse_args()
    slides = parse_slides()
    build_pdf(slides)
    build_html(slides)
    if not args.skip_video:
        build_video(slides)
    print(f"PDF: {PDF}")
    print(f"HTML: {HTML}")
    if MP4.exists():
        print(f"MP4: {MP4}")


if __name__ == "__main__":
    main()
