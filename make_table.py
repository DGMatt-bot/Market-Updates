import os
import datetime as dt
import requests

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "").strip()
BASE_URL = "https://api.polygon.io"


def get_json(url: str, params: dict | None = None) -> dict:
    if not POLYGON_API_KEY:
        raise RuntimeError("POLYGON_API_KEY is missing. Add it as a GitHub Actions secret.")

    params = dict(params or {})
    params["apiKey"] = POLYGON_API_KEY

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def pct_change(o: float, c: float) -> float | None:
    if o is None or o <= 0:
        return None
    return (c - o) / o * 100.0


def get_grouped_daily(date_str: str) -> list[dict]:
    url = f"{BASE_URL}/v2/aggs/grouped/locale/us/market/stocks/{date_str}"
    data = get_json(url)
    return data.get("results") or []


def get_company_name(ticker: str) -> str:
    url = f"{BASE_URL}/v3/reference/tickers/{ticker}"
    data = get_json(url)
    res = data.get("results") or {}
    return res.get("name") or ticker


def get_note_from_news(ticker: str) -> str:
    url = f"{BASE_URL}/v2/reference/news"
    params = {"ticker": ticker, "limit": 1, "order": "desc", "sort": "published_utc"}
    data = get_json(url, params=params)
    items = data.get("results") or []
    if not items:
        return ""
    return (items[0].get("title") or "").strip()


def build_rows(date_str: str, top_n_each_side: int = 4) -> list[dict]:
    grouped = get_grouped_daily(date_str)

    moves = []
    for bar in grouped:
        t = bar.get("T")
        o = bar.get("o")
        c = bar.get("c")
        if not t or o is None or c is None:
            continue
        chg = pct_change(float(o), float(c))
        if chg is None:
            continue
        moves.append({"ticker": t, "change": chg})

    moves.sort(key=lambda x: x["change"], reverse=True)

    gainers = moves[:top_n_each_side]
    losers = list(reversed(moves[-top_n_each_side:]))

    selected = gainers + losers

    rows = []
    for item in selected:
        t = item["ticker"]
        rows.append(
            {
                "company": get_company_name(t),
                "ticker": t,
                "change": item["change"],
                "note": get_note_from_news(t),
            }
        )
    return rows


def render_html(rows: list[dict], date_str: str) -> str:
    def fmt_pct(x: float) -> str:
        sign = "+" if x > 0 else ""
        return f"{sign}{x:.1f}%"

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
            f"<td class='col-change'>{fmt_pct(float(r['change']))}</td>"
            f"<td class='col-notes'>{r['note'] or ''}</td>"
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
    date_str = dt.date.today().isoformat()

    rows = build_rows(date_str=date_str, top_n_each_side=4)
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
