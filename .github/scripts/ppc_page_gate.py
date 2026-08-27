#!/usr/bin/env python3
"""PPC page gate (Greg, 2026-08-18) — blocks the defect classes that reached
production or nearly did during the 2026-08-18 lander build.

Each rule below exists because the failure ACTUALLY HAPPENED, not in theory:

  1. PAGE BLOAT — 149 of 216 live /ppc/ pages were 16.5 MB each because three
     MP4 videos were base64-inlined straight into the HTML (7.6 + 3.8 + 2.0 MB).
     Inlined bytes sit in the initial document, so the browser must download all
     16.5 MB before rendering anything and lazy-loading is impossible. These are
     pages we pay for clicks to, on rural mobile connections. Fixed 2026-08-18 by
     swapping every blob for a ../shared/<file> reference (2.4 GB -> 34 MB, each
     page 16.5 MB -> ~103 KB). This gate stops it coming back.

  2. TEMPLATING ARTIFACTS — an agent's regex replacement wrote literal `\\g<1>`
     and `\\g<2>` into two pages instead of the captured tags, so the hero
     primer, reciprocity line, and a section heading rendered as unstyled raw
     text with a visible `\\g<1>` prefix. The agent reported success. Caught only
     by independent verification.

  3. MISSING PRODUCER ANCHOR — negative disambiguation ("not for homeowners",
     heating-oil callouts) is BANNED (Greg purged it 2026-07-22), so the POSITIVE
     producer primer is the only thing gating consumer-intent traffic out. A page
     without one has no gate at all.

  4. BANNED COPY — em dashes (LLM tell), GreaseBook-only stats leaking into
     TinyPumper copy, well-count gating, pumper tracking/GPS language, and
     heating-oil negative disambiguation.

Exit 1 on any violation. Run with --fix-hint for remediation commands.
"""
from __future__ import annotations
import os, re, sys

MAX_PAGE_BYTES = 1_500_000     # ~103 KB is normal; 1.5 MB is a generous ceiling
                               # that still catches a re-inlined video instantly.
# New-page source budget (spec §4.14B, Greg 2026-08-19). The 1.5 MB ceiling is
# a corpus regression backstop; new/changed pages get the tighter budget so
# LP Experience never re-degrades by drift. WARN at the current template
# weight (~480 KB); hard-fail at 600 KB.
NEW_PAGE_WARN_BYTES = 480_000
NEW_PAGE_MAX_BYTES = 600_000
ROOT = os.environ.get("GITHUB_WORKSPACE", ".")

# STRUCTURAL rules — enforced repo-wide, hard fail. All currently clean, so any
# hit is a NEW regression. These are machine-checkable facts, not copy taste.
STRUCTURAL = [
    (r"data:(image|video)/[a-zA-Z0-9.+-]+;base64,",
     "base64 data URI inlined in HTML — reference ../shared/<file> instead "
     "(rule of 2026-08-18; this is what made 149 pages 16.5 MB each)"),
    (r"\\g<\d+>",
     "literal regex-substitution artifact left in the page (\\g<1>) — a broken "
     "template replacement shipped raw text into the hero"),
    (r"\{\{\s*\w+\s*\}\}",
     "unrendered template placeholder"),
]

# COPY rules — hard fail on pages this change touches, WARN on the legacy corpus.
# WHY split: as of 2026-08-18 the legacy pages carry 189 well-count violations and
# 121 em dashes predating these rules. Failing CI on all of them would either
# block every deploy or get the gate disabled, and a disabled gate protects
# nothing. New and edited pages are held to the full standard from day one; the
# legacy backlog is reported every run so it stays visible instead of forgotten.
COPY = [
    (r"\b\d+\s+to\s+[\d,]+\s+wells\b",
     "well-count gating — TinyPumper is a SCADA alternative at ANY scale "
     "(feedback_tinypumper_not_well_count_gated); say 'wells at any scale'"),
    (r"6%\s*pump[- ]to[- ]net|98%\s*success\s*rate|200%\s*money[- ]back",
     "GreaseBook-only stat in TinyPumper copy — TP's guarantee is 60-day "
     "money-back"),
    (r"not for (a )?(home|furnace|heating)|furnace fuel|heating oil|homeowner",
     "negative heating-oil disambiguation — banned 2026-07-22; the positive "
     "producer anchor does the gating"),
    (r"\btrack(ing)? your pumper\b|\bGPS\b",
     "pumper tracking/GPS language — never 'tracking' or 'GPS' about pumpers"),
]

