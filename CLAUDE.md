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
