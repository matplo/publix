# publix

Public artifacts served via GitHub Pages at https://matplo.github.io/publix/

Anything under `public/` is deployed on push to `main` (see `.github/workflows/static.yml`).

## The index page

`public/index.html` is a 3D file browser (three.js): folders are glowing nodes that unfold
into cards for their files. Click a folder to unfold it, or click a file to open it in a new tab.
A synced side panel adds search, type filters and a plain list. Links like `…/publix/#alice-logos`
open a folder directly.

The file list is generated: just drop files into `public/` and run

```sh
python3 tools/build_index.py          # rescans public/ and updates public/index.html
python3 -m http.server -d public      # preview at http://localhost:8000
```

The deploy workflow also runs the script, so the live site is always current even if you forget.
The script only rewrites the marked data blocks in `index.html`, so the page's look can be
edited by hand. Dot-files are skipped; use `--exclude 'glob'` to hide more.