REQUIRED = [
    ('name="robots" content="noindex, nofollow"',
     "/ppc/ pages must be noindex,nofollow"),
    ("tp-attr.js", "missing the engagement beacon (see beacon-gate)"),
]


def _strip_tags(html: str) -> str:
    t = re.sub(r"(?is)<[^>]+>", " ", html or "")
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"&nbsp;", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def claimed_phrase(html: str, path: str) -> str:
    """The phrase this page claims to target.

    Spec §4.14B: read it from the page's own H1/title, not a sidecar. Prefer
    the <title> text before a `|` brand suffix; fall back to the H1; last
    resort the directory slug. Competitor landers (`*-alternative`) return
    empty — Rule 9, never rebuild or re-key those from a template.
    """
    base = os.path.basename(os.path.dirname(os.path.abspath(path)))
    if "/ppc/" not in path.replace("\\", "/"):
        return ""
    if base.endswith("-alternative") or base == "ppc" or base.startswith("_"):
        # `_`-prefixed dirs are previews/scaffolding, not landers.
        return ""
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html or "")
    if m:
        title = _strip_tags(m.group(1))
        title = re.split(r"\s+\|\s+", title)[0].strip()
    h1 = ""
    m = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", html or "")
    if m:
        h1 = _strip_tags(m.group(1))
    # The canonical phrase is the slug (one-keyword lander). Title/H1 must
    # CONTAIN it; we don't take the whole H1 as the phrase (H1s are longer).
    slug_phrase = re.sub(r"[-_]+", " ", base).strip().lower()
    return slug_phrase


def _contains_phrase(hay: str, phrase: str) -> bool:
    """Alphanumeric-fold both sides so punctuation never fakes a miss:
    slug `247-oilfield-data` must match page text "24/7 Oilfield Data"
    (found live 2026-08-19 — the slash made an honest page a false positive)."""
    if not phrase:
        return True
    import re as _re
    fold = lambda s: _re.sub(r"[^a-z0-9]+", " ", (s or "").lower()
                             .replace("&", " and ")).split()
    h, p = fold(hay), fold(phrase)
    if p and any(h[i:i + len(p)] == p for i in range(len(h) - len(p) + 1)):
        return True
    # Squashed fallback: slug `247` is one token but the page writes "24/7"
    # (two tokens after folding). Comparing with all non-alphanumerics removed
    # entirely catches digit/punctuation splits without loosening word order.
    squash = lambda toks: "".join(toks)
    return squash(p) in squash(h) if p else True


def visible_text(html: str) -> str:
    """Strip script/style/comments so rules match COPY, not machinery.
    The tracking block legitimately contains an em dash in a comment banner."""
    h = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    return re.sub(r"<[^>]+>", " ", h)


