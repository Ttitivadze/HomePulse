# HomePulse v2.0.0 — Post-Deploy Smoke Test

Run through this checklist after pushing v2.0.0 to a live deployment.
Each step says exactly what to verify and flags any non-obvious failure
modes. Report back with which steps passed and which didn't.

Assumes the deployment flow from `docs/DEPLOY.md` / Report #1:
rebuild via `docker compose up -d --build --force-recreate`.

---

## 0. Pre-flight

- [ ] Confirm `cat /opt/HomePulse/VERSION` prints `2.0.0`.
- [ ] `docker ps --filter name=homepulse` shows status `healthy`
      within 60 s of the rebuild finishing.
- [ ] `docker logs --tail=50 homepulse` has no unhandled tracebacks
      during startup. A `warnings` line for unconfigured services is
      expected and fine.

## 1. Dashboard baseline

- [ ] `curl -s https://home.ttitivadze.dev/api/health` returns
      `{"status":"ok"}` (or the raw IP: `http://192.168.1.102:8450/api/health`).
- [ ] Loading the UI in a browser renders **all six sections**:
      Proxmox, Docker, Media Library, Streaming, Uptime, Infrastructure.
      No section shows a 500 error card.
- [ ] Header shows `HomePulse · 2.0.0`.
- [ ] "Last updated" pill in the header refreshes every ~5 s.

## 2. Theme toggle (v1.3.0 carry-over)

- [ ] Click the ☀/☾ icon. Dashboard recolours within one frame.
- [ ] Hard reload the page. Theme persists (stored under `hp_theme`
      in `localStorage`).

## 3. Claude chat

- [ ] Open the chat panel. Status line reads `Online` if
      `CLAUDE_API_KEY` is set, else `Offline` — both are valid states.
- [ ] Send `hello` (if configured). Response streams token-by-token;
      no "request failed" toast.
- [ ] Logs show `homepulse.claude` entries only on auth errors.

## 4. Docker container updates

- [ ] Wait ~60 s, then open any container card backed by a public
      Docker Hub image whose `latest` tag is older than the running
      image. An **Update** badge should appear next to the name.
- [ ] Containers running the current digest have **no** badge.
- [ ] Containers pinned by digest (`nginx@sha256:…`) never show the
      badge (`update_available: null`).
- [ ] For a host with many containers, only ~3 uncached lookups happen
      per refresh. You can verify by checking `docker logs homepulse`
      for `homepulse.docker_updates` DEBUG lines; later refreshes fill
      in the rest as the 6 h cache populates.

## 5. Uptime Kuma

**Ping view (no metrics token)**
- [ ] Single card "Uptime Kuma — Online" with a hint line about
      setting `UPTIME_KUMA_METRICS_TOKEN`.

**Deep view (metrics token set)**
- [ ] Mint an API key in Uptime Kuma: *Settings → API Keys → Create*.
- [ ] Add `UPTIME_KUMA_METRICS_TOKEN=<key>` to `.env`, redeploy.
- [ ] Section now renders one card per monitor with a coloured dot
      (green/red/yellow/purple) plus response-time and cert days.
- [ ] Header badge shows `X/Y` (up/total) and turns red when anything
      is down.

## 6. Infrastructure widget

- [ ] Storage bars show Proxmox storages.
- [ ] If `NAS_MOUNTS=/mnt/nas,...` is set **and the volume is mounted
      into the container**, NAS paths appear at the top of the storage
      list with `type: mount` and `used / total` matching `df -h`.
- [ ] Backup cards show last vzdump per CT.
- [ ] SSL cert card shows days-until-expiry coloured by urgency.

## 7. Notifications

- [ ] With Telegram configured:
      `curl -X POST https://home.ttitivadze.dev/api/notifications/test`
      returns `{"status":"sent"}` and a message arrives in the
      configured chat.
- [ ] With Telegram unconfigured: same curl returns **400** with a
      clear error body (no stack traces in the log).

## 8. Login rate limiting

- [ ] Log out, then hit the login form with wrong credentials
      **six** times in <60 s. The 6th attempt should return
      HTTP 429 *Too Many Requests*.
- [ ] Wait 60 s. A single correct login succeeds and the counter
      resets (next 4 wrong attempts are 401, not 429).

## 9. Settings — live preview

- [ ] Open *Settings → Appearance*. Change the Accent colour; the
      dashboard recolours immediately and a yellow chip
      **Preview active — Save to persist** appears next to the Save
      button.
- [ ] Click *Close* (NOT Save). Dashboard reverts to the previous
      accent colour — no flash of the unsaved state.
- [ ] Re-open, change again, click *Save*. Colour persists across a
      hard refresh.

## 10. External API keys

- [ ] *Settings → API Keys → Create*. A one-time banner shows the
      plaintext `hp_…` key. Copy it.
- [ ] The listing row shows only the prefix (`hp_XXXXXXXX…`), the
      created date, and "Never" under Last Used.
- [ ] (Default config) `curl https://home.ttitivadze.dev/api/dashboard`
      still returns 200 **anonymously** — `DASHBOARD_REQUIRE_AUTH` is
      false by default.
- [ ] Add `DASHBOARD_REQUIRE_AUTH=true` to `.env` and redeploy. Now:
      - Anonymous `curl` → 401
      - `curl -H "X-API-Key: hp_..."` → 200
      - Wrong key → 401
      - After clicking *Revoke* in the UI, Last Used is populated
        (from the prior curl). The same key curl → 401.

## 11. Private-registry auth for update checks *(optional)*

- [ ] If you run any image from a private ghcr.io repo:
      set `REGISTRY_AUTH_JSON={"ghcr.io":{"username":"...","password":"ghp_..."}}`,
      redeploy. The Update badge should start appearing on those
      containers within a few refresh cycles (cache TTL = 6 h so the
      first check after the config change is the slow one).

## 12. Regression: docker_links on error paths

This was Report #2's first bug. To verify:

- [ ] Temporarily break Docker socket permissions on the host
      (e.g. `sudo chmod o-r /var/run/docker.sock` — revert right
      after!).
- [ ] Reload the dashboard. Docker card shows an error **but the
      existing container cards still carry their clickable links**.
- [ ] Restore permissions: `sudo chmod o+r /var/run/docker.sock`.

---

## Reporting results

Paste a tick-list of what passed vs. failed. For any failure:

1. Which step number
2. The observed behaviour
3. A relevant `docker logs --tail=100 homepulse` excerpt if the
   failure was server-side

I'll triage from there.
