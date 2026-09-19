# Scheduling the digest

## Why this is set up the way it is

GitHub Actions `schedule` (cron) triggers are **best-effort**. GitHub deprioritizes
scheduled jobs during high load — worst of all at the top of the hour (`:00`) — and
runs can be delayed by **hours** or skipped entirely. Our old schedule fired at
`12:00 / 13:00 / 14:00 UTC` (all `:00`) and was routinely landing 2–5 hours late.

## Current approach: crons set early, to be absorbed by the delay

The external trigger below was documented but **never set up** — every run to date has
been a `schedule` event. Moving to odd, off-peak minutes did not fix the delay. Measured
over 20 days (Aug 30 – Sep 18, 2026), the first run of the day landed a **median of ~4h10
after its cron time** (min 3h05, max 7h15), so digests arrived 9:30 AM – 1:30 PM ET.

The delay is large but fairly *consistent*, so the crons are now set ~4h **before** the
desired send time and left to be absorbed by the queue. This does not make the digest
stale: the job fetches when it actually dequeues (~10:30 UTC / 6:30 AM ET), not at cron
time. Two regimes are covered:

- **Queue delayed (typical):** the `06:22 UTC` attempt dequeues around `10:30 UTC`.
- **Queue empty (occasional):** the early attempts are blocked by the `EARLIEST_SEND_UTC`
  floor (`10:00 UTC` = 6:00 AM EDT / 5:00 AM EST) so they can't email at 2 AM ET, and the
  `10:22 UTC` attempt — which is past the floor — sends on time instead.

The **skip-if-already-ran** guard ensures only the first eligible run of the day actually
sends; the rest no-op. The crons run in UTC (no DST), so send time drifts ~1 hour between
seasons.

If this still proves too unreliable, the upgrade is the external trigger below: it calls
the GitHub API to *dispatch* the workflow, and dispatch events aren't subject to the
schedule queue, so they fire promptly. cron-job.org supports a timezone, so it tracks
EDT/EST automatically.

## Set up the primary external trigger (~5 minutes)

### 1. Create a fine-grained GitHub token

GitHub → Settings → Developer settings → **Fine-grained personal access tokens** → Generate new token:

- **Resource owner:** your account
- **Repository access:** Only select repositories → `cunningmatt5/cre-daily-digest`
- **Permissions → Repository permissions → Actions:** **Read and write**
  (this is the only permission needed — it's what `workflow_dispatch` requires)
- **Expiration:** your choice (set a reminder to rotate)

Copy the token (starts with `github_pat_…`). It is **not** stored in this repo — it lives only in the external scheduler.

### 2. Verify the dispatch works (optional but recommended)

```bash
curl -i -X POST \
  -H "Authorization: Bearer github_pat_YOUR_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/cunningmatt5/cre-daily-digest/actions/workflows/daily_digest.yml/dispatches \
  -d '{"ref":"master"}'
```

A **`204 No Content`** response = success; a run should appear under the repo's Actions tab.

### 3. Create the scheduled job on cron-job.org

Sign up (free) at https://cron-job.org, then **Create cronjob**:

- **Title:** CRE Digest trigger
- **URL:** `https://api.github.com/repos/cunningmatt5/cre-daily-digest/actions/workflows/daily_digest.yml/dispatches`
- **Schedule:** Every day at **06:30**, **timezone `America/New_York`** (DST-handled for you)
- **Advanced / Request settings:**
  - **Request method:** `POST`
  - **Request body:** `{"ref":"master"}`
  - **Headers:**
    - `Authorization: Bearer github_pat_YOUR_TOKEN`
    - `Accept: application/vnd.github+json`
    - `X-GitHub-Api-Version: 2022-11-28`
    - `Content-Type: application/json`
- Enable notifications on failure (so you hear if the trigger ever breaks).

Save and enable. Tomorrow it should dispatch at 6:30 AM ET; the fallback cron covers you if it doesn't.

## Changing the time later

- **Primary:** edit the time/timezone on the cron-job.org job.
- **Fallback:** edit the `cron:` lines in `.github/workflows/daily_digest.yml` (remember they're **UTC**: EDT = UTC−4, EST = UTC−5, and avoid `:00`).