def check_page(path: str) -> tuple[list[str], list[str]]:
    """Returns (structural_problems, copy_problems)."""
    problems: list[str] = []
    copy_problems: list[str] = []
    raw = open(path, encoding="utf-8", errors="replace").read()
    vis = visible_text(raw)
    size = os.path.getsize(path)
    if size > MAX_PAGE_BYTES:
        problems.append(
            f"page is {size/1048576:.1f} MB (ceiling {MAX_PAGE_BYTES/1048576:.1f} MB) "
            "— almost certainly a re-inlined asset")
    # Structural rules scan the RAW source; copy rules scan visible text only.
    for pat, msg in STRUCTURAL:
        if re.search(pat, raw, re.I):
            problems.append(msg)
    for needle, msg in REQUIRED:
        if needle not in raw:
            problems.append(msg)
    for pat, msg in COPY:
        if re.search(pat, vis, re.I):
            copy_problems.append(msg)
    if "\u2014" in vis:
        copy_problems.append(f"em dash in visible copy x{vis.count(chr(8212))} — "
                             "banned, use parens/periods/colons")
    if 'class="hero__primer' not in raw:
        copy_problems.append("no hero producer primer — the positive anchor that "
                             "gates consumer-intent traffic out (negative "
                             "disambiguation is banned)")
    # Every referenced shared asset must actually exist. NOTE template-lite.html
    # lives at ppc/ root but is COPIED INTO ppc/<slug>/, so its ../shared/ paths
    # are written for the destination depth, not its own.
    base = os.path.dirname(path)
    if os.path.basename(path) == "template-lite.html":
        shared_dir = os.path.join(base, "shared")
    else:
        shared_dir = os.path.join(base, "..", "shared")
    for ref in set(re.findall(r'\.\./shared/([A-Za-z0-9._-]+)', raw)):
        if not os.path.isfile(os.path.join(shared_dir, ref)):
            problems.append(f"references missing asset ../shared/{ref}")

    # QS-serving copy rules (spec §4.14B) — applied to changed/new pages by
    # main() the same way as the other copy rules. Viewport is an LP
    # Experience input; canonical-in-four-places is the LP-relevance half of
    # message match. Competitor landers skip the phrase check (Rule 9).
    if not re.search(r'(?i)<meta[^>]+name=["\']viewport["\'][^>]+width\s*=\s*device-width',
                     raw) and not re.search(
                         r'(?i)<meta[^>]+content=["\'][^"\']*width\s*=\s*device-width', raw):
        copy_problems.append("missing viewport meta (width=device-width) — "
                             "mobile usability is an LP Experience input")
    phrase = claimed_phrase(raw, path)
    if phrase:
        title = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
        if m:
            title = _strip_tags(m.group(1))
        meta = ""
        m = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                      raw)
        if not m:
            m = re.search(r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
                          raw)
        if m:
            meta = _strip_tags(m.group(1))
        h1 = ""
        m = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", raw)
        if m:
            h1 = _strip_tags(m.group(1))
        hero = ""
        m = re.search(r'(?is)<p[^>]*class=["\'][^"\']*hero__sub[^"\']*["\'][^>]*>(.*?)</p>', raw)
        if m:
            hero = _strip_tags(m.group(1))
        missing = [name for name, text in (("title", title), ("meta description", meta),
                                           ("H1", h1), ("hero subtext", hero))
                   if not _contains_phrase(text, phrase)]
        if missing:
            copy_problems.append(
                f"canonical phrase {phrase!r} missing from {', '.join(missing)} "
                "(LP-relevance half of message match)")
    return problems, copy_problems


