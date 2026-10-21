#!/usr/bin/env python3
"""Page-weight gate, run before every deploy: greasebook-deploy checks the built site (_site) in
jekyll.yml; tinypumper-deploy (no build step) checks the repo itself in page-weight-gate.yml.
Same script in both repos; change both together.

WHY (Greg, 2026-10-21): many prospects open these pages on phones in rural and remote areas
with weak signal. On 2026-10-21 the homepage downloaded 18.8 MB on a phone, 12.9 MB of it
phone-demo videos loaded straight from GitHub and playing on open; every blog post embeds the
homepage, so the weight spread site-wide. These rules keep every page light; a page that breaks
one does not deploy.

Rules, checked on every built HTML page (markup inside <script>, <noscript> and comments is ignored):
1. HTML document at most 600 KB (same ceiling as the PPC lander gate).
2. No <video autoplay>, and no looping <video> outside the loader (a tap-to-play video with
   controls is fine). A looping video uses data-light-video (or the older data-lazy-autoplay):
   it has a poster (or data-overlay when it sits on its own data-bg thumbnail), no src on the tag, and its sources use data-src, so assets/js/gb-light-media.js
   plays it only on screen and only on a good connection.
3. Every looping video's file is on this site (no outside host) and at most 600 KB.
4. A page with a looping video or a data-bg thumbnail loads the shared loader
   (gb-light-media.js on greasebook.com, light-media.js on tinypumper.com).
5. At most 12 images load on open: <img> without loading="lazy" plus inline style
   background-image urls. Everything else loads as it scrolls in (loading="lazy" or data-bg).
Usage: check-page-weight.py [site_dir] (default _site). Exit 1 on any failure.
Folders skipped: .git, vendor, node_modules (never published).
"""
import os
import re
import sys

MAX_HTML = 600 * 1024
MAX_VIDEO = 600 * 1024
MAX_EAGER_IMAGES = 12

site = sys.argv[1] if len(sys.argv) > 1 else "_site"
fails = []

for root, dirs, files in os.walk(site):
    dirs[:] = [d for d in dirs if d not in (".git", "vendor", "node_modules")]
    for name in files:
        # template*.html are generator sources whose relative paths only resolve once copied
        # into ppc/<slug>/ (tinypumper-deploy ppc/template-lite.html); the copies are checked.
        if not name.endswith(".html") or name.startswith("template"):
            continue
        path = os.path.join(root, name)
        rel = os.path.relpath(path, site)
        html = open(path, errors="ignore").read()
        if len(html) > MAX_HTML:
            fails.append(f"{rel}: HTML is {len(html) // 1024} KB, over 600 KB")
        body = re.sub(r"<script\b.*?</script>|<noscript\b.*?</noscript>|<!--.*?-->", "", html, flags=re.S | re.I)

        loops = 0
        for m in re.finditer(r"<video\b([^>]*)>(.*?)</video>", body, re.S | re.I):
            attrs, inner = m.group(1), m.group(2)
            if re.search(r"\sautoplay\b", attrs, re.I):
                fails.append(f"{rel}: <video autoplay> plays on open; use data-light-video with data-src and a poster")
            marked = re.search(r"data-light-video|data-lazy-autoplay", attrs, re.I)
            if not marked:
                # A tap-to-play video (controls) is fine. A loop without the marker is ambient video
                # that skipped the loader and its checks.
                if re.search(r"\sloop\b", attrs, re.I) and not re.search(r"\scontrols\b", attrs, re.I):
                    fails.append(f"{rel}: looping <video> without data-light-video; it must go through the loader")
                continue
            loops += 1
            # data-overlay: the clip sits on its own thumbnail (data-bg), which is its still.
            if not re.search(r"\sposter=|\sdata-overlay\b", attrs, re.I):
                fails.append(f"{rel}: looping video without a poster")
            if re.search(r"\ssrc\s*=", attrs, re.I) or re.search(r"<source\b[^>]*\ssrc\s*=", inner, re.I):
                fails.append(f"{rel}: looping video has src; use data-src so it loads only on a good connection")
            for src in re.findall(r"""data-src\s*=\s*["']([^"']+)["']""", attrs + inner):
                if re.match(r"(https?:)?//", src):
                    fails.append(f"{rel}: looping video from {src}; host a light copy on this site")
                    continue
                clean = src.split("?")[0]
                f = (os.path.join(site, clean.lstrip("/")) if clean.startswith("/")
                     else os.path.normpath(os.path.join(os.path.dirname(path), clean)))
                if os.path.isfile(f) and os.path.getsize(f) > MAX_VIDEO:
                    fails.append(f"{rel}: {src} is {os.path.getsize(f) // 1024} KB, over 600 KB")
                elif not os.path.isfile(f):
                    fails.append(f"{rel}: {src} is missing")

        if (loops or re.search(r"\sdata-bg=", body)) and "light-media.js" not in html:
            fails.append(f"{rel}: has looping videos or data-bg thumbnails but does not load the light-media loader")

        imgs = re.findall(r"<img\b[^>]*>", body, re.I)
        eager = [i for i in imgs if not re.search(r"loading\s*=\s*[\"']lazy", i, re.I)]
        inline_bg = re.findall(r"style=\"[^\"]*background-image:\s*url\(", body, re.I)
        if len(eager) + len(inline_bg) > MAX_EAGER_IMAGES:
            fails.append(f"{rel}: {len(eager) + len(inline_bg)} images load on open (max {MAX_EAGER_IMAGES}); "
                         "add loading=\"lazy\" or use data-bg")

for f in fails:
    print(f"::error::{f}")
if fails:
    print(f"{len(fails)} page-weight failure(s)")
    sys.exit(1)
print("page-weight gate passed")
