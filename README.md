# SlideWala — Phase 2 (AI PowerPoint Maker)

SlideWala turns a topic into a slide-by-slide outline (titles, bullets and
speaker notes) using any **OpenAI-compatible Chat Completions API**.

## What's included in Phase 2

- Real AI generation via `/api/generate` (no fake content).
- Audience selector (Student / Professional).
- Slide count selector: **5, 8, 10, or 12**.
- Presentation preview: every slide, with numbered cards, bullet lists,
  and expandable **speaker notes**.
- Working **Copy outline** button (copies everything, including speaker notes).
- Friendly loading, error, and empty-topic messages.
- `/health` endpoint that also reports whether the AI key is configured.
- Preserved Phase 1 design, purple theme, layout, and responsiveness.

## Phase 3 (planned, not in this build)

Accounts, database storage, editable slides, PPTX/PDF export, template gallery.

## Project structure

```text
slidewala/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── Procfile
├── render.yaml
├── README.md
├── templates/
│   └── index.html
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```

## Windows setup (beginner friendly)

1. Install **Python 3.10+** from python.org (tick **"Add Python to PATH"**).
2. Extract the project folder, e.g. `C:\Users\you\Desktop\slidewala`.
3. Open that folder in **VS Code** or open **Command Prompt** there.
4. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

5. Activate it:

   ```powershell
   .\.venv\Scripts\activate
   ```

6. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

7. Create your `.env` from the template:

   ```powershell
   copy .env.example .env
   ```

8. Open `.env` and paste your real `AI_API_KEY` (see the next section).

9. Run the site:

   ```powershell
   python app.py
   ```

10. Open **http://127.0.0.1:5000** in your browser.

## How to configure the AI API key

Get a key from any OpenAI-compatible provider, e.g. OpenAI
(https://platform.openai.com/api-keys). Then:

1. Open `.env`.
2. Set:

   ```env
   AI_API_KEY=sk-your-real-key-here
   AI_BASE_URL=https://api.openai.com/v1
   AI_MODEL=gpt-4o-mini
   AI_TIMEOUT=60
   ```

3. Save the file and **restart** `python app.py`.

The key stays on the server. It is never sent to the browser and never
appears in HTML or JavaScript.

**If you see "AI is not configured yet":** `.env` is missing the key, or the
server was not restarted after you added it, or you're running from a
different working directory.

## Test Phase 2 locally

- Homepage loads → yes.
- `/health` returns JSON → yes (shows `"ai_configured": true` after setup).
- Empty topic → friendly error message.
- Topic + 5 slides → 5 slide cards render with bullets and notes.
- **Copy outline** copies the full presentation.
- **Generate another** clears the form.
- Temporarily break `AI_API_KEY` → you get a friendly server-side error, not a crash.

**Tested locally without a key:** validation, `/health`, loading UI, results
rendering (using a mock response), copy, reset, error handling.
**Needs a real AI key:** actual slide content generation.

## Deploying to Render

1. Push this folder to GitHub.
2. On https://render.com → **New → Web Service** → connect the repo.
3. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Environment:** Python 3
4. Under **Environment → Add Environment Variable**, add:

   | Key | Value |
   |---|---|
   | `SECRET_KEY` | auto-generate (Render can generate) |
   | `AI_API_KEY` | your real key |
   | `AI_BASE_URL` | `https://api.openai.com/v1` |
   | `AI_MODEL` | `gpt-4o-mini` |
   | `AI_TIMEOUT` | `60` |

5. Deploy. Visit `/health` on your Render URL to confirm.

## Security notes

- The AI key is **server-only**. Never put it in HTML/JS.
- Never commit `.env` (it's in `.gitignore`).
- Rotate the key immediately if it's ever exposed.
- In Phase 3 we'll add auth, per-user keys, and rate limiting.
