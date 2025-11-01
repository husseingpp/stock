#!/usr/bin/env python3
"""
Flask backend for the Stock Research Dashboard.

Endpoints:
- GET /                 -> serves the frontend (index.html)
- GET /api/<symbol>     -> returns JSON with financial data for <symbol>
- GET /api/recent       -> returns recent searches from SQLite
- GET /export/<symbol>  -> export results as CSV or XLSX (?format=csv|xlsx)
"""

import json
import sqlite3
import io
import datetime
from typing import List, Dict, Any, Optional

from flask import (
    Flask,
    jsonify,
    request,
    send_file,
    render_template,
    g,
)
import yfinance as yf
import pandas as pd

DB_PATH = "searches.db"

app = Flask(__name__, static_folder="static", template_folder="templates")


def get_db():
    """
    Get a sqlite3 connection (simple wrapper). Ensures the table exists.
    """
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        # Ensure table exists
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                company TEXT,
                data_json TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )
        db.commit()
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def save_search(symbol: str, company: str, data: Dict[str, Any]) -> None:
    """
    Save a search record into SQLite. Stores the returned JSON.
    """
    db = get_db()
    db.execute(
        "INSERT INTO searches (symbol, company, data_json, timestamp) VALUES (?, ?, ?, ?)",
        (symbol.upper(), company, json.dumps(data), datetime.datetime.utcnow().isoformat() + "Z"),
    )
    db.commit()


def fetch_recent(limit: int = 10) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db.execute("SELECT id, symbol, company, data_json, timestamp FROM searches ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    results = []
    for r in rows:
        results.append(
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "company": r["company"],
                "data": json.loads(r["data_json"]) if r["data_json"] else None,
                "timestamp": r["timestamp"],
            }
        )
    return results


