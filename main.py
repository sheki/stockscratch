import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DATA_FILE = Path(__file__).parent / "data" / "russell_1000.csv"
SEC_CACHE_DIR = Path(__file__).parent / "data" / "sec_cache"
SEC_USER_AGENT = "stockscratch/1.0 (contact: example@example.com)"
OPENAI_API_URL = "https://api.openai.com/v1/responses"


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


def fetch_json_cached(url: str, cache_path: Path) -> Any:
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    data = fetch_json(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data))
    return data


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_latest_annual_report(symbol: str) -> tuple[str, str]:
    ticker = symbol.upper()
    ticker_data = fetch_json_cached(
        "https://www.sec.gov/files/company_tickers.json",
        SEC_CACHE_DIR / "company_tickers.json",
    )

    cik: int | None = None
    for entry in ticker_data.values():
        if entry.get("ticker", "").upper() == ticker:
            cik = int(entry["cik_str"])
            break

    if cik is None:
        raise ValueError(f"Ticker {ticker} not found in SEC ticker mapping")

    submissions = fetch_json_cached(
        f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
        SEC_CACHE_DIR / f"submissions_CIK{cik:010d}.json",
    )
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


def filing_to_plain_text(filing_content: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", filing_content)
    normalized = re.sub(r"\s+", " ", without_tags)
    return normalized.strip()


def evaluate_tam_for_company(company: dict[str, str], model: str) -> dict[str, Any]:
    report_url = company.get("annual_report_url", "").strip()
    if not report_url:
        filed_at, report_url = fetch_latest_annual_report(company["ticker"])
        company["annual_report_filed"] = filed_at
        company["annual_report_url"] = report_url

    filing_text = filing_to_plain_text(fetch_text(report_url))
    filing_excerpt = filing_text[:12000]

    prompt = (
        "You are evaluating market growth from an SEC annual filing. "
        "Use the filing excerpt and web search context to assess the company. "
        "Return JSON only with keys: tam_growing (yes/no), tam_growing_faster_than_us_gdp "
        "(yes/no), reasoning (string).\n\n"
        f"Ticker: {company['ticker']}\n"
        f"Company: {company['name']}\n"
        f"Sector: {company['sector']}\n"
        f"SEC annual filing URL: {report_url}\n"
        "SEC annual filing excerpt:\n"
        f"{filing_excerpt}"
    )

    payload = {
        "model": model,
        "reasoning": {"effort": "high"},
        "tools": [{"type": "web_search_preview"}],
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "tam_eval",
                "schema": {
                    "type": "object",
                    "properties": {
                        "tam_growing": {"type": "string", "enum": ["yes", "no"]},
                        "tam_growing_faster_than_us_gdp": {
                            "type": "string",
                            "enum": ["yes", "no"],
                        },
                        "reasoning": {"type": "string"},
                    },
                    "required": [
                        "tam_growing",
                        "tam_growing_faster_than_us_gdp",
                        "reasoning",
                    ],
                    "additionalProperties": False,
                },
            }
        },
    }

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")

    request = Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_payload = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API request failed for {company['ticker']}: {error_payload}") from exc

    output_text = data.get("output_text", "").strip()
    result = json.loads(output_text)
    return {
        "ticker": company["ticker"],
        "tam_growing": result["tam_growing"],
        "tam_growing_faster_than_us_gdp": result["tam_growing_faster_than_us_gdp"],
        "reasoning": result["reasoning"],
        "annual_report_url": report_url,
    }


def evaluate_tam_all_companies(output_file: Path, model: str) -> None:
    companies = load_companies()
    results: list[dict[str, Any]] = []

    for company in companies:
        print(f"Evaluating {company['ticker']}...")
        results.append(evaluate_tam_for_company(company, model))

    save_companies(companies)

    with output_file.open("w") as f:
        for row in results:
            f.write(json.dumps(row) + "\n")

    print(f"Saved {len(results)} JSON lines to {output_file}")


def evaluate_tam_single_ticker(symbol: str, output_file: Path, model: str) -> None:
    companies = load_companies()
    ticker = symbol.upper()
    company = next((c for c in companies if c["ticker"].upper() == ticker), None)
    if company is None:
        raise ValueError(f"Ticker {ticker} is not present in {DATA_FILE.name}")

    print(f"Evaluating {ticker}...")
    result = evaluate_tam_for_company(company, model)
    save_companies(companies)

    with output_file.open("w") as f:
        f.write(json.dumps(result) + "\n")

    print(f"Saved 1 JSON line to {output_file}")


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
    parser.add_argument(
        "--evaluate-tam-all",
        action="store_true",
        help="Call OpenAI for each ticker and write newline-delimited JSON TAM evaluations",
    )
    parser.add_argument(
        "--evaluate-tam",
        metavar="SYMBOL",
        help="Call OpenAI for one ticker and write newline-delimited JSON TAM evaluation",
    )
    parser.add_argument(
        "--output",
        default="data/tam_evaluations.jsonl",
        help="Output file path for --evaluate-tam-all (default: data/tam_evaluations.jsonl)",
    )
    parser.add_argument(
        "--model",
        default="gpt-5",
        help="Model for --evaluate-tam-all (default: gpt-5)",
    )
    args = parser.parse_args()

    if args.annual_report:
        update_symbol_annual_report(args.annual_report)
    elif args.evaluate_tam:
        evaluate_tam_single_ticker(args.evaluate_tam, Path(args.output), args.model)
    elif args.evaluate_tam_all:
        evaluate_tam_all_companies(Path(args.output), args.model)
    else:
        print_companies()


if __name__ == "__main__":
    main()
