import os
import datetime as dt
from massive import RESTClient

MASSIVE_API_KEY = os.environ.get("POLYGON_API_KEY", "").strip()
if not MASSIVE_API_KEY:
    raise RuntimeError("Missing POLYGON_API_KEY. Add it in GitHub Secrets, Actions secrets.")

client = RESTClient(MASSIVE_API_KEY)

EARNINGS_KEYWORDS = (
    "earnings",
    "reports q",
    "eps",
    "revenue",
    "beats",
    "misses",
    "profit",
    "guidance",
    "quarter",
)

MAX_ROWS = 8
NEWS_LIMIT = 80


def looks_like_earnings(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in EARNINGS_KEYWORDS)


def pick_trade_date(max_lookback_days: int = 7) -> str:
    d = dt.date.today()
    for _ in range(max_lookback_days):
        date_str = d.isoformat()
        try:
            items = list(client.list_news(limit=1, order="desc", sort="published_utc"))
            return date_str
        except Exception:
            pass
        d = d - dt.timedelta(days=1)
    return dt.date.today().isoformat()


def safe_company_name(ticker: str) -> str:
    try:
        res = client.get_ticker_details(ticker)
        name = getattr(res, "name", None)
        return name or ticker
    except Exception:
        return ticker


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
        if not b.open or b.open <= 0:
            return None
        return (b.close - b.open) / b.open * 100.0
    except Exception:
        return None


def render_html(rows, date_str: str) -> str:
    title = f"Notes ({date_str})"

    css = """
    :root { --text:#111827; --muted:#6b7280; --line:#e5e7eb; --bg:#ffffff; }
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
        sign = "+" if x is not None and x > 0 else ""
        return "" if x is None else f"{sign}{x:.1f}%"

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
    date_str = pick_trade_date()

    earnings_candidates = {}
    news_items = list(client.list_news(limit=NEWS_LIMIT, order="desc", sort="published_utc"))

    for item in news_items:
        title = getattr(item, "title", "") or ""
        if not looks_like_earnings(title):
            continue
        item_tickers = getattr(item, "tickers", None) or []
        for t in item_tickers:
            if t and t not in earnings_candidates:
                earnings_candidates[t] = title

    rows = []
    for ticker, headline in earnings_candidates.items():
        chg = safe_daily_change_pct(ticker, date_str)
        if chg is None:
            continue
        rows.append(
            {
                "company": safe_company_name(ticker),
                "ticker": ticker,
                "change": chg,
                "note": headline,
            }
        )

    rows.sort(key=lambda x: x["change"], reverse=True)
    rows = rows[:MAX_ROWS]

    html = render_html(rows, date_str)

    out_dir = "docs"
    os.makedirs(out_dir, exist_ok=True)

    latest_path = os.path.join(out_dir, "index.html")
    dated_path = os.path.join(out_dir, f"daily_table_{date_str}.html")

    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)

    with open(dated_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("Wrote:", latest_path, dated_path)


if __name__ == "__main__":
    main()
