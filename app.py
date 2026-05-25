from flask import Flask
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "BonaEvents PR Panel Online 🔥"

# Railway usa questa variabile automaticamente
port = int(os.environ.get("PORT", 8080))

# IMPORTANTISSIMO:
app.run(host="0.0.0.0", port=port)