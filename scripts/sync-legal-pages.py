#!/usr/bin/env python3
"""Regenerate tinypumper.com legal pages from their canonical source in greasebook-deploy.

HARD RULE (Greg, 2026-07-24): the privacy policy and terms of service live canonically
on greasebook.com (greasebook-deploy Jekyll posts). tinypumper.com/privacy/ and
tinypumper.com/terms/ are generated mirrors and MUST always match the canonical
content. Never hand-edit the generated pages — edit the canonical markdown in
greasebook-deploy, then run this script and commit both repos in the same session.
WHY: third parties evaluating TinyPumper need the legal pages on the TinyPumper
domain, but duplicate copies drift; generating the mirror from the source makes
drift impossible at edit time, and legal-pages-drift-check.yml (greasebook-deploy)
catches any miss after deploy.

Usage: python3 scripts/sync-legal-pages.py [path-to-greasebook-deploy]
(default source path: ../greasebook-deploy)
"""
import html
import re
import sys
from pathlib import Path

import markdown

TP_ROOT = Path(__file__).resolve().parent.parent
GB_ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else TP_ROOT.parent / "greasebook-deploy"
TEMPLATE_SOURCE = TP_ROOT / "60-day-love-it-or-shove-it-trial-terms" / "index.html"

PAGES = [
    {
        "key": "privacy",
        "source": GB_ROOT / "_posts" / "2016-08-19-greasebook-privacy-policy.md",
        "out": TP_ROOT / "privacy" / "index.html",
        "title": "GreaseBook & TinyPumper Privacy Policy | TinyPumper",
        "description": "How GreaseBook, LLC and TinyPumper, LLC collect, use, and protect your personal information across our websites, mobile applications, and connected hardware devices.",
        "canonical": "https://tinypumper.com/privacy/",
    },
    {
        "key": "terms",
        "source": GB_ROOT / "_posts" / "2026-07-24-greasebook-tinypumper-terms-of-service.md",
        "out": TP_ROOT / "terms" / "index.html",
        "title": "GreaseBook & TinyPumper Terms of Service | TinyPumper",
        "description": "The terms that govern use of our websites, the GreaseBook software, and TinyPumper services.",
        "canonical": "https://tinypumper.com/terms/",
    },
]

EXTRA_CSS = """
/* LEGAL BODY (generated pages) */
.legal-body>h2:first-of-type{font-size:clamp(26px,5vw,38px);text-align:center;margin:16px 0 8px;line-height:1.25}
.legal-body h3{margin-top:36px}
.legal-body hr{border:none;border-top:1px solid var(--border);margin:32px 0}
.legal-body table{width:100%;border-collapse:collapse;margin-bottom:16px}
"""

GENERATED_BANNER = (
    "<!-- GENERATED FILE — DO NOT HAND-EDIT.\n"
    "     Canonical source: greasebook-deploy/_posts (see scripts/sync-legal-pages.py).\n"
    "     Edit the canonical markdown, run the sync script, commit both repos. -->\n"
)


def extract_canonical(md_text: str, key: str) -> str:
    m = re.search(
        rf"<!-- LEGAL-CANONICAL-START:{key} -->(.*?)<!-- LEGAL-CANONICAL-END:{key} -->",
        md_text,
        re.S,
    )
    if not m:
        raise SystemExit(f"canonical markers for '{key}' not found")
    body = m.group(1)
    # drop the canonical-source explainer comment; keep everything else
    body = re.sub(r"<!-- CANONICAL SOURCE:.*?-->", "", body, flags=re.S)
    return body.strip()


def build_page(cfg: dict, template: str) -> str:
    md_text = cfg["source"].read_text()
    body_md = extract_canonical(md_text, cfg["key"])
    body_html = markdown.markdown(body_md, extensions=["md_in_html"])

    head = template.split("</head>")[0] + "</head>"
    head = re.sub(r"<title>.*?</title>", f"<title>{cfg['title']}</title>", head, flags=re.S)
    head = re.sub(
        r'<meta name="description" content="[^"]*">',
        f'<meta name="description" content="{html.escape(cfg["description"], quote=True)}">',
        head,
    )
    head = re.sub(
        r'<link rel="canonical" href="[^"]*">',
        f'<link rel="canonical" href="{cfg["canonical"]}">',
        head,
    )
    head = head.replace("</style>", EXTRA_CSS + "</style>")

    return f"""{GENERATED_BANNER}{head}
<body>

<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-5PQGM83" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>

<nav class="nav">
  <a href="https://tinypumper.com/">TinyPumper</a>
</nav>

<div class="container">

  <div class="section legal-body">
<!-- LEGAL-CANONICAL-START:{cfg['key']} -->
{body_html}
<!-- LEGAL-CANONICAL-END:{cfg['key']} -->
  </div>

</div><!-- /.container -->

<!-- CONTACT -->
<div class="contact">
  <h2>Questions?</h2>
  <p>Text, call, or email us anytime. Real folks on the other end.</p>
  <div class="contact-info">
    <a href="tel:18557867645">1-855-PUMP-OIL</a><br>
    <a href="mailto:tinypumper@greasebook.com">tinypumper@greasebook.com</a>
  </div>
</div>

<div class="footer">
  <p>&copy; 2026 TinyPumper. All rights reserved. &nbsp;|&nbsp; <a href="https://tinypumper.com/">Home</a> &nbsp;|&nbsp; <a href="/privacy/">Privacy</a> &nbsp;|&nbsp; <a href="/terms/">Terms</a></p>
</div>

</body>
</html>
"""


def main() -> None:
    template = TEMPLATE_SOURCE.read_text()
    for cfg in PAGES:
        out = build_page(cfg, template)
        cfg["out"].parent.mkdir(parents=True, exist_ok=True)
        cfg["out"].write_text(out)
        print(f"wrote {cfg['out'].relative_to(TP_ROOT)}")


if __name__ == "__main__":
    main()
