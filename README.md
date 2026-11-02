# SlideWala — Phase 3 (Premium AI Presentation Maker)

SlideWala turns a topic into a full presentation: structured content, relevant Wikimedia images, real PowerPoint (.pptx) export, real PDF export, and a premium slide-by-slide preview — all in one Flask app.

Built with Flask, OpenRouter (any OpenAI-compatible API), python-pptx, ReportLab, and Pillow. Deploys to Render via gunicorn.

## What's included in Phase 3
- AI slide generator with topic, audience, tone, theme, and slide count controls.
- Real images from Wikimedia Commons per slide.
- Real PowerPoint export (.pptx) editable in PowerPoint and Google Slides.
- Real PDF export (.pdf) with one slide per page and speaker notes appended.
- Premium, mobile-first UI with live preview and keyboard navigation.

## Windows setup
1. Install Python 3.10+.
2. Extract the project folder.
3. Create a virtual environment: `py -m venv .venv`
4. Activate it: `.\.venv\Scripts\activate`
5. Install dependencies: `python -m pip install -r requirements.txt`
6. Copy `.env.example` to `.env` and add your real `OPENROUTER_API_KEY`.
7. Run: `python app.py`
8. Open http://127.0.0.1:5000

## How the AI key works
The `OPENROUTER_API_KEY` is read on the server only. It is never sent to the browser. If it is missing, `/health` shows `ai_configured: false` and `/api/generate` returns a helpful 503 message.

## Deploying to Render
1. Push to GitHub.
2. In Render, create a Web Service from your repo.
3. Set Build Command: `pip install -r requirements.txt`
4. Set Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 4 --timeout 180`
5. Add environment variables: `OPENROUTER_API_KEY`, `AI_BASE_URL`, `AI_MODEL`, `AI_TIMEOUT`, `SECRET_KEY`, `WIKIMEDIA_USER_AGENT`.
6. Deploy and visit `/health` to confirm `phase: 3`.

## Local smoke tests (run these after install)
| Test | Expected |
|------|----------|
| `/health` | `{"status":"ok","phase":3,"ai_configured":true}` |
| Empty topic | Toast error message |
| Generate 5 slides | Loading overlay then rendered deck |
| Download PPTX | File opens in PowerPoint |
| Download PDF | File opens in any PDF reader |
| Resize to 375px | No horizontal scroll |

**Honest note:** I cannot run Python in this environment. Every function is written against current documented APIs, but the smoke tests above are what you must run to confirm it works on your machine. If a test fails, the error will name the file to inspect.
