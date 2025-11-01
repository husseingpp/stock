```markdown
# Stock Research Dashboard

A simple, professional web application to look up a stock symbol (e.g., AAPL, MSFT, TSLA) and retrieve key financial data and reports. Built with Flask (Python) on the backend and a minimal HTML/CSS/JavaScript frontend. Uses yfinance for data retrieval and SQLite to persist recent searches.

Features
- Fetch company name, market cap, revenue, net income, P/E ratio, sector, and links to investor/SEC pages.
- Revenue history chart (last up to 5 years) using Chart.js.
- Recent searches stored in SQLite.
- Export financial summary to Excel (XLSX) or CSV.
- Download results as PDF from the browser (client-side using jsPDF).
- Error handling for invalid symbols and missing data.

Quick start (local)
1. Clone the repo
2. Create a virtualenv and activate it (recommended)
   - python -m venv venv
   - source venv/bin/activate  (macOS / Linux)
   - venv\Scripts\activate     (Windows)
3. Install dependencies:
   - pip install -r requirements.txt
4. Run the Flask app:
   - FLASK_APP=app.py flask run
   - (or) python app.py
5. Open http://127.0.0.1:5000 in your browser.

Notes
- This app uses yfinance. yfinance scrapes Yahoo Finance and is fine for small-scale personal use. For production or heavy use, consider using a paid financial data API (Financial Modeling Prep, Alpha Vantage, IEX Cloud, etc.).
- The "Latest annual report" link uses the company's website (if available) and an SEC search link as fallback.
- This project intentionally keeps API keys out; if you choose to use an API requiring a key, add .env handling and keep credentials secret.

Files
- app.py: Flask backend with API endpoints and SQLite persistence.
- templates/index.html: Frontend page.
- static/css/styles.css: Styling.
- static/js/app.js: Frontend logic (fetch API, Chart.js, jsPDF integration).
- requirements.txt: Python dependencies.

License
- MIT-style (adapt as needed)
```