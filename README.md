

## Save latest annual report URL for a symbol

```bash
python main.py --annual-report AAPL
```

This looks up the company in SEC data, finds its latest annual filing (10-K/20-F/40-F), and writes the filing date and URL into `data/russell_1000.csv` for that ticker.
