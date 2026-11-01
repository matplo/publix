#!/usr/bin/env python3
"""Put videos back into an HTML exported from the Slides deck.

The web export replaces each video with its still picture. This script swaps
those pictures for the real videos (stored inside the HTML, so the file stays
self-contained) and adds a tiny script that plays each video once whenever its
slide comes up, stopping on the last frame.

Which pictures are replaced: those whose description (alt text) starts with
"Animation:", in slide order. Clips are matched to them in the order given,
unless a clip names its picture with  clip.mp4=<part of the description>.

Run in the folder with the export and the clip(s):

    python3 embed_video.py                         # newest export + morph_short.mp4 -> <name>-ev.html
    python3 embed_video.py deck.html               # a specific export
    python3 embed_video.py -c a.mp4 -c b.mp4       # two videos: 1st and 2nd "Animation:" picture
    python3 embed_video.py -c morph.mp4="ALICE logo" -c flow.mp4="elliptic flow"
"""
import argparse, base64, glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUFFIX = "-ev"          # output: <export>-ev.html  (ev = embedded video)
MARK = "data-embedded-video"


def pick_export():
    cands = [f for f in glob.glob("*.html")
             if not re.search(rf"({SUFFIX}|_video)\.html$", f)]
    if not cands:
        sys.exit("No exported .html found in this folder. Pass its path: python3 embed_video.py <export.html>")
    return max(cands, key=os.path.getmtime)


def find_file(name):
    for c in (name, os.path.join(HERE, name)):
        if os.path.exists(c):
            return c
    sys.exit(f"Video {name!r} not found (looked here and next to the script).")


def img_span(html, pos):
    a = html.rfind("<img", 0, pos + 4)   # the <img that starts at or before pos
    return a, html.find(">", a) + 1


def animation_imgs(html):
    """Spans of all <img> whose alt starts with 'Animation:', in document order."""
    return [img_span(html, m.start()) for m in re.finditer(r'<img\b[^>]*\balt="Animation:', html)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", nargs="?", help="exported deck .html (default: newest .html in this folder)")
    ap.add_argument("-o", "--out", help=f"output file (default: <export>{SUFFIX}.html)")
    ap.add_argument("-c", "--clip", action="append", metavar="FILE[=DESCRIPTION]",
                    help="video to embed; repeat for several (default: morph_short.mp4)")
    ap.add_argument("--blend", default="multiply", choices=["multiply", "normal"],
                    help="multiply hides a white video background on light slides (default); "
                         "use normal for videos on dark slides")
    args = ap.parse_args()

    src = args.export or pick_export()
    out = args.out or re.sub(r"\.html?$", "", src) + SUFFIX + ".html"
    html = open(src, encoding="utf-8").read()
    if MARK in html or "data-embedded-morph" in html:
        sys.exit(f"{src} already has embedded video(s); run on the original export.")

    clips = []
    for c in args.clip or ["morph_short.mp4"]:
        f, _, desc = c.partition("=")
        clips.append((find_file(f), desc.strip()))

    # decide which picture each clip replaces
    auto = animation_imgs(html)
    used, jobs = set(), []
    for f, desc in clips:
        if desc:
            i = html.find(desc)
            if i < 0 or html.rfind("<img", 0, i) < html.rfind(">", 0, i):
                sys.exit(f"No picture whose description contains {desc!r}.")
            span = img_span(html, i)
        else:
            free = [s for s in auto if s not in used]
            if not free:
                sys.exit(f"No picture left for {os.path.basename(f)}: the export has {len(auto)} "
                         'picture(s) described "Animation: …". Name one with  clip.mp4=<part of its description>.')
            span = free[0]
        if span in used:
            sys.exit(f"Two clips point at the same picture ({os.path.basename(f)}).")
        used.add(span)
        jobs.append((span, f))

    # replace from the end so earlier positions stay valid
    html_orig = html
    blend = ";mix-blend-mode:multiply" if args.blend == "multiply" else ""
    for (a, b), f in sorted(jobs, reverse=True):
        tag = html[a:b]
        assert tag.startswith("<img") and 'alt="' in tag, "internal error: wrong element picked"
        m = re.search(r'style="([^"]*)"', tag)
        style = m.group(1) if m else "width:100%;height:100%;display:block;object-fit:contain"
        m = re.search(r'alt="([^"]*)"', tag)
        alt = m.group(1) if m else ""
        b64 = base64.b64encode(open(f, "rb").read()).decode()
        html = html[:a] + (f'<video {MARK} muted playsinline preload="auto" aria-label="{alt}" '
                           f'style="{style}{blend}" src="data:video/mp4;base64,{b64}"></video>') + html[b:]

    k = html.rfind("</body>")
    html = html[:k] + PLAYER + html[k:] if k >= 0 else html + PLAYER
    open(out, "w", encoding="utf-8").write(html)
    for (a, b), f in sorted(jobs):
        alt = re.search(r'alt="([^"]{0,50})', html_orig[a:b]).group(1)
        sec = re.findall(r'aria-label="(Slide \d+)', html_orig[:a])
        print(f"  embedded {os.path.basename(f)} -> {sec[-1] if sec else '?'}: {alt}…")
    print(f"Done: {src} -> {out}")


PLAYER = r"""<script>
(function(){
  function setup(){
    Array.prototype.forEach.call(document.querySelectorAll('video[data-embedded-video]'),function(v){
      var slide=v.closest('.deck-slide')||v.parentElement, inView=false, active=false;
      function update(){
        var on=!slide.hasAttribute('data-off') && inView;
        if(on && !active){active=true; try{v.currentTime=0;}catch(e){} var p=v.play(); if(p&&p.catch)p.catch(function(){});}
        else if(!on && active){active=false; v.pause();}
      }
      if('IntersectionObserver' in window){
        new IntersectionObserver(function(es){es.forEach(function(e){inView=e.isIntersecting&&e.intersectionRatio>0.5;});update();},{threshold:[0,0.5,1]}).observe(slide);
      } else { inView=true; }
      new MutationObserver(update).observe(slide,{attributes:true,attributeFilter:['data-off','aria-hidden']});
      update();
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
</script>"""


if __name__ == "__main__":
    main()
