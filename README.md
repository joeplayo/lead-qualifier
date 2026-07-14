# Solar Lead Qualifier

AI-powered lead scoring for solar sales leads. Two modes:

- **Score a Lead** — fill out a form, get an instant score/status/next action.
- **Run Sheet Batch** — scans a connected Google Sheet for unscored leads and
  processes them all (this is the original batch workflow).

## Project structure

```
app.py         Streamlit UI (start here)
qualifier.py   Core LLM scoring logic (no UI, no sheets)
sheets.py      Google Sheets read/write
main.py        Original CLI batch script (still works standalone)
```

## Local setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create `.streamlit/secrets.toml` (this file is gitignored — never commit it):
   ```toml
   GROQ_API_KEY = "your-groq-key-here"
   ```

3. If using batch/sheet mode, put your Google service account JSON at
   `credentials/service_account.json` (also gitignored).

4. Run it:
   ```
   streamlit run app.py
   ```

## Deploying (so sales reps get a link, not a file)

1. Push this repo to GitHub. **Double-check `credentials/` and any `.env`
   files are NOT committed** — check `.gitignore` is doing its job before
   you push.
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → point
   it at this repo and `app.py`.
3. In the app's Settings → Secrets, paste:
   ```toml
   GROQ_API_KEY = "your-groq-key-here"
   ```
   For batch mode, you'll also need to get the service account JSON into
   the deployed environment securely — either paste its contents as a
   secret and write it to disk on startup, or skip batch mode in the
   hosted version and keep it as a local-only script for now.
4. Share the resulting `*.streamlit.app` URL with your sales team.

## Notes

- The single-lead form doesn't require Google Sheets access at all — it's
  the simplest path to a usable tool for reps who just want a quick score.
- Batch mode requires sheet credentials and matches the original
  `main.py` behavior exactly.
