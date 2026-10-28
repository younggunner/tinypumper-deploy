# Why `.greptile/config.json` says what it says

Decided by Greg on 2026-10-27, after the GreaseBook org hit its monthly Greptile flex limit. The full numbers are in the AR Engine project's `docs/greptile-usage-review.md`. The rules for agents live in the `astra-grok-delivery` skill, step 9.

- **`"effort": "base"`**: every review costs 1 credit. In Greptile's tier comparison an explicit tier beats Auto, so if someone sets the dashboard to Auto, PRs here still won't run at Plus (3 credits) or Apex (10 credits). From Sept 15 to Oct 27, all 395 app reviews ran at Base and still found P1s on 181 PRs. Revisit if a Base review misses a defect that a deeper tier would have caught on a money path.
- **`"autoReview": ["open"]`**: the app reviews a PR once, when it is opened or marked ready for review, and not on every push. This matches the dashboard today. Pinning it here means a dashboard change can't quietly turn on reviews for every push. Open a draft PR while work is still landing, then mark it ready to get the one review.
- **`"ignoreKeywords": "[no-greptile]"`**: put `[no-greptile]` in a PR title or description and the app skips that PR. Use it in two cases. First, low-risk PRs (docs, page copy, data files, test-only changes), which per skill step 9 get no paid review. Second, branches that already got their paid review from the CLI gate, so the same change isn't billed twice. On Oct 25 to 27, 25 of the 29 branches the CLI reviewed were reviewed again by the app when their PR opened.

Greptile reads this file from the PR's source branch, so it applies to branches cut from `main` after this merges. The account-wide settings (dashboard tier, triggers) are Greg's to change in the Greptile dashboard; agents never change them.
