"""Build a small static Pages site for KeyQuest docs."""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "site"
README_HTML = REPO_ROOT / "README.html"
CHANGELOG_MD = REPO_ROOT / "docs" / "user" / "WHATS_NEW.md"
VERSION_FILE = REPO_ROOT / "modules" / "version.py"
ASSETS_DIR = REPO_ROOT / "docs" / "assets"


def read_version() -> str:
    match = re.search(
        r'__version__\s*=\s*"([^"]+)"',
        VERSION_FILE.read_text(encoding="utf-8"),
    )
    if not match:
        return ""
    return match.group(1)


def read_release_date() -> str:
    """__release_date__ from version.py, stamped by release_bump.py."""
    match = re.search(
        r'__release_date__\s*=\s*"([^"]+)"',
        VERSION_FILE.read_text(encoding="utf-8"),
    )
    if not match:
        return ""
    return match.group(1)


def _inline_markup(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    parts: list[str] = []
    in_list = False
    in_code = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(item.strip() for item in paragraph if item.strip())
            parts.append(f"<p>{_inline_markup(text)}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                parts.append("</code></pre>")
                in_code = False
            else:
                parts.append("<pre><code>")
                in_code = True
            continue

        if in_code:
            parts.append(html.escape(line))
            continue

        if not stripped:
            flush_paragraph()
            close_list()
            continue

        if stripped == "---":
            flush_paragraph()
            close_list()
            parts.append("<hr>")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            close_list()
            level = len(heading_match.group(1))
            text = _inline_markup(heading_match.group(2))
            parts.append(f"<h{level}>{text}</h{level}>")
            continue

        bullet_match = re.match(r"^\s*-\s+(.*)$", line)
        if bullet_match:
            flush_paragraph()
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_markup(bullet_match.group(1))}</li>")
            continue

        numbered_match = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if numbered_match:
            flush_paragraph()
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_markup(numbered_match.group(1))}</li>")
            continue

        close_list()
        paragraph.append(line)

    flush_paragraph()
    close_list()
    if in_code:
        parts.append("</code></pre>")

    return "\n".join(parts)


def build_changelog_page() -> str:
    body = markdown_to_html(CHANGELOG_MD.read_text(encoding="utf-8"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>New in Key Quest</title>
  <style>
    :root {{
      color-scheme: light;
    }}
    body {{
      font-family: Arial, sans-serif;
      font-size: 18px;
      line-height: 1.6;
      color: #111;
      background: #fff;
      margin: 0;
      padding: 0;
    }}
    header,
    main,
    footer {{
      display: block;
    }}
    header,
    footer {{
      padding: 0 24px;
    }}
    .content-block {{
      max-width: 75ch;
      margin: 0 auto;
    }}
    main {{
      max-width: 900px;
      margin: 0 auto;
      padding: 24px;
    }}
    a {{
      color: #0b57d0;
    }}
    a:hover {{
      text-decoration-thickness: 2px;
    }}
    a:focus-visible {{
      outline: 3px solid #111;
      outline-offset: 2px;
    }}
    .skip-link {{
      position: absolute;
      left: 8px;
      top: -48px;
      z-index: 1000;
      background: #fff;
      color: #111;
      border: 2px solid #111;
      padding: 8px 10px;
      text-decoration: none;
    }}
    .skip-link:focus {{
      top: 8px;
    }}
    h1, h2, h3 {{
      line-height: 1.3;
    }}
    h1 {{
      margin-top: 0;
    }}
    ul {{
      padding-left: 20px;
    }}
    code, pre {{
      font-family: Consolas, "Courier New", monospace;
    }}
    pre {{
      background: #f4f4f4;
      padding: 12px;
      overflow-x: auto;
    }}
    hr {{
      border: 0;
      border-top: 1px solid #ccc;
      margin: 24px 0;
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <header>
    <div class="content-block">
      <p><a href="index.html">Back to the KeyQuest User Guide</a></p>
    </div>
  </header>
  <main id="main-content">
    <div class="content-block">
    {body}
    </div>
  </main>
  <footer>
    <div class="content-block">
      <p>End of New in Key Quest.</p>
    </div>
  </footer>
</body>
</html>
"""


def build_index_page() -> str:
    source = README_HTML.read_text(encoding="utf-8")
    version = read_version()
    if version:
        source = source.replace("{{APP_VERSION}}", version)
    release_date = read_release_date()
    if release_date:
        # The About line said 2026-02-19 under every version until 1.28.1.
        source = source.replace("{{APP_RELEASE_DATE}}", release_date)
    if 'href="changelog.html"' not in source:
        source = source.replace(
            '<li><a href="#help">Need Help</a></li>',
            '<li><a href="changelog.html">New in Key Quest</a></li>\n      <li><a href="#help">Need Help</a></li>',
        )
    return source


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (OUTPUT_DIR / "index.html").write_text(build_index_page(), encoding="utf-8")
    (OUTPUT_DIR / "changelog.html").write_text(build_changelog_page(), encoding="utf-8")
    if ASSETS_DIR.exists():
        shutil.copytree(ASSETS_DIR, OUTPUT_DIR / "docs" / "assets", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
