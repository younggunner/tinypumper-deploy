# TinyPumper Website — GitHub Pages Deploy

This folder contains the static HTML files for **tinypumper.com**, deployed via GitHub Pages.

## Structure

```
tinypumper-deploy/
├── CNAME                 # Custom domain → tinypumper.com
├── index.html            # Main homepage (TODO: pull from NameHero)
├── approved/
│   └── index.html        # Booking/approved page (quiz.tinypumper.com/approved iframes this)
└── assets/               # Images, CSS, JS assets (TODO: pull from NameHero)
```

## Deploy

This folder is deployed as its own GitHub repo with GitHub Pages enabled.

```bash
# From this directory:
git add -A && git commit -m "Update site" && git push
```

GitHub Pages auto-deploys on push. Changes go live in ~60 seconds.

## Initial Setup

See `hosting_and_deployment.md` for the full migration guide from NameHero to GitHub Pages.
