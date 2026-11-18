# DarGlobal + Wasalt Property Assistant

A small Streamlit RAG demo that indexes publicly available pages from DarGlobal and Wasalt, retrieves relevant passages with SQLite FTS5, and answers through OpenRouter with source links.

The chat includes suggested questions, a greeting/help response, clear search and answer progress, indexed page counts by website, a last-refresh time, and source previews. The sidebar explains what page types are included and why they are used.

The interface uses a restrained property-focused theme and separate DarGlobal/Wasalt brand cards. Restart Streamlit after changing `.streamlit/config.toml` so the theme is reloaded.

## Run locally

1. Install Python 3.12 or later and dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Set your OpenRouter key in the current PowerShell session:

   ```powershell
   $env:OPENROUTER_API_KEY = "your-key"
   ```

3. Start the app:

   ```powershell
   streamlit run app.py
   ```

4. Select **Refresh website data** in the sidebar, then ask a question.

The default model is `openrouter/free`. Set `OPENROUTER_MODEL` to another model available to your OpenRouter account if needed. The API key is only used by the server.

## Docker

```powershell
docker build -t dar-wasalt-assistant .
docker run --rm -p 8501:8501 `
  -e OPENROUTER_API_KEY="your-key" `
  -v "${PWD}\data:/app/data" `
  dar-wasalt-assistant
```

Open `http://localhost:8501`. Configure a persistent volume at `/app/data` when deploying so the indexed corpus survives restarts.

## Deploy on Render

The included `render.yaml` defines a Docker web service with a health check. Connect the GitHub repository to Render and deploy the blueprint, then set `OPENROUTER_API_KEY` in the Render service's environment settings. `OPENROUTER_MODEL` defaults to `openrouter/free`. After deployment, open the app and select **Update website information** to build its public-page index. Without a persistent disk, the index may need to be refreshed after a service restart or redeploy.

## Data collection and limitations

The app reads the sites' published sitemap URLs, checks each candidate page against the site's `robots.txt`, restricts requests to the two target domains, skips legal/policy pages, and limits collection to 80 pages per site at a measured request rate. It does not access sign-in-only pages or search endpoints. The initial index is empty until refreshed; collected pages are a limited public sample, not a complete or continuously updated listing database.

Answers are grounded in the local index and cite source URLs. Availability, prices, and other time-sensitive details should be verified on the linked source page.
