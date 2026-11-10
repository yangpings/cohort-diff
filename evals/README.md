# Eval set: LLM-drafted cohort definitions

`items.jsonl` holds 20 items, frozen on 2026-11-10 before any model was run. Do not edit an
item after seeing model output; if an item turns out to be wrong, add a dated note here and
report results with and without it.

## Items

| Source | Items | What the text is |
| --- | --- | --- |
| `author` | 8 | The one-line rule of a built-in definition (no paper exists) |
| `code` | 2 | The author's summary of community source code (MIT-LCP mimic-code) |
| `paper` | 8 answerable + 2 not | Short excerpts quoted from the paper's methods, with citation |

Each answerable item names its `reference`: the built-in definition the draft is graded
against. Sentences starting "Task:" were added by the author to narrow the scope (for
example, "implement only the diabetes criterion"); everything else in a `paper` item is quoted,
with "..." marking cuts. Figure 1A of Zhang & Cao 2023 is transcribed, since it is an image.

Two items (`ye2025_no_rule`, `su2025_no_window`) state no computable rule: Ye et al. never say
how diabetes was identified, and Su et al. give no time window for readmission. For these the
correct answer is to say the rule is not stated (`rule_stated: false`), not to invent one.

## Two conditions

- **A. Paper text:** the model gets the item's `text`. This is what a researcher has.
- **B. Full specification:** the model gets the reference definition's SQL header (every "As
  written" and "Assumed:" line), without its query. This separates "the paper is ambiguous"
  from "the model writes wrong SQL".

Both conditions also give the model the table and column names. Neither ever sends patient data.

## Grading (per draft)

1. Valid output in the JSON schema (`name`, `condition`, `rule_stated`, `sql`, `assumptions`).
2. The SQL runs on DuckDB.
3. Exact agreement with the reference on synthetic data (2,000 patients, seed 0).
4. Passes the reference's hand-made, oracle and property tests.

Also reported: Jaccard with the reference on the MIMIC-IV demo (computed locally). For the two
unanswerable items, the grade is `rule_stated == false`.