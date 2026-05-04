import csv
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "russell_1000.csv"


def load_companies() -> list[dict[str, str]]:
    with DATA_FILE.open(newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    companies = load_companies()
    print(f"Russell 1000 — {len(companies)} companies")
    print(f"{'Ticker':<8} {'Name':<48} Sector")
    print("-" * 96)
    for c in companies:
        print(f"{c['ticker']:<8} {c['name']:<48} {c['sector']}")


if __name__ == "__main__":
    main()
