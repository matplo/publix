#!/usr/bin/env python3
"""Scan ./public and refresh the 3D file browser in public/index.html.

Usage
-----
    python3 tools/build_index.py                     # scan ./public, update ./public/index.html
    python3 tools/build_index.py --title "My stuff"  # change the page title
    python3 tools/build_index.py --exclude 'drafts/*' --exclude '*.tmp'

How it works
------------
public/index.html holds the whole browser UI (three.js scene, side panel, styles).
This script only rewrites three marked regions inside it:

  * <title>…</title>
  * <script type="application/json" id="publix-manifest"> … </script>   data for the 3D view
    (also supports id="ib-manifest")
  * <!-- publix:static --> … <!-- /publix:static -->                    plain list (no-JS fallback)
    (also supports index-browser:static markers)

so the page's look can be edited freely and the script re-run whenever files change.
Hidden files/folders (dot-names) and the index page itself are skipped; empty folders
are dropped. Dates come from the last git commit touching a file, falling back to mtime.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

KINDS = {
    "html": {"html", "htm", "xhtml"},
    "pdf": {"pdf"},
    "image": {"png", "jpg", "jpeg", "gif", "webp", "svg", "avif", "bmp", "ico", "tif", "tiff"},
    "video": {"mp4", "webm", "mov", "m4v", "ogv"},
    "audio": {"mp3", "wav", "ogg", "oga", "m4a", "flac", "aac"},
    "text": {"md", "txt", "csv", "tsv", "json", "yaml", "yml", "xml", "log", "tex", "ipynb"},
}
EXT_KIND = {ext: kind for kind, exts in KINDS.items() for ext in exts}
DEFAULT_EXCLUDES = [".*", "__pycache__", "Thumbs.db", "desktop.ini"]

TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)
PAGE_TITLE_RE = re.compile(r"<title>.*?</title>", re.S)
MANIFEST_RE = re.compile(
    r'(<script type="application/json" id="(?:publix|ib)-manifest">)(.*?)(</script>)', re.S
)
STATIC_RE = re.compile(
    r"(<!-- (?:publix|index-browser):static -->)(.*?)(<!-- /(?:publix|index-browser):static -->)",
    re.S,
)


def iso_utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def kind_of(name: str) -> tuple[str, str]:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""
    return ext, EXT_KIND.get(ext, "other")


def git_dates(root: Path) -> dict[str, str]:
    """Map path (relative to root) -> ISO date of the last commit that touched it."""
    cmd = ["git", "-c", "core.quotepath=off", "log", "--format=%x01%ct",
           "--name-only", "--relative", "--", "."]
    try:
        out = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    dates: dict[str, str] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("\x01"):
            current = iso_utc(int(line[1:]))
        elif line and current:
            dates.setdefault(line, current)  # log is newest-first
    return dates


def html_title(path: Path) -> str | None:
    try:
        with path.open("rb") as fh:
            head = fh.read(256 * 1024)
    except OSError:
        return None
    m = TITLE_RE.search(head)
    if not m:
        return None
    title = " ".join(html.unescape(m.group(1).decode("utf-8", "replace")).split())
    return title[:200] or None


def is_excluded(rel: str, name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def scan(directory: Path, root: Path, patterns: list[str], dates: dict[str, str],
         skip: set[str]) -> dict:
    rel_dir = "" if directory == root else directory.relative_to(root).as_posix()
    node = {"type": "dir", "name": directory.name, "path": rel_dir, "children": []}
    try:
        entries = sorted(os.scandir(directory), key=lambda e: (e.name.lower(), e.name))
    except OSError as exc:
        print(f"warning: cannot read {directory}: {exc}", file=sys.stderr)
        return node

    dirs, files = [], []
    for entry in entries:
        rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
        if rel in skip or is_excluded(rel, entry.name, patterns):
            continue
        if entry.is_dir(follow_symlinks=False):
            sub = scan(Path(entry.path), root, patterns, dates, skip)
            if sub["children"]:
                dirs.append(sub)
        elif entry.is_file():
            st = entry.stat()
            ext, kind = kind_of(entry.name)
            item = {
                "type": "file",
                "name": entry.name,
                "path": rel,
                "href": quote(rel),
                "ext": ext,
                "kind": kind,
                "size": st.st_size,
                "mtime": dates.get(rel) or iso_utc(st.st_mtime),
            }
            if kind == "html":
                title = html_title(Path(entry.path))
                if title:
                    item["title"] = title
            files.append(item)
    node["children"] = dirs + files
    return node


def static_list(node: dict) -> str:
    parts = ["<ul>"]
    for child in node["children"]:
        name = html.escape(child["name"])
        if child["type"] == "dir":
            parts.append(f"<li><strong>{name}/</strong>{static_list(child)}</li>")
        else:
            href = html.escape(child["href"], quote=True)
            parts.append(f'<li><a href="{href}" target="_blank" rel="noopener">{name}</a></li>')
    parts.append("</ul>")
    return "".join(parts)


def tally(node: dict) -> tuple[int, int, int]:
    files = folders = size = 0
    for child in node["children"]:
        if child["type"] == "dir":
            f, d, s = tally(child)
            files, folders, size = files + f, folders + d + 1, size + s
        else:
            files, size = files + 1, size + child["size"]
    return files, folders, size


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=repo / "public",
                    help="directory to scan (default: ./public)")
    ap.add_argument("--index", type=Path, default=None,
                    help="page to update (default: <root>/index.html)")
    ap.add_argument("--title", default="publix", help="page title (default: publix)")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                    help="glob to skip, matched against names and root-relative paths; repeatable")
    args = ap.parse_args()

    root = args.root.resolve()
    index = (args.index or root / "index.html").resolve()
    if not index.is_file():
        print(f"error: {index} not found", file=sys.stderr)
        return 1

    skip = set()
    if index.parent == root or root in index.parents:
        skip.add(index.relative_to(root).as_posix())

    tree = scan(root, root, DEFAULT_EXCLUDES + args.exclude, git_dates(root), skip)
    tree["name"] = args.title
    manifest = {"title": args.title, "root": tree}

    # Escape every "<" so file names can never close the <script> element early.
    data = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

    page = index.read_text(encoding="utf-8")
    if not MANIFEST_RE.search(page):
        print(
            f'error: {index} has no supported manifest block '
            f'(<script type="application/json" id="publix-manifest"> or id="ib-manifest")',
              file=sys.stderr)
        return 1
    new = MANIFEST_RE.sub(lambda m: m.group(1) + data + m.group(3), page, count=1)
    new = STATIC_RE.sub(lambda m: m.group(1) + static_list(tree) + m.group(3), new, count=1)
    new = PAGE_TITLE_RE.sub(lambda m: f"<title>{html.escape(args.title)}</title>", new, count=1)

    files, folders, size = tally(tree)
    rel_index = os.path.relpath(index, Path.cwd())
    if new != page:
        index.write_text(new, encoding="utf-8")
        print(f"Indexed {files} files in {folders} folders ({human(size)}) -> {rel_index}")
    else:
        print(f"{rel_index} already up to date ({files} files in {folders} folders)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
