# Release Tag Guide — `v1.2.0-alpha2-feature-freeze`

## Step 1: Save current state to GitHub

Use the **"Save to GitHub"** button in the Emergent chat input to push the current codebase (Phase A–J complete, 394 tests passing, feature-freeze declared) to your GitHub repo.

Emergent's GitHub integration handles the commit and push automatically. It does **not** create git tags.

## Step 2: Tag the freeze commit locally

Once the Save-to-GitHub push is complete, on your local machine:

```bash
# 1. Clone or update your local checkout of the repo
git clone <your-repo-url>   # or `git fetch --all` if already cloned
cd <repo>

# 2. Verify the freeze commit is on main
git log -1 --oneline

# 3. Create an annotated tag on the current HEAD
git tag -a v1.2.0-alpha2-feature-freeze -m "Backend feature freeze — Phase A–J complete.

- 100 legacy routers online
- 17 orchestrator tasks registered
- Meta-Learning + Factory Self-Evaluation both default OBSERVE
- 394 pytests passing (Phase A–J with -n 0)
- Structural non-modification invariants intact

Next: VPS deployment → Paper Broker Validation → 24h + 72h Tier 5 → Production sign-off → Frontend."

# 4. Push the tag to origin
git push origin v1.2.0-alpha2-feature-freeze

# 5. Verify
git ls-remote --tags origin | grep feature-freeze
```

## Step 3 (optional): GitHub Release

If you want a formal release page on GitHub:

1. Navigate to `https://github.com/<owner>/<repo>/releases/new`.
2. Choose tag `v1.2.0-alpha2-feature-freeze`.
3. Title: "Strategy Factory v1.2.0-alpha2 — Backend Feature Freeze".
4. Description: paste `docs/BACKEND_FEATURE_FREEZE_v1.2.0-alpha2.md` contents.
5. Attach:
   - Full pytest summary (paste output of the 394-test regression run).
   - Boot log lines confirming the invariants.
6. Publish as **pre-release** (this is alpha, not GA).

## Post-tag actions

- Continue to `docs/POST_FREEZE_DEPLOYMENT_CHECKLIST.md`.
- Do not rebase or amend the tagged commit. Any fixes go on top.
