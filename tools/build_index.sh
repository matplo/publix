#!/usr/bin/env bash
# Regenerate public/index.html with index-browser (https://pypi.org/project/index-browser/).
#
#   tools/build_index.sh              # refresh public/index.html
#   tools/build_index.sh --serve      # …and preview it at http://127.0.0.1:8000
#   tools/build_index.sh --check      # exit 1 if the page is out of date
#
# Extra arguments are passed straight to index-browser (see `index-browser --help`).
# Pin a version with INDEX_BROWSER_VERSION=0.1.0. tools/build_index.py is the older,
# self-contained generator; it is kept for now.
set -euo pipefail

cd "$(dirname "$0")/.."

spec="index-browser${INDEX_BROWSER_VERSION:+==$INDEX_BROWSER_VERSION}"
if command -v pipx >/dev/null 2>&1; then
  run=(pipx run --spec "$spec" index-browser)
elif command -v uvx >/dev/null 2>&1; then
  run=(uvx --from "$spec" index-browser)
else
  echo "build_index.sh: needs pipx or uvx (pip install pipx, or see https://docs.astral.sh/uv/)" >&2
  exit 2
fi

args=(public -t publix --link https://github.com/matplo/publix)

# The page made by build_index.py uses different markers, so index-browser won't update it
# in place; the first run replaces it with index-browser's own page.
if [[ -f public/index.html ]] && ! grep -q 'id="ib-manifest"' public/index.html; then
  echo "build_index.sh: public/index.html is not an index-browser page yet; replacing it (--fresh)" >&2
  args+=(--fresh)
fi

exec "${run[@]}" "${args[@]}" "$@"
