#!/usr/bin/env python3
"""Embed an MP4 into an exported Slides HTML in place of an <img> (matched by alt text).

usage: python3 embed_video.py exported.html clip.mp4 "alt text fragment" out.html

The video is inlined as a data: URI (the export's CSP allows media-src data:),
plays once when its slide becomes the current one, and stops on its last frame.
"""
import base64, re, sys

src, clip, alt_frag, out = sys.argv[1:5]
html = open(src, encoding="utf-8").read()

i = html.find(alt_frag)
if i < 0:
    sys.exit(f"alt text not found: {alt_frag!r}")
a = html.rfind("<img", 0, i)
b = html.find(">", i) + 1
tag = html[a:b]
style = re.search(r'style="([^"]*)"', tag)
style = style.group(1) if style else "width:100%;height:100%;display:block;object-fit:contain;"
alt = re.search(r'alt="([^"]*)"', tag).group(1)

b64 = base64.b64encode(open(clip, "rb").read()).decode()
video = (f'<video data-embedded-morph muted playsinline preload="auto" '
         f'aria-label="{alt}" style="{style};mix-blend-mode:multiply" src="data:video/mp4;base64,{b64}"></video>')
html = html[:a] + video + html[b:]

script = r"""<script>
(function(){
  function setup(){
    var vids=document.querySelectorAll('video[data-embedded-morph]');
    Array.prototype.forEach.call(vids,function(v){
      var slide=v.closest('.deck-slide')||v.parentElement, inView=false, active=false;
      function isOn(){return !slide.hasAttribute('data-off') && inView;}
      function update(){
        var on=isOn();
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
k = html.rfind("</body>")
html = html[:k] + script + html[k:] if k >= 0 else html + script
open(out, "w", encoding="utf-8").write(html)
print("ok", len(html))
