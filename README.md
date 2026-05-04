## Save latest annual report URL for a symbol

```bash
python main.py --annual-report AAPL
```

This looks up the company in SEC data, finds its latest annual filing (10-K/20-F/40-F), and writes the filing date and URL into `data/russell_1000.csv` for that ticker.

## Evaluate TAM growth for all tickers with OpenAI

```bash
OPENAI_API_KEY=... python main.py --evaluate-tam-all --output data/tam_evaluations.jsonl --model gpt-5
```

For each ticker in `data/russell_1000.csv`, this:

1. Ensures an SEC annual filing URL exists (fetches one if missing).
2. Downloads the annual filing and sends an excerpt to the OpenAI Responses API.
3. Enables web search and high reasoning effort.
4. Writes one JSON object per line to the output file with:
   - `ticker`
   - `tam_growing` (`yes`/`no`)
   - `tam_growing_faster_than_us_gdp` (`yes`/`no`)
   - `reasoning`
   - `annual_report_url`

SEC lookup JSON is cached in `data/sec_cache/`, so repeated runs reuse local SEC data instead of downloading it again.

## Evaluate TAM growth for a single ticker

```bash
OPENAI_API_KEY=... python main.py --evaluate-tam NVDA --output data/tam_nvda.jsonl --model gpt-5
```
