# Deploying StudySager to Render

Much simpler than the Cloud Run path (`DEPLOY.md`) for small-scale use: one backend web service
plus one static-site frontend. No code changes were needed for this - the app already falls back
to local SQLite/disk whenever `DATABASE_URL`/`GCS_BUCKET_NAME` aren't set, which is exactly the
case here.

No CLI, no Cloud Shell - this is entirely done through Render's dashboard.

## Cost note - currently configured for the FREE tier

`render.yaml` is currently set to `plan: free` on the backend with no persistent disk, so this
costs **$0/month**. The real tradeoff: without a disk, the backend's local SQLite database,
uploaded resumes, and Chroma vector DB reset every time the service redeploys or spins down from
15 minutes of inactivity (free services sleep when idle and take ~30-60s to wake back up on the
next request) - fine for trying the app out, **not fine for keeping real user accounts/resumes**.

**When you're ready to make data permanent**, add this back under the backend service in
`render.yaml`, change `plan: free` to `plan: starter` (~$7/month), commit, and push - Render
auto-redeploys with the change:

```yaml
    disk:
      name: studysager-data
      mountPath: /var/data
      sizeGB: 1
```
and add an env var `APP_DATA_DIR` = `/var/data` alongside the others. Just ask and I'll make that
edit directly when you're ready.

## Deploy

1. Push the latest code to GitHub (from your Mac, in the `studysager` folder):
   ```
   git add -A
   git commit -m "Add Render deployment support"
   git push origin main
   ```

2. Go to [dashboard.render.com](https://dashboard.render.com), sign in (or sign up - it connects
   directly to GitHub).

3. Click **New +** → **Blueprint**.

4. Connect your GitHub account if you haven't already, then select the `Interview-Prep`
   repository (or whatever you named it) - Render will find `render.yaml` at the repo root
   automatically and show you a preview of both services it's about to create
   (`studysager-backend`, `studysager-frontend`).

5. Click **Apply**. Render builds both Docker/static images and deploys them - takes a few
   minutes. You'll land on a dashboard showing both services' status.

6. **Set your API keys** - these were intentionally left blank in `render.yaml` (`sync: false`)
   so they never touch git. Click into the `studysager-backend` service → **Environment** tab,
   and fill in real values for `GROQ_API_KEY`, `HF_API_TOKEN`, and optionally `GEMINI_API_KEY` /
   `DEEPSEEK_API_KEY` (same values as your local `backend/.env`). Saving triggers an automatic
   redeploy.

7. Once both services show "Live," open the frontend's URL (shown on its service page, something
   like `https://studysager-frontend.onrender.com`) - that's your app.

## If a service name doesn't come out as expected

Render appends a random suffix to the URL if your chosen service name is already taken globally
(e.g. `studysager-backend-a1b2.onrender.com` instead of the clean version) - Render tells you the
actual URL on each service's page. If that happens, the two services won't be able to reach each
other correctly since `render.yaml` hardcodes the expected URLs in `EXTRA_CORS_ORIGINS` and
`VITE_API_URL`. Fix: copy the real URLs from each service's dashboard page, then update those two
environment variables manually (Environment tab → edit the value) on the other service to match.

## After the first deploy

- **Redeploying after a code change**: just `git push` - Render auto-deploys on every push to
  `main` by default.
- **Logs**: each service's dashboard page has a **Logs** tab, streamed live.
- **Custom domain**: service page → **Settings** → **Custom Domains**.
- **Scaling up later**: if you outgrow this, `DEPLOY.md` has the Cloud Run + Cloud SQL + GCS path
  already built and ready (the same backend code supports both - it's purely env-var driven).

## Local development is unaffected

Nothing about `npm run dev` / local `uvicorn` changes - this deployment doesn't touch any of the
app's actual code, only adds `render.yaml` as a new file describing how Render should build and
run what's already there.
