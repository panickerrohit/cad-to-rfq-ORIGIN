# Deploying

Web on Vercel, API on Render (Docker, because CadQuery needs system libraries). Both need the code in a GitHub repo.

## 1. API on Render
1. Push this `website/` folder to a GitHub repo.
2. Render dashboard > New > Blueprint > pick the repo. It reads `render.yaml` and creates `rfq-api` from `api/Dockerfile` with a 1 GB disk at `/data` for jobs.
3. Set `ANTHROPIC_API_KEY` when prompted. After step 2 below, set `CORS_ORIGINS` to your Vercel URL.
4. Check `https://<your-api>.onrender.com/health` returns `{"ok": true, ...}`.

## 2. Web on Vercel
1. Vercel > Add New > Project > same repo, **Root Directory = `web`**. Framework is detected as Next.js.
2. Environment variable `API_URL = https://<your-api>.onrender.com` (the `/api/*` rewrite forwards there).
3. Deploy.

## Before sharing the link
- There is no login yet: anyone with the URL can upload files and spend Claude credits. Add basic auth or Clerk before sending it beyond people you trust.
- Uploaded CAD sits on the Render disk until deleted.
- The Dockerfile was written and its Python stack tested outside Docker; the image build itself hasn't been run yet, so watch the first Render build log.
