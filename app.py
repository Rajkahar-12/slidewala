
import os
from flask import Flask, render_template

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/health")
def health():
    return {
        "status": "ok",
        "app": "SlideWala",
        "phase": 1
    }

if __name__ == "__main__":
    app.run(debug=True)
