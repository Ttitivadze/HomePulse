# HomePulse Post-Deploy Smoke Test

Run through this checklist after deploying a new version to a live
host. Each step states exactly what to verify and flags non-obvious
failure modes. Report back which steps passed / failed, with a log
excerpt for anything that didn't.

Assumes either:
- **GHCR image deploy** (recommended from 2.1.0 onward):
  `docker compose pull && docker compose up -d`
- **Build-from-source deploy** (legacy): `docker compose up -d --build --force-recreate`

---

## 0. Pre-flight

- [ ] `cat /opt/HomePulse/VERSION` prints the version you just deployed.
- [ ] `docker ps --filter name=homepulse` shows status `healthy`
      within 60 s of startup. If stuck `starting`, check
      `docker logs homepulse` for the healthcheck failure.
- [ ] `docker logs --tail=50 homepulse` has no unhandled tracebacks
      during startup. A `warnings` line for unconfigured services is
      expected and fine.

## 1. Dashboard baseline

- [ ] `curl -s <host>:8450/api/health` returns `{"status":"ok"}`.
- [ ] Loading the UI in a browser renders every enabled section
      (Proxmox, Docker, Media Library, Streaming, Uptime, Infrastructure,
      HomePulse Host). Bookmarks appears only if admin added any.
      No section shows a 500 error card.
- [ ] Header shows the version number you expected.
- [ ] "Last updated" pill in the header refreshes every ~5 s.

## 2. Theme toggle (v2.0.0)

- [ ] Click the ☀/☾ icon. Dashboard recolours within one frame.
- [ ] Hard-reload the page. Theme persists (stored under `hp_theme`
      in `localStorage`).

## 3. Claude chat (v2.0.0)

- [ ] Open the chat panel. Status reads `Online` if `CLAUDE_API_KEY`
      is set, else `Offline`. Both are valid states.
- [ ] If configured, send `hello` — tokens stream in one-by-one.
- [ ] No `homepulse.claude` traceback in logs on successful chats;
      auth errors log a single WARNING line.

## 4. Docker container updates (v2.0.0)

- [ ] After ~60 s, cards backed by public Docker Hub images with a
      newer `latest` tag show an **Update** badge.
- [ ] Containers at the latest digest have **no** badge.
- [ ] Digest-pinned images (`nginx@sha256:…`) never show the badge.
- [ ] Operators running many containers: only ~3 uncached lookups per
      refresh (check `homepulse.docker_updates` DEBUG lines). Later
      refreshes fill in the rest as the 6 h cache populates.

## 5. Uptime Kuma (v2.0.0 + v2.1.0 deep-view tweaks)

**Ping view (no metrics token set)**
- [ ] Single card "Uptime Kuma — Online" with a hint line about
      setting `UPTIME_KUMA_METRICS_TOKEN`.

