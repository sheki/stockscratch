import argparse
import csv
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

DATA_FILE = Path(__file__).parent / "data" / "russell_1000.csv"
SEC_USER_AGENT = "stockscratch/1.0 (contact: example@example.com)"


def load_companies() -> list[dict[str, str]]:
    with DATA_FILE.open(newline="") as f:
        return list(csv.DictReader(f))


def save_companies(companies: list[dict[str, str]]) -> None:
    fieldnames = ["ticker", "name", "sector", "annual_report_filed", "annual_report_url"]
    normalized: list[dict[str, str]] = []
    for company in companies:
        normalized.append({k: company.get(k, "") for k in fieldnames})

    with DATA_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)


def fetch_json(url: str) -> Any:
    req = Request(url, headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_latest_annual_report(symbol: str) -> tuple[str, str]:
    ticker = symbol.upper()
    ticker_data = fetch_json("https://www.sec.gov/files/company_tickers.json")

    cik: int | None = None
    for entry in ticker_data.values():
        if entry.get("ticker", "").upper() == ticker:
            cik = int(entry["cik_str"])
            break

    if cik is None:
        raise ValueError(f"Ticker {ticker} not found in SEC ticker mapping")

    submissions = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])

    for i, form in enumerate(forms):
        if form in {"10-K", "20-F", "40-F"}:
            accession = accession_numbers[i].replace("-", "")
            primary_doc = primary_docs[i]
            filing_date = filing_dates[i]
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"
            )
            return filing_date, filing_url

    raise ValueError(f"No annual report filing (10-K/20-F/40-F) found for {ticker}")


def update_symbol_annual_report(symbol: str) -> None:
    companies = load_companies()
    ticker = symbol.upper()

    matches = [c for c in companies if c["ticker"].upper() == ticker]
    if not matches:
        raise ValueError(f"Ticker {ticker} is not present in {DATA_FILE.name}")

    filed_at, report_url = fetch_latest_annual_report(ticker)
    for company in matches:
        company["annual_report_filed"] = filed_at
        company["annual_report_url"] = report_url

    save_companies(companies)
    print(f"Updated {ticker}: {filed_at} — {report_url}")


def print_companies() -> None:
    companies = load_companies()
    print(f"Russell 1000 — {len(companies)} companies")
    print(f"{'Ticker':<8} {'Name':<48} Sector")
    print("-" * 96)
    for c in companies:
        print(f"{c['ticker']:<8} {c['name']:<48} {c['sector']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--annual-report",
        metavar="SYMBOL",
        help="Download latest annual report link from SEC and store it for a ticker",
    )
    args = parser.parse_args()

    if args.annual_report:
        update_symbol_annual_report(args.annual_report)
    else:
        print_companies()


if __name__ == "__main__":
    main()
