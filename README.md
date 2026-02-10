# Information Authenticator

An AI-powered web application that verifies user claims by searching academic and trusted sources and provides a confidence score with an AI-generated summary.

## Features
- Claim verification using academic APIs
- Confidence scoring (Supported / Moderate / Not Supported)
- AI-generated explanation using Gemini
- Simple Flask-based web interface
- SQLite backend for query history

## Tech Stack
- Python (Flask)
- Google Gemini API
- SQLite
- HTML/CSS

## How to Run
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