**Deep view (metrics token set)**
- [ ] Add `UPTIME_KUMA_METRICS_TOKEN=<key>` (key minted from Uptime
      Kuma's Settings → API Keys page) to `.env`, redeploy.
- [ ] Dashboard shows one card per monitor with a coloured dot.
- [ ] Header badge reads `X/Y` (up/total) and turns red when
      anything is down.

## 6. Infrastructure widget (v2.0.0 + v2.1.0 NAS mounts)

- [ ] Proxmox storages appear in the storage list.
- [ ] If `NAS_MOUNTS=/mnt/nas,/mnt/backup` is set **and** the volume
      is mounted into the container via `docker-compose.yml`, NAS
      paths appear at the top of the storage list with `type: mount`.
      Used / total bytes match `df -h` on the host.
- [ ] Backup cards show last vzdump per CT.
- [ ] SSL cert card shows days-until-expiry coloured by urgency.

## 7. Telegram notifications (v2.0.0)

- [ ] With Telegram configured: `curl -X POST <host>:8450/api/notifications/test`
      returns `{"status":"sent"}` and a message lands in the chat.
- [ ] Without Telegram configured: same curl returns **400** with a
      clear error body (no stack traces in the log).

## 8. Login rate limiting (v2.0.0)

- [ ] Log out, hit the login form with wrong credentials **six** times
      in <60 s. The 6th attempt returns HTTP 429.
- [ ] Wait 60 s. One correct login succeeds and the counter resets
      (next four wrong attempts are 401, not 429).

## 9. Settings — live preview (v2.0.0)

- [ ] Open *Settings → Appearance*. Change Accent colour → dashboard
      recolours immediately and a yellow chip "Preview active — Save
      to persist" appears next to the Save button.
- [ ] Close the overlay without saving → dashboard reverts.
- [ ] Re-open, change again, click Save → persists across hard refresh.

## 10. External API keys (v2.0.0 + v2.1.0 hardening)

- [ ] *Settings → API Keys → Create*. One-time banner shows the
      `hp_…` plaintext key. Copy it.
- [ ] List row shows only the prefix, created date, "Never" last-used.
- [ ] (Default) `curl <host>:8450/api/dashboard` still returns 200
      anonymously when `DASHBOARD_REQUIRE_AUTH=false`.
- [ ] Set `DASHBOARD_REQUIRE_AUTH=true` and redeploy:
      - Anonymous curl → **401**
      - `curl -H "X-API-Key: hp_..."` → **200**
      - Invalid key → **401**
      - After clicking *Revoke*, the same key curl → **401**
- [ ] **(v2.1.0)** `curl -X DELETE <host>:8450/api/settings/api-keys/0`
      with a valid JWT returns **422** (Path(ge=1) rejection), not
      the old 404.
- [ ] **(v2.1.0)** With `ALLOWED_ORIGINS` unset and auth on, a
      cross-origin browser request is blocked by CORS.

## 11. Bookmarks widget (v2.1.0)

- [ ] Fresh install with no bookmarks: the Bookmarks section is
      **hidden** on the dashboard (no empty placeholder).
- [ ] *Settings → Bookmarks → Add*: create one with Name, URL, optional
      icon (emoji or image URL), optional group.
- [ ] Dashboard now shows a Bookmarks section with that card; clicking
      it opens the URL in a new tab.
- [ ] **XSS gate**: try to add a bookmark with `javascript:alert(1)` as
      the URL — server returns **422**, bookmark is not created.
- [ ] Delete the bookmark from the admin panel — section hides again.

## 12. HomePulse self-monitoring (v2.1.0)

- [ ] New "HomePulse Host" section renders three cards: Memory, Load
      Average, Uptime.
- [ ] Memory bar colour: green <70 %, yellow 70–89 %, red ≥ 90 %.
- [ ] Load card shows 1m / 5m / 15m averages and CPU count. Bar
      normalised so load == cpu_count shows 100 %.
- [ ] Uptime card shows host uptime, process uptime, and HomePulse's
      own RSS. Process uptime resets to near-zero after each redeploy.
- [ ] On non-Linux hosts (shouldn't apply in production, but for
      reference): section reports "Self-monitoring (no /proc access)".

## 13. PWA install (v2.1.0)

- [ ] Visit the dashboard on a mobile browser. Browser prompts
      "Add to Home Screen" or shows an install hint.
- [ ] Installed app opens in standalone mode (no browser chrome),
      icon shows the HomePulse pulse graphic.

## 14. Container update registry auth (v2.1.0, optional)

- [ ] If you run any image from a private ghcr.io repo: set
      `REGISTRY_AUTH_JSON={"ghcr.io":{"username":"...","password":"ghp_..."}}`
      and redeploy. Update badges appear on those containers within a
      refresh cycle (first check is slow; subsequent are cached 6 h).

## 15. Regression: docker_links on error paths (v2.0.0)

This was Report #2's first bug. To verify:

- [ ] Temporarily break the Docker socket:
      `sudo chmod o-r /var/run/docker.sock` (revert right after!).
- [ ] Reload the dashboard. Docker card shows an error **but** the
      existing container cards still carry their clickable links.
- [ ] Restore permissions: `sudo chmod o+r /var/run/docker.sock`.

## 16. CI / release automation (v2.1.0)

- [ ] README badges at the top of the repo render green:
      - `tests` workflow on main
      - `docker-publish` workflow on main
- [ ] `docker pull ghcr.io/ttitivadze/homepulse:latest` succeeds on
      at least one `amd64` and one `arm64` host.
- [ ] For a tag release (`git tag v2.1.0 && git push origin v2.1.0`):
      `ghcr.io/ttitivadze/homepulse:2.1.0` and `:2.1` appear in the
      package registry within ~10 minutes.

---

## Reporting results

Paste a tick-list of what passed vs. failed. For any failure:

1. Step number
2. Observed behaviour
3. Relevant `docker logs --tail=100 homepulse` excerpt if the failure
   was server-side

I'll triage from there.
