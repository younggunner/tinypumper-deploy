# tinypumper-deploy — page builder rules

## Engagement beacon (HARD RULE, Greg 2026-08-14)

Every published HTML page must load the engagement beacon:

```html
<script src="/assets/js/tp-attr.js"></script>
```

directly before `</head>`. This repo has no build step — the include goes in
every page file.

**WHY:** `tp-attr.js` feeds the `lander_engagement` telemetry (scroll depth,
active seconds, word count) that KVS keyword scoring, the weekly traffic-quality
digest, and paid-ads cut/hold decisions read. A page without it is invisible to
engagement scoring; deep-read rate is a first-class optimization signal per
Paid-Ads.md.

**Exempt:** meta-refresh redirect stubs (instant bounce; rows would be junk).

**Enforced:** `.github/workflows/beacon-gate.yml` fails the deploy on any
HTML page missing the include.

Design system rules for TinyPumper pages live in `Mission_Control/CLAUDE.md`
(warm cream palette, Libre Baskerville + Outfit, gold CTAs). Canonical beacon
rule + full WHY: `Mission_Control/docs/Infrastructure/Hosting/hosting_architecture.md`.

## Assets are FILES, never base64 (HARD RULE, Greg 2026-08-18)

Every image and video on a page is referenced as `../shared/<content-hash>.<ext>`.
**Never inline a `data:image/...;base64,` or `data:video/...;base64,` URI.**

**WHY:** 149 of 216 live `/ppc/` pages were **16.5 MB each** because three MP4
videos (7.6 + 3.8 + 2.0 MB) were base64-inlined into the HTML. Inlined bytes sit
in the *initial document*, so the browser must download all 16.5 MB before
rendering anything, and lazy-loading is impossible. These are pages we pay for
clicks to, frequently on rural mobile connections. Fixed 2026-08-18: every blob
swapped for a `../shared/` reference, verified byte-identical by MD5 before
replacing. Result: **2.4 GB → 34 MB**, each page **16.5 MB → ~103 KB**, with page
structure byte-identical once asset refs are normalised.

New assets go in `ppc/shared/` named by content hash (first 12 hex of MD5 +
extension), which is why identical assets are shared across pages for free.

`ppc/template-lite.html` is de-bloated too — anything built from it starts lean.

**Enforced:** `.github/workflows/ppc-page-gate.yml`.

## PPC page gate — what else it blocks

Structural rules (hard fail, repo-wide — all currently clean, so any hit is a new
regression):

- base64 data URIs (above)
- literal `\g<1>` regex-substitution artifacts. A copy agent's broken replacement
  wrote these into two pages, so the hero primer and a section heading rendered
  as unstyled raw text. The agent reported success; only independent verification
  caught it.
- unrendered `{{ placeholder }}`
- missing `noindex, nofollow` (every `/ppc/` page)
- missing `tp-attr.js` beacon
- a `../shared/` reference that does not resolve to a real file
- page over 1.5 MB

Copy rules (hard fail on pages a push touches, warning for the legacy backlog):

- em dashes in visible copy
- well-count gating (`2 to 2,000 wells`) — TinyPumper is a SCADA alternative at
  ANY scale; say "wells at any scale"
- GreaseBook-only stats in TinyPumper copy (6% pump-to-net, 98% success, 200%
  money-back). TP's guarantee is **60-day money-back**.
- negative heating-oil disambiguation — banned 2026-07-22; the **positive**
  producer primer does the gating, which is why a missing `hero__primer` is
  itself a violation
- "tracking"/"GPS" language about pumpers

The copy rules are split from the structural ones because the legacy corpus
carries ~310 pre-existing copy issues. A gate that fails every deploy gets
disabled, and a disabled gate protects nothing.