def changed_pages(root: str) -> set:
    """Pages touched by this push/PR — held to the FULL standard including copy.
    Falls back to 'nothing changed' so a missing git context never turns the
    legacy backlog into a hard failure."""
    import subprocess
    base = os.environ.get("GATE_DIFF_BASE") or "HEAD~1"
    try:
        out = subprocess.run(["git", "diff", "--name-only", base, "HEAD"],
                             cwd=root, capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return set()
        return {os.path.normpath(os.path.join(root, f))
                for f in out.stdout.split() if f.endswith(".html")}
    except Exception:
        return set()


def main() -> int:
    ppc = os.path.join(ROOT, "ppc")
    if not os.path.isdir(ppc):
        print("no ppc/ directory — nothing to gate")
        return 0
    targets = [os.path.join(ppc, d, "index.html")
               for d in sorted(os.listdir(ppc))
               if os.path.isfile(os.path.join(ppc, d, "index.html"))]
    tmpl = os.path.join(ppc, "template-lite.html")
    if os.path.isfile(tmpl):
        targets.append(tmpl)
    touched = changed_pages(ROOT)
    fails = 0
    legacy = 0
    for p in targets:
        rel = os.path.relpath(p, ROOT)
        struct, copy = check_page(p)
        for msg in struct:                       # repo-wide, always hard
            print(f"::error file={rel}::{msg}")
            fails += 1
        is_new = os.path.normpath(p) in touched
        if is_new:
            size = os.path.getsize(p)
            if size > NEW_PAGE_MAX_BYTES:
                print(f"::error file={rel}::new/changed page is "
                      f"{size/1024:.0f} KB (ceiling {NEW_PAGE_MAX_BYTES/1024:.0f} KB)")
                fails += 1
            elif size > NEW_PAGE_WARN_BYTES:
                print(f"::warning file={rel}::new/changed page is "
                      f"{size/1024:.0f} KB (template weight ~"
                      f"{NEW_PAGE_WARN_BYTES/1024:.0f} KB; ceiling "
                      f"{NEW_PAGE_MAX_BYTES/1024:.0f} KB)")
        for msg in copy:
            if is_new:                           # changed page: hard
                print(f"::error file={rel}::{msg}")
                fails += 1
            else:
                legacy += 1
    # New/changed HTML outside /ppc/ (homepage, /reads/, legal, etc.) gets
    # the lightweight-payload rules so a non-lander GitHub Page cannot
    # re-introduce the 16.5 MB inlined-asset scar. Untouched legacy files
    # (the 3 MB homepage still carries data URIs) are NOT blocked until edited.
    ppc_norm = {os.path.normpath(p) for p in targets}
    for p in sorted(touched):
        if os.path.normpath(p) in ppc_norm:
            continue
        if not p.endswith(".html"):
            continue
        rel = os.path.relpath(p, ROOT)
        if rel.startswith(".github/") or "/assets/" in rel.replace("\\", "/"):
            continue
        if not os.path.isfile(p):
            continue
        raw = open(p, encoding="utf-8", errors="replace").read()
        size = os.path.getsize(p)
        if size > NEW_PAGE_MAX_BYTES:
            print(f"::error file={rel}::new/changed GitHub Page is "
                  f"{size/1024:.0f} KB (ceiling {NEW_PAGE_MAX_BYTES/1024:.0f} KB)")
            fails += 1
        if re.search(r"data:(image|video)/[a-zA-Z0-9.+-]+;base64,", raw, re.I):
            print(f"::error file={rel}::inlined base64 data URI — "
                  "assets must be files (2026-08-18 /ppc/ 16.5 MB scar)")
            fails += 1
        if not re.search(r'(?i)<meta[^>]+name=["\']viewport["\'][^>]+width\s*=\s*device-width',
                         raw) and not re.search(
                             r'(?i)<meta[^>]+content=["\'][^"\']*width\s*=\s*device-width', raw):
            print(f"::error file={rel}::missing viewport meta (width=device-width)")
            fails += 1
    if legacy:
        print(f"::warning::{legacy} copy issue(s) on legacy pages not touched by "
              "this change (em dashes / well-count gating predating the rules). "
              "Backlog — sweep separately; not blocking this deploy.")
    if fails:
        print(f"\nPPC page gate FAILED: {fails} blocking problem(s) across "
              f"{len(targets)} page(s).")
        print("Bloat fix: replace every data: URI with ../shared/<file> "
              "(assets are content-hash named; see the 2026-08-18 de-bloat).")
        return 1
    print(f"PPC page gate passed — {len(targets)} pages, 0 blocking problems "
          f"({legacy} legacy copy items tracked)")
    return 0


def self_test() -> int:
    """Planted-violation self-test (spec §6.1). Exit 1 if any plant is missed
    or did not land. A no-op plant makes a broken checker look clean — this
    false-negative mode occurred twice during the 2026-08-18 build."""
    # Import sibling-machine helper when running from Mission_Control; fall
    # back to an inline copy of the plants if ppc_machine isn't on sys.path.
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "..",
            ".github", "scripts")))
        import ppc_machine as PM
        fails = PM.page_planted_self_test(sys.modules[__name__])
    except Exception:
        # Running inside tinypumper-deploy CI — inline a minimal plant set so
        # the gate still proves itself without the sibling module.
        import tempfile
        fails = []
        clean = (
            '<!doctype html><html><head>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex, nofollow">'
            '<script src="/assets/js/tp-attr.js"></script>'
            '</head><body>'
            '<p class="hero__primer">Built for oil and gas producers.</p>'
            '<p>Wells at any scale.</p></body></html>'
        )
        with tempfile.TemporaryDirectory() as td:
            def w(name, html):
                p = os.path.join(td, name + ".html")
                open(p, "w").write(html)
                return p
            p = w("b64", clean.replace("</body>", "data:video/mp4;base64,AAAA</body>"))
            s, _ = check_page(p)
            if not s:
                fails.append("missed planted base64 data URI")
            p = w("re", clean.replace("producers.", r"\g<1> primer"))
            s, _ = check_page(p)
            if not s:
                fails.append("missed planted \\g<1>")
            p = w("em", clean.replace("producers.", "The leak — nobody talks about"))
            _, c = check_page(p)
            if not any("em dash" in x.lower() for x in c):
                fails.append("missed planted em dash")
    if fails:
        print("PPC page gate self-test FAILED:")
        for f in fails:
            print("  " + f)
        return 1
    print("PPC page gate self-test passed — planted defects caught")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
