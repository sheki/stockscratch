"""Download Russell 1000 constituents from the iShares IWB ETF holdings CSV.

IWB tracks the Russell 1000 and BlackRock publishes the holdings daily; this is
the most accessible canonical public source for the index.
"""

import csv
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund"
)
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "russell_1000.csv"


def main() -> None:
    print(f"Fetching {SOURCE_URL}")
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8-sig")

    lines = raw.splitlines(keepends=True)
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("Ticker,Name,Sector"))

    fund_date = next(
        (
            line.split(",", 1)[1].strip().strip('"')
            for line in lines
            if line.startswith("Fund Holdings as of,")
        ),
        "unknown",
    )

    reader = csv.DictReader(lines[header_idx:])
    rows = [
        {"ticker": r["Ticker"], "name": r["Name"], "sector": r["Sector"], "annual_report_filed": "", "annual_report_url": ""}
        for r in reader
        if r.get("Ticker") and (r.get("Asset Class") or "").strip() == "Equity"
    ]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "name", "sector", "annual_report_filed", "annual_report_url"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} constituents to {OUTPUT_FILE} (as of {fund_date})")


if __name__ == "__main__":
    main()
