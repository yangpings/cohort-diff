# Part 7 results

Full runs: 20261110T122605Z.jsonl, 20261110T130325Z.jsonl, 20261110T133618Z.jsonl, 20261120T095213Z.jsonl, 20261120T103224Z.jsonl, 20261120T110625Z.jsonl (684 drafts, US$12.34).
Correct = the same admissions as the reference on synthetic data and no failing reference test.
Intervals: 95%, bootstrap over the 18 items (a draft's samples are not independent).

## Share of drafts correct

| Model | Condition | Correct | 95% CI | Drafts | By run |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-5-5 | A | 44% | 23%-65% | 108 | 44% / 43% |
| claude-haiku-5-5 | B | 70% | 51%-88% | 108 | 70% / 70% |
| claude-sonnet-5-5 | A | 41% | 21%-61% | 108 | 41% / 41% |
| claude-sonnet-5-5 | B | 80% | 61%-94% | 108 | 78% / 81% |
| claude-opus-5-5 | A | 46% | 27%-66% | 108 | 46% / 46% |
| claude-opus-5-5 | B | 85% | 67%-100% | 108 | 87% / 83% |

## Paired differences (share correct, item by item)

| Comparison | Difference | 95% CI |
| --- | --- | --- |
| claude-haiku-5-5 B minus claude-haiku-5-5 A | +27% | +8% to +46% |
| claude-sonnet-5-5 B minus claude-sonnet-5-5 A | +39% | +21% to +57% |
| claude-opus-5-5 B minus claude-opus-5-5 A | +39% | +22% to +56% |
| claude-opus-5-5 B minus claude-haiku-5-5 B | +15% | +4% to +28% |
| claude-opus-5-5 A minus claude-haiku-5-5 A | +3% | -8% to +15% |

## Items with no computable rule: share that said so

| Item | claude-haiku-5-5 | claude-sonnet-5-5 | claude-opus-5-5 |
| --- | --- | --- | --- |
| item19 ye2025_no_rule | 6/6 | 6/6 | 6/6 |
| item20 su2025_no_window | 5/6 | 1/6 | 0/6 |

## Correct drafts per item (of 6 per model and condition)

| Item | Definition | A: haiku / sonnet / opus | B: haiku / sonnet / opus |
| --- | --- | --- | --- |
| item01 | aki_icd | 6 / 6 / 6 | 6 / 6 / 6 |
| item02 | aki_kdigo_48h | 0 / 0 / 0 | 0 / 2 / 2 |
| item03 | aki_kdigo_7d | 6 / 5 / 6 | 6 / 6 / 6 |
| item04 | dm_icd | 6 / 6 / 6 | 6 / 6 / 6 |
| item05 | dm_hba1c | 6 / 6 / 3 | 6 / 6 / 6 |
| item06 | dm_meds | 2 / 5 / 6 | 0 / 6 / 6 |
| item07 | readmit30_any | 0 / 0 / 0 | 0 / 0 / 0 |
| item08 | readmit30_excl | 0 / 0 / 0 | 0 / 0 / 0 |
| item09 | aki_kdigo_mimiccode | 0 / 0 / 2 | 3 / 3 / 6 |
| item10 | dm_charlson_mimiccode | 6 / 2 / 4 | 6 / 6 / 6 |
| item11 | aki_rahimi2023_b1 | 0 / 0 / 0 | 6 / 6 / 6 |
| item12 | aki_rahimi2023_b2 | 0 / 0 / 0 | 6 / 6 / 6 |
| item13 | aki_rahimi2023_b3 | 0 / 0 / 0 | 5 / 6 / 6 |
| item14 | dm_cheng2025 | 5 / 1 / 4 | 5 / 6 / 6 |
| item15 | dm_zhang2023_emerge | 0 / 2 / 3 | 3 / 3 / 6 |
| item16 | readmit_gupta2022 | 0 / 0 / 0 | 6 / 6 / 6 |
| item17 | readmit_prempeh2026 | 6 / 6 / 6 | 6 / 6 / 6 |
| item18 | readmit_shen2025 | 4 / 5 / 4 | 6 / 6 / 6 |

## Failure categories (every failed draft, one category each)

| Category | claude-haiku-5-5 | claude-sonnet-5-5 | claude-opus-5-5 |
| --- | --- | --- | --- |
| SQL error | 0 | 2 | 3 |
| computed a rule where the text states none | 1 | 5 | 6 |
| different cohort (Jaccard < 0.99) | 41 | 20 | 12 |
| near miss (Jaccard >= 0.99) | 25 | 26 | 34 |
| right cohort on synthetic data, fails a reference test | 27 | 38 | 25 |

Of 180 drafts for definitions that round the creatinine comparison (floating point), 120 do not round it.
