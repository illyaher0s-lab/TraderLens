# Golden Case Parquet Snapshots

Generate these files with:

```powershell
python backend/scripts/generate_golden_cases.py
```

The generator writes one `*_daily.parquet` and one `*_status.parquet` file for each of the five fixed test stocks. It requires `pyarrow`, because M0 must use real Parquet files rather than JSON files with a Parquet extension.
