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
        for msg in copy:
            if is_new:                           # changed page: hard
                print(f"::error file={rel}::{msg}")
                fails += 1
            else:
                legacy += 1
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


if __name__ == "__main__":
    sys.exit(main())