def dollars_or_none(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def find_row_like(df: pd.DataFrame, substrings: List[str]) -> Optional[str]:
    """
    Try to find an index label in df that contains one of substrings (case-insensitive).
    Returns the matching index label or None.
    """
    if df is None or df.empty:
        return None
    labels = [str(l).lower() for l in df.index]
    for s in substrings:
        s = s.lower()
        for i, lab in enumerate(labels):
            if s in lab:
                return df.index[i]
    return None


def extract_revenue_history(financials: pd.DataFrame, years: int = 5) -> List[Dict[str, Any]]:
    """
    Extract last N years of revenue from financials DataFrame (columns are periods).
    Returns list of {year: YYYY, revenue: int}
    """
    if financials is None or financials.empty:
        return []
    # Try several variants for revenue row names
    revenue_row = find_row_like(financials, ["total revenue", "totalrevenue", "revenue", "totalrevenues"])
    if revenue_row is None:
        return []
    # financials columns are timestamps; convert to years (if possible) and pick most recent N
    series = financials.loc[revenue_row]
    # Series may have columns as datetimes or strings; try to parse year from column labels
    rev_list = []
    # iterate columns in reverse order (most recent first)
    for col in list(series.columns)[::-1][:years]:
        value = series[col]
        try:
            # derive year label
            if isinstance(col, (pd.Timestamp, datetime.datetime)):
                year = col.year
            else:
                # try to parse as str then extract year
                col_str = str(col)
                # common format: '2022' or '2022-12-31'
                year = int(col_str[:4])
        except Exception:
            year = str(col)
        # Convert value to numeric (some values are in thousand? yfinance returns raw)
        try:
            num = float(value) if (value is not None and not pd.isna(value)) else None
        except Exception:
            num = None
        rev_list.append({"year": year, "revenue": num})
    # Return in chronological order (oldest-first)
    return rev_list[::-1]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/<symbol>", methods=["GET"])
def get_symbol(symbol):
    """
    Main API endpoint to fetch financial data for a symbol.
    Uses yfinance under the hood. Returns JSON:
    {
      symbol, companyName, marketCap, revenue (latest), netIncome (latest),
      peRatio, sector, latestAnnualReportLink, revenueHistory: [{year, revenue}, ...]
    }
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400

    try:
        ticker = yf.Ticker(symbol)
    except Exception as e:
        return jsonify({"error": f"Failed to create ticker: {str(e)}"}), 500

    # Guard: sometimes yfinance returns empty info
    info = {}
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    # Basic fields from info
    company_name = info.get("shortName") or info.get("longName") or info.get("symbol") or symbol
    market_cap = dollars_or_none(info.get("marketCap"))
    pe_ratio = info.get("trailingPE") or info.get("forwardPE") or None
    sector = info.get("sector") or None

    # Financial statements: try to load annual financials DataFrame
    revenue_latest = None
    net_income_latest = None
    revenue_history = []
    try:
        financials = ticker.financials  # annual financials
        # financials is a DataFrame where rows are labels, columns are periods
        if financials is not None and not financials.empty:
            # Extract revenue history (up to 5 years)
            revenue_history = extract_revenue_history(financials, years=5)
            if revenue_history:
                revenue_latest = revenue_history[-1]["revenue"]
            # Try to find net income row
            net_row = find_row_like(financials, ["net income", "netincome", "net income common", "net_income"])
            if net_row:
                try:
                    series = financials.loc[net_row]
                    # pick latest available column (right-most)
                    latest_col = list(series.columns)[-1]
                    net_income_latest = float(series[latest_col]) if not pd.isna(series[latest_col]) else None
                except Exception:
                    net_income_latest = None
    except Exception:
        financials = None

    # Fallbacks: earnings / income statements
    if revenue_latest is None or net_income_latest is None:
        try:
            # try ticker.earnings (DataFrame of yearly earnings usually has 'Revenue' and 'Earnings')
            earnings = ticker.earnings  # usually a dataframe with 'Revenue' and 'Earnings'
            if earnings is not None and not earnings.empty:
                # earnings is chronological ascending by year; pick last row
                last = earnings.iloc[-1]
                if revenue_latest is None:
                    if "Revenue" in last.index:
                        revenue_latest = float(last["Revenue"])
                    elif "Total Revenue" in last.index:
                        revenue_latest = float(last["Total Revenue"])
                if net_income_latest is None:
                    if "Earnings" in last.index:
                        net_income_latest = float(last["Earnings"])
        except Exception:
            pass

    # Latest annual report link: use website (investor relations) if present, and SEC search as fallback
    website = info.get("website")
    # create SEC search link using symbol/company name to help user find 10-K/annual reports
    sec_search_link = f"https://www.sec.gov/edgar/search/#/q={symbol}"
    # A helpful investor relations search (attempt using company name)
    investor_rel = website
    latest_annual_report_link = investor_rel or sec_search_link

    # Build response
    result = {
        "symbol": symbol,
        "companyName": company_name,
        "marketCap": market_cap,
        "revenue": revenue_latest,
        "netIncome": net_income_latest,
        "peRatio": pe_ratio,
        "sector": sector,
        "latestAnnualReportLink": latest_annual_report_link,
        "revenueHistory": revenue_history,
        "rawInfo": {k: info.get(k) for k in ["longBusinessSummary", "website", "exchange", "fullTimeEmployees"]},
    }

    # Save search record (non-blocking - but we will save synchronously for simplicity)
    try:
        save_search(symbol, company_name, result)
    except Exception:
        # Don't fail the request for DB problems; just continue
        pass

    # If no meaningful data found, return 404 with helpful error
    if (market_cap is None and revenue_latest is None and net_income_latest is None and pe_ratio is None and sector is None):
        return jsonify({"error": f"No data found for symbol '{symbol}'. Please check the symbol and try again."}), 404

    return jsonify(result)


@app.route("/api/recent", methods=["GET"])
def api_recent():
    """
    Return recent searches saved in the SQLite DB.
    """
    limit = int(request.args.get("limit", 10))
    recent = fetch_recent(limit=limit)
    return jsonify({"recent": recent})


@app.route("/export/<symbol>", methods=["GET"])
def export_symbol(symbol):
    """
    Export the result for a symbol as CSV or XLSX.

    Query parameter:
    - format=csv or format=xlsx (default xlsx)
    """
    fmt = (request.args.get("format") or "xlsx").lower()
    # Reuse same logic as /api/<symbol> to obtain data
    # For reliability, call internal API handler function (but not as HTTP)
    with app.test_request_context():
        resp = get_symbol(symbol)
    # get_symbol might return (json, code) or response object
    if hasattr(resp, "get_json"):
        data = resp.get_json()
        status_code = resp.status_code
    else:
        # if tuple
        try:
            data, status_code = resp
        except Exception:
            data = None
            status_code = 500
    if status_code != 200:
        # Return same error response
        return jsonify(data), status_code

    # Build a small DataFrame summarizing key metrics and revenue history
    summary = {
        "Symbol": data.get("symbol"),
        "Company": data.get("companyName"),
        "Market Cap": data.get("marketCap"),
        "P/E Ratio": data.get("peRatio"),
        "Sector": data.get("sector"),
        "Latest Annual Report Link": data.get("latestAnnualReportLink"),
        "Net Income (Latest)": data.get("netIncome"),
        "Revenue (Latest)": data.get("revenue"),
    }

    # DF for summary
    summary_df = pd.DataFrame(list(summary.items()), columns=["Metric", "Value"])

    # Revenue history
    revenue_history = data.get("revenueHistory") or []
    rev_df = pd.DataFrame(revenue_history) if revenue_history else pd.DataFrame(columns=["year", "revenue"])

    if fmt == "csv":
        # Create an in-memory zip or single CSV? We'll return a single CSV with summary then blank line then revenue table.
        buf = io.StringIO()
        summary_df.to_csv(buf, index=False)
        buf.write("\n\n")
        rev_df.to_csv(buf, index=False)
        buf.seek(0)
        return send_file(
            io.BytesIO(buf.getvalue().encode("utf-8")),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{symbol}_financials.csv",
        )
    else:
        # xlsx
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="Summary", index=False)
            rev_df.to_excel(writer, sheet_name="RevenueHistory", index=False)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{symbol}_financials.xlsx",
        )


if __name__ == "__main__":
    # For local development
    app.run(debug=True, host="0.0.0.0", port=5000)