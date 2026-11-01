# SlideWala — Phase 1

A Flask-based foundation for a presentation-making website for students and professionals.

## Included in Phase 1
- Responsive landing page
- Student / Professional audience selector
- Topic input with basic validation and preview feedback
- Flask health-check endpoint
- Clean separation of templates, CSS and JavaScript

**Important:** This phase is the website foundation. Real AI generation, slide editing, accounts, database storage and PPTX/PDF export are planned for later phases. No fake AI generation is included.

## Windows setup

1. Install Python 3.10 or newer.
2. Extract `SlideWala-Phase1.zip`.
3. Open the extracted `slidewala` folder in VS Code or Command Prompt.
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

7. Start the website:

   ```powershell
   python app.py
   ```

8. Open **http://127.0.0.1:5000** in your browser.

## Test Phase 1

- Open the homepage and check that the SlideWala page loads.
- Click **For students** and **For professionals**; the selected card and label should change.
- Leave the topic empty and click Continue; a validation message should appear.
- Enter a topic and click Continue; a Phase 2 message should appear.
- Open **http://127.0.0.1:5000/health**; it should return JSON with `"status": "ok"`.

## Project structure

```text
slidewala/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── templates/
│   └── index.html
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```

## Security note

Do not put API keys in HTML or JavaScript. Phase 2 will read the real AI API key from a local `.env` file on the Flask backend.
