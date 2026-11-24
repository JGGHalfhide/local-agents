Scores: reviewed per the accepted rule (all 80 flagged answers); 8 unflagged answers keep their pattern score and await the user's spot-check (off-greedy c16, off-qwen c20, on-greedy c04 c06 c10 c16 c20, on-qwen c16). Not final.

| Config | Cause = 2 | Fix = 2 | Both | Points (of 4n) | Harmful | No-fault right | Latency p50 / p95 (s) | Completion tokens (mean) | Cut at max_tokens | Errors | Reviewed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| off-greedy | 6/22 | 5/22 | 1/22 | 38/88 | 0 | 0/2 | 28.28 / 36.55 | 378 | 0 | 0 | 21/21 |
| off-qwen | 6/22 | 2/22 | 2/22 | 30/88 | 1 | 0/2 | 26.49 / 37.87 | 339 | 0 | 0 | 21/21 |
| on-greedy | 11/22 | 7/22 | 6/22 | 49/88 | 1 | 0/2 | 93.49 / 103.95 | 1325 | 0 | 0 | 17/17 |
| on-qwen | 6/22 | 5/22 | 2/22 | 42/88 | 2 | 0/2 | 86.62 / 100.51 | 1232 | 0 | 0 | 21/21 |
