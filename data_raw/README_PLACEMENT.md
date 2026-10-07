# Where the dataset goes

Dataset files are not in git (the full CSV is 97 MB). Copy the course files into this folder, unmodified:
`spotify_reviews_18months.csv`, `analysis_10000.csv`, `checkpoint_500.csv`, `cost_100.csv`, `golden_50_to_label.csv`,
plus the course `manifest.json`, `GRADING_CONTRACT.md`, `COST_CALCULATOR.md`, `README.md`. Everything in this folder except this file is git-ignored.

Check them (from the repo root):

```sh
shasum -a 256 data_raw/*.csv
```

SHA-256 values from the course `manifest.json`:

| File | Bytes | SHA-256 |
|---|---|---|
| spotify_reviews_18months.csv | 97,400,616 | 1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6 |
| analysis_10000.csv | 1,477,793 | eaa62ca6d44d717302904a9c922e99b0b4584d174309cb45295ecbc2ba2a91b5 |
| checkpoint_500.csv | 76,170 | a94e31663ee7b7eaa77e23b7a8425b530cc0c866ed5e714953172a0afef6a12f |
| cost_100.csv | 15,466 | c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e |
| golden_50_to_label.csv | 7,905 | 1a125c3e509f58b0246ba16d0ea332675a53ffadb1928be4338a0bd7053a11c7 |
