import os
import datetime as dt

import pandas as pd
from massive import RESTClient

API_KEY = os.environ.get("POLYGON_API_KEY", "").strip()
if not API_KEY:
    raise RuntimeError("Missing POLYGON_API_KEY GitHub secret")

client = RESTClient(API_KEY)

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

EARNINGS_KEYWORDS = (
    "earnings",
    "reports",
    "eps",
    "revenue",
    "beats",
    "misses",
    "profit",
    "guidance",
    "quarter",
    "q1",
    "q2",
    "q3",
    "q4",
)

MAX_ROWS = 12
NEWS_PER_TICKER = 2


def looks_like_earnings(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in EARNINGS_KEYWORDS)


def get_sp500_tickers() -> list[str]:
    tables = pd.read_html(WIKI_SP500_URL)
    df = tables[0]
    tickers = df["Symbol"].astype(str).tolist()

    clean = []
    for t in tickers:
        t = t.strip().upper()
        t = t.replace(".", "-")
        clean.append(t)

    return clean


def pick_date_str() -> str:
    return dt.date.today().isoformat()


def safe_daily_change_pct(ticker: str, date_str: str):
    try:
        bars = client.get_aggs(
            ticker=ticker,
            multiplier=1,
            timespan="day",
            from_=date_str,
            to=date_str,
            adjusted=True,
        )
        bars = list(bars) if bars else []
        if not bars:
            return None

        b = bars[0]
        o = getattr(b, "open", None)
        c = getattr(b, "close", None)
        if not o or o <= 0 or c is None:
            return None

        return (c - o) / o * 100.0
    except Exception:
        return None


def safe_company_name(ticker: str) -> str:
    try:
        res = client.get_ticker_details(ticker)
        name = getattr(res, "name", None)
        return name or ticker
    except Exception:
        return ticker


def latest_earnings_headline(ticker: str) -> str | None:
    try:
        items = client.list_ticker_news(
            ticker=ticker,
            limit=NEWS_PER_TICKER,
            order="desc",
            sort="published_utc",
        )
        for item in items:
            title = getattr(item, "title", "") or ""
            if looks_like_earnings(title):
                return title
        return None
    except Exception:
        return None


def render_html(rows, date_str: str) -> str:
    title = f"Notes ({date_str})"

    css = """
    :root { --text:#111827; --line:#e5e7eb; --bg:#ffffff; }
    body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
           background: var(--bg); color: var(--text); margin: 24px; }
    .wrap { max-width: 1100px; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    thead th { text-align: left; font-weight: 700; font-size: 14px; padding: 14px 10px;
               border-bottom: 1px solid var(--line); }
    tbody td { padding: 18px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; font-size: 14px; }
    tbody tr:last-child td { border-bottom: 1px solid var(--line); }
    .col-company { width: 33%; }
    .col-ticker { width: 12%; }
    .col-change { width: 12%; }
    .col-notes { width: 43%; }
    """

    def fmt_pct(x):
        if x is None:
            return ""
        sign = "+" if x > 0 else ""
        return f"{sign}{x:.1f}%"

    head = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<table>
  <thead>
    <tr>
      <th class="col-company">Company</th>
      <th class="col-ticker">Ticker</th>
      <th class="col-change">Change (%)</th>
      <th class="col-notes">{title}</th>
    </tr>
  </thead>
  <tbody>
"""

    body_rows = []
    for r in rows:
        body_rows.append(
            "    <tr>"
            f"<td class='col-company'>{r['company']}</td>"
            f"<td class='col-ticker'>{r['ticker']}</td>"
            f"<td class='col-change'>{fmt_pct(r['change'])}</td>"
            f"<td class='col-notes'>{r['note']}</td>"
            "</tr>"
        )

    tail = """
  </tbody>
</table>
</div>
</body>
</html>
"""
    return head + "\n".join(body_rows) + tail


def main():
    date_str = pick_date_str()
    tickers = get_sp500_tickers()

    matches = []
    for t in tickers:
        headline = latest_earnings_headline(t)
        if not headline:
            continue

        chg = safe_daily_change_pct(t, date_str)
        if chg is None:
            continue

        matches.append(
            {
                "company": safe_company_name(t),
                "ticker": t,
                "change": chg,
                "note": headline,
            }
        )

    matches.sort(key=lambda x: x["change"], reverse=True)
    matches = matches[:MAX_ROWS]

    html = render_html(matches, date_str)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(f"docs/daily_table_{date_str}.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("Wrote docs index.html")


if __name__ == "__main__":
    main()

