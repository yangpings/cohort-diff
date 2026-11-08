# cohort-diff

**Keywords:** EHR · MIMIC-IV · cohort definitions · phenotyping · acute kidney injury · diabetes · 30-day readmission · reproducibility · odds ratio · Jaccard index · bootstrap confidence intervals

**Skills:** Python · SQL · DuckDB · pandas · NumPy · patient-level bootstrap · uv packaging · PyPI (Trusted Publishing) · GitHub Actions CI · pytest · Hypothesis (property-based testing) · test oracles · mypy (strict) · ruff · AI-assisted engineering (Claude Code with CLAUDE.md, tests first, AI log)

How different are "the same" EHR cohorts? `cohort-diff` runs several definitions of one condition side by side on MIMIC-IV-shaped data and reports how much the cohorts, and the results built on them, disagree.

## Description

A cohort definition is a modelling decision, but papers usually report it in a sentence. Two studies that both say "AKI patients in MIMIC-IV" may share only a fraction of their admissions: one counts discharge diagnosis codes, another a creatinine rise within 48 hours, another a rise over 7 days. A finding such as "AKI is associated with higher in-hospital mortality" can change size with the definition. `cohort-diff` stores each definition as a versioned SQL file with its source, runs them on DuckDB directly over MIMIC's `.csv.gz` files, and reports overlap, who is in each cohort, and how a typical downstream association moves.

## Objective

1. Build a tested, pip-installable library that runs cohort definitions as reviewable SQL and checks each one against an independent implementation.
2. Measure how much definitions of the same condition (AKI, diabetes, 30-day readmission) disagree, in membership and in a downstream result (the odds ratio between membership and in-hospital mortality), with confidence intervals.
3. *(Extension, branch `cohort-diff-llm`.)* Measure how often a large language model, given a paper's methods text, drafts a cohort definition that passes the same oracle tests as the hand-written one.

## Hypotheses

- **H1.** Definitions of the same condition select substantially different admissions (pairwise Jaccard well below 1).
- **H2.** Code-based and lab-based definitions differ systematically: codes under-capture, and lab rules with fixed thresholds over-capture when measurements are frequent and noisy.
- **H3.** The mortality odds ratio reported for "the same" condition changes materially with the definition: for some pairs, the 95% interval of the ratio of their odds ratios excludes 1.
- **H4.** A definition limits which questions its cohort can answer (for example, readmission exclusions that remove every death).
- **H5.** *(Extension.)* LLM-drafted definitions often run without error but fail the oracle tests at clinically important details (thresholds, time windows, specimen type, boundary conditions), so tests, not inspection, decide whether a draft can be used.

## Samples

| Dataset | Access | Size | Role |
| --- | --- | --- | --- |
| Synthetic, MIMIC-shaped (`cohort-diff synth`, seed 0) | Generated | 2,000 patients, 2,738 admissions | Known-structure validation; numbers say nothing about real patients |
| MIMIC-IV Clinical Database Demo v2.2 | Open (ODbL) | 100 patients, 275 admissions | End-to-end run on real EHR data |

The demo shares the full MIMIC-IV schema, so the same definitions run on full MIMIC-IV (credentialed) unchanged.

## Methods

- **Definitions as data.** Each definition is one SQL file in `src/cohort_diff/definitions/` with a header (`name`, `condition`, `description`, `reference`) and returns one column, `hadm_id`. Adding a definition does not touch Python.
- **Built-in definitions.**

| Name | Condition | Rule |
| --- | --- | --- |
| `aki_icd` | AKI | ICD-10 N17.* or ICD-9 584.* on the admission |
| `aki_kdigo_48h` | AKI | Creatinine rises ≥ 0.3 mg/dL within 48 h (KDIGO 2012, criterion 1) |
| `aki_kdigo_7d` | AKI | Creatinine ≥ 1.5 × the lowest value in the prior 7 days (KDIGO 2012, criterion 2) |
| `aki_kdigo_mimiccode` | AKI | **Published:** KDIGO creatinine stage ≥ 1 as implemented in MIT-LCP mimic-code, ICU-anchored (results from 7 days before ICU admission to ICU discharge; ≥ lowest in 48 h + 0.3 or ≥ 1.5 × lowest in 7 days; itemid 50912, values ≤ 150, same-time results averaged, no rounding) |
| `aki_rahimi2023_b3` | AKI | **Published:** Kamel Rahimi et al. 2023, Baseline sCr 3: new AKI on ICU day 2 or 3 (≥ 0.3 mg/dL within 48 h or ≥ 1.5 × baseline), baseline = mean creatinine 180 to 7 days before ICU admission, else MDRD back-calculation (eGFR 75, exponent −0.887 as printed); first ICU stay of adults with creatinine on days 1–3; day-1 AKI excluded. Written by Claude Code from a spec and failing tests, checked against an independent answer key; creatinine ≤ 0 dropped (all three baselines) |
| `aki_rahimi2023_b1` | AKI | **Published:** Kamel Rahimi et al. 2023, Baseline sCr 1: same cohort and AKI rules, baseline = minimum creatinine in the first 24 h of ICU admission |
| `aki_rahimi2023_b2` | AKI | **Published:** Kamel Rahimi et al. 2023, Baseline sCr 2: day-1 AKI judged against the MDRD estimate and excluded; days 2–3 judged against the day-1 minimum |
| `dm_icd` | Diabetes | ICD-10 E10/E11/E13/E14 or ICD-9 250.* |
| `dm_hba1c` | Diabetes | Any HbA1c ≥ 6.5% during the admission |
| `dm_meds` | Diabetes | Any glucose-lowering medication |
| `dm_charlson_mimiccode` | Diabetes | **Published:** the Charlson comorbidity "diabetes" flags (without or with complications) as implemented in MIT-LCP mimic-code: ICD-9 250.0–250.9 or ICD-10 E10–E14, by the first four characters (Quan et al. 2005 codes) |
| `dm_cheng2025` | Diabetes | **Published:** Cheng et al. 2025: type 2 diabetes = ICD-10 E11 on the admission (ICD-10 only, so ICD-9-era admissions never qualify). Only the paper's diabetes rule; its heart-failure, age and ICU criteria are not part of this definition |
| `dm_zhang2023_emerge` | Diabetes | **Published:** Zhang & Cao 2023, the eMERGE type 2 diabetes case algorithm adapted to MIMIC-IV: no type 1 code, then one of five paths combining ICD-9 type 2 codes (no ICD-10), type 1 and type 2 drugs and their order, ≥ 2 coded admissions, and HbA1c ≥ 6.5 or glucose ≥ 125 (values ≥ 1000 removed; lab and chart glucose). Per patient: every admission of a case. Written by Claude Code from a spec and failing tests, checked against an independent answer key |
| `readmit30_any` | Readmission | Any admission within 30 days of discharge |
| `readmit30_excl` | Readmission | As above, excluding deaths, hospice, discharge against advice and elective readmissions (inspired by CMS HRRP, simplified) |

- **Engine.** DuckDB, in process, reads the MIMIC tables in place (demo folder layout or flat CSVs) as views. Lab items are found by label and fluid, not by itemid.
- **Correctness.** Every rule-based definition is compared with an independent, deliberately slow pandas implementation (a test oracle written with loops rather than joins), on the synthetic data and on hundreds of random creatinine series generated by Hypothesis. Hand-picked regression tests pin threshold edge cases that both implementations could get wrong together.
- **Comparison.** For every pair of definitions: admissions in both, in only one, and the Jaccard index |A ∩ B| / |A ∪ B|. For each cohort: size, prevalence, mean age, % female, in-hospital mortality. For every pair it also reports in-hospital mortality among the admissions in both definitions and in each one's exclusive part: a gap there means the definitions select different severities, not just different numbers of admissions.
- **Downstream result.** Unadjusted odds ratio between membership and in-hospital mortality, with a Woolf 95% CI (log OR ± 1.96·√(1/a + 1/b + 1/c + 1/d)); 0.5 is added to every cell when any cell is 0 (Haldane–Anscombe). An odds ratio exists only when both groups and both outcomes are non-empty: with a whole margin empty the correction answers from the group sizes alone (a cohort matching no admissions got an OR of 16.16), so the report prints `n/a` and names the empty margin instead.
- **Uncertainty.** Patient-level bootstrap (1,000 resamples; a patient drawn k times contributes all their admissions k times) gives 95% percentile intervals for each pair's Jaccard index and for the ratio of their mortality odds ratios (OR of a / OR of b). An interval for the ratio that excludes 1 means the two definitions disagree about the association, beyond sampling noise. A test checks that patients, not admissions, are resampled.
- **Scale check.** Wall time of `compare` for each condition, on the demo and (once credentialed) on full MIMIC-IV, on one laptop.
- **Extension: LLM-drafted definitions** *(planned, branch `cohort-diff-llm`)*. An LLM receives a paper's methods text and the table and column names only (never patient data) and returns a definition through JSON-schema structured output. Each draft is graded by the same oracle and property tests, and by exact agreement with the hand-written definition on synthetic data. Pass rates for 3+ models on a 20-item labeled set, with 95% intervals; every failure is categorized.
- **Engineering.** Strict typing, lint and tests on Python 3.11–3.13 in CI; the wheel is built in CI; releases go to PyPI by Trusted Publishing from version tags.

## Results

### Synthetic data (2,000 patients, 2,738 admissions, seed 0)

| Definition | n | Prevalence | Mortality among members | Mortality OR [95% CI] |
| --- | --- | --- | --- | --- |
| aki_icd | 400 | 14.6% | 16.8% | 3.06 [2.24, 4.19] |
| aki_kdigo_48h | 2,139 | 78.2% | 9.2% | 4.23 [2.44, 7.33] |
| aki_kdigo_7d | 2,033 | 74.3% | 8.4% | 1.48 [1.04, 2.10] |
| dm_icd | 438 | 16.0% | 15.8% | 2.84 [2.09, 3.87] |
| dm_hba1c | 374 | 13.7% | 10.4% | 1.48 [1.03, 2.14] |
| dm_meds | 355 | 13.0% | 16.1% | 2.77 [2.00, 3.84] |
| readmit30_any | 296 | 10.8% | 0.0% | not meaningful (no deaths by construction) |
| readmit30_excl | 242 | 8.8% | 0.0% | not meaningful (no deaths by construction) |

Pairwise overlap and disagreement in the mortality association (patient-level bootstrap, 1,000 resamples, 95% intervals):

| Pair | Jaccard [95% CI] | Ratio of mortality ORs [95% CI] |
| --- | --- | --- |
| aki_icd vs aki_kdigo_48h | 0.160 [0.145, 0.176] | 0.72 [0.33, 1.26] |
| aki_icd vs aki_kdigo_7d | 0.142 [0.127, 0.157] | **2.08 [1.29, 3.37]** |
| aki_kdigo_48h vs aki_kdigo_7d | 0.883 [0.869, 0.896] | **2.87 [1.87, 5.15]** |
| dm_hba1c vs dm_icd | 0.099 [0.078, 0.121] | **0.52 [0.31, 0.83]** |
| dm_hba1c vs dm_meds | 0.093 [0.072, 0.116] | **0.54 [0.32, 0.86]** |
| dm_icd vs dm_meds | 0.811 [0.776, 0.847] | 1.03 [0.88, 1.21] |
| readmit30_any vs readmit30_excl | 0.818 [0.771, 0.860] | not meaningful (no deaths in either cohort) |

Bold: the interval excludes 1, so the two definitions disagree about the mortality association beyond sampling noise.

- **Code vs lab definitions barely overlap** (Jaccard 0.09–0.16), while two lab rules (KDIGO 48 h vs 7 d) or two code-like rules (ICD vs medications) overlap 81–88%.
- **High overlap does not mean the same answer.** The two KDIGO definitions share 88% of admissions, yet their mortality ORs differ about threefold (ratio 2.87 [1.87, 5.15]).
- **Different-looking ORs can be compatible.** `aki_icd` (3.06) and `aki_kdigo_48h` (4.23) look different, but the interval for their ratio includes 1.
- **KDIGO-48h flags 78% of synthetic admissions**: the generator draws creatinine about every 12 h with noise (SD 0.3 mg/dL), and a 0.3 mg/dL rule fires on noise when labs are frequent. Whether real data shows the same is what the demo and full MIMIC-IV can answer.
- **Readmission cohorts contain no deaths by construction** (an admission followed by another one cannot end in death), so their mortality ORs come only from the 0.5 zero-cell correction. The definition limits which questions the cohort can answer.

### MIMIC-IV demo (real data: 100 patients, 275 admissions)

| Definition | n | Prevalence | Mortality among members | Mortality OR [95% CI] |
| --- | --- | --- | --- | --- |
| aki_icd | 70 | 25.5% | 15.7% | 9.37 [2.88, 30.51] |
| aki_kdigo_48h | 69 | 25.1% | 15.9% | 9.58 [2.94, 31.20] |
| aki_kdigo_7d | 53 | 19.3% | 20.8% | 14.27 [4.34, 46.97] |
| aki_kdigo_mimiccode | 44 | 16.0% | 25.0% | 18.92 [5.69, 62.88] |
| aki_rahimi2023_b1 | 18 | 6.5% | 11.1% | 2.35 [0.49, 11.30] (2 deaths) |
| aki_rahimi2023_b2 | 16 | 5.8% | 12.5% | 2.70 [0.56, 13.17] (2 deaths) |
| aki_rahimi2023_b3 | 15 | 5.5% | 6.7% | 1.26 [0.15, 10.24] (1 death) |
| dm_icd | 111 | 40.4% | 4.5% | 0.73 [0.24, 2.19] |
| dm_hba1c | 17 | 6.2% | 0.0% | 0.45 [0.03, 7.82] (no deaths; zero-cell correction) |
| dm_meds | 135 | 49.1% | 5.9% | 1.20 [0.42, 3.40] |
| dm_charlson_mimiccode | 111 | 40.4% | 4.5% | 0.73 [0.24, 2.19] |
| dm_cheng2025 | 60 | 21.8% | 6.7% | 1.32 [0.41, 4.32] |
| dm_zhang2023_emerge | 51 (9 patients) | 18.5% | 0.0% | 0.13 [0.01, 2.23] (no deaths; zero-cell correction) |
| readmit30_any | 53 | 19.3% | 0.0% | not meaningful (no deaths by construction) |
| readmit30_excl | 49 | 17.8% | 0.0% | not meaningful (no deaths by construction) |

| Pair | Jaccard [95% CI] | Ratio of mortality ORs [95% CI] |
| --- | --- | --- |
| aki_icd vs aki_kdigo_48h | 0.376 [0.263, 0.494] | 0.98 [0.25, 3.23] |
| aki_icd vs aki_kdigo_7d | 0.309 [0.189, 0.440] | 0.66 [0.17, 2.48] |
| aki_kdigo_48h vs aki_kdigo_7d | 0.564 [0.447, 0.679] | 0.67 [0.20, 2.35] |
| aki_icd vs aki_kdigo_mimiccode | 0.326 [0.221, 0.449] | 0.50 [0.13, 1.80] |
| aki_kdigo_48h vs aki_kdigo_mimiccode | 0.614 [0.475, 0.759] | **0.51 [0.36, 0.71]** |
| aki_kdigo_7d vs aki_kdigo_mimiccode | 0.492 [0.387, 0.611] | 0.75 [0.22, 2.59] |
| aki_icd vs aki_rahimi2023_b3 | 0.062 [0.014, 0.126] | 7.46 [1.32, 56.25] |
| aki_kdigo_48h vs aki_rahimi2023_b3 | 0.217 [0.118, 0.345] | 7.63 [1.36, 57.58] |
| aki_kdigo_mimiccode vs aki_rahimi2023_b3 | 0.255 [0.139, 0.395] | 15.07 [2.98, 100.38] |
| aki_kdigo_mimiccode vs aki_rahimi2023_b1 | 0.292 [0.175, 0.420] | 8.06 [1.93, 66.12] |
| aki_kdigo_mimiccode vs aki_rahimi2023_b2 | 0.224 [0.113, 0.370] | 7.00 [1.04, 89.07] |
| aki_rahimi2023_b1 vs aki_rahimi2023_b2 | 0.619 [0.391, 0.812] | 0.87 [0.15, 5.14] |
| aki_rahimi2023_b1 vs aki_rahimi2023_b3 | 0.650 [0.428, 0.867] | 1.87 [0.66, 6.50] |
| aki_rahimi2023_b2 vs aki_rahimi2023_b3 | 0.824 [0.625, 1.000] | 2.15 [0.85, 7.56] |
| dm_hba1c vs dm_icd | 0.113 [0.071, 0.171] | 0.62 [0.17, 5.56] (zero-cell) |
| dm_hba1c vs dm_meds | 0.126 [0.079, 0.176] | 0.38 [0.09, 1.91] (zero-cell) |
| dm_icd vs dm_meds | 0.608 [0.461, 0.715] | 0.61 [0.15, 1.51] |
| dm_charlson_mimiccode vs dm_icd | 1.000 [1.000, 1.000] | 1.00 [1.00, 1.00] |
| dm_charlson_mimiccode vs dm_cheng2025 | 0.541 [0.321, 0.716] | 0.55 [0.25, 1.58] |
| dm_cheng2025 vs dm_hba1c | 0.055 [0.017, 0.108] | 2.95 [0.30, 14.57] (zero-cell) |
| dm_cheng2025 vs dm_meds | 0.327 [0.150, 0.458] | 1.11 [0.23, 3.83] |
| dm_icd vs dm_zhang2023_emerge | 0.397 [0.128, 0.651] | 5.54 [0.58, 19.51] (zero-cell) |
| dm_cheng2025 vs dm_zhang2023_emerge | 0.388 [0.068, 0.632] | 10.09 [1.07, 34.24] (zero-cell) |
| dm_meds vs dm_zhang2023_emerge | 0.265 [0.064, 0.460] | 9.12 [1.29, 37.06] (zero-cell) |
| dm_hba1c vs dm_zhang2023_emerge | 0.079 [0.026, 0.132] | 3.42 [0.86, 7.85] (zero-cell) |
| readmit30_any vs readmit30_excl | 0.925 [0.852, 1.000] | not meaningful |

- **Real definitions also select different patients.** The AKI definitions have similar prevalence (19–25%) but share only 31–56% of their combined admissions. Diabetes by HbA1c ≥ 6.5% (6% of admissions) overlaps the code and medication definitions at Jaccard 0.11–0.13.
- **An ICD-10-only diabetes definition loses almost half the cohort to the coding switch.** Cheng et al. 2025 define type 2 diabetes as ICD-10 E11. On the demo this finds 60 of the 111 admissions with a diabetes code (Jaccard 0.54 with the Charlson definition); of the 51 it misses, 50 are coded only in ICD-9 (before October 2015) and 1 has a non-E11 ICD-10 code. The eMERGE definition (Zhang & Cao 2023) uses ICD-9 codes only, yet it is not blind to the ICD-10 years (next point).
- **A multi-source phenotype is not its code list, and in-hospital insulin decides who qualifies.** eMERGE as adapted by Zhang & Cao 2023 classifies patients, not admissions, and returns every admission of a case: 51 admissions (18.5%) from only 9 patients. It shares 46 with `dm_icd` (Jaccard 0.40) and, despite its ICD-9-only codes, 31 with the ICD-10 Cheng cohort, because path 5 (type 2 drug + abnormal glucose or HbA1c) needs no code and a case patient's ICD-10-era admissions come with them. Its 5 admissions outside `dm_icd` all belong to patients with a diabetes code on another admission. No case qualified by path 1 (type 2 code + type 2 drug, no insulin). Of the 65 `dm_icd` admissions it misses, 53 (19 patients) are lost to insulin, which the algorithm counts as a type 1 drug: 36 because insulin came no later than the first type 2 drug, and 17 because there was insulin, no type 2 drug and a type 2 code on only one admission. The other 12 (7 patients) have no ICD-9 type 2 code and no type 2 drug. Insulin is the usual treatment for high glucose in hospital, so the rule's "type 1 medication" step removes most coded inpatients. Measured with `notes/check_emerge.py` (counts only).
- **eMERGE's cases include no in-hospital deaths.** Its ratio intervals against Cheng (10.09 [1.07, 34.24]) and the medication definition (9.12 [1.29, 37.06]) exclude 1, but only because of the zero-cell correction on 9 patients; they are not evidence of a different association.
- **The community definition matches the textbook one.** mimic-code's Charlson diabetes flags select exactly the same 111 admissions as the built-in `dm_icd` (Jaccard 1.0).
- **The medication phenotype captures the most** (49% of admissions vs 40% by codes), consistent with insulin given for stress hyperglycemia; every HbA1c-defined admission is also in the medication cohort.
- **KDIGO-48h flags 25% of demo admissions, not the 78% seen on synthetic data**, so the synthetic over-capture came from the generator's frequent, noisy creatinine, not from the rule itself.
- **Anchoring to the ICU changes the cohort and the answer.** The published mimic-code KDIGO definition flags 44 admissions (16%) against 69 (25%) for the same creatinine rule over the whole hospital stay; 43 of its 44 are in the hospital-wide cohort. Its members are sicker (mortality 25% vs 16%), and the ratio of mortality ORs, 0.51 [0.36, 0.71], is the one demo interval that excludes 1. The cohorts are nested, which keeps the paired interval narrow; with 100 patients this shows how much the anchoring choice matters, not a real-world effect size.
- **A prediction-study definition selects a different population.** Kamel Rahimi et al.'s Baseline 3 keeps only new AKI on ICU day 2 or 3 in first ICU stays with creatinine on days 1–3, and excludes AKI on day 1. On the demo it flags 15 admissions (5.5%), all inside the hospital-wide KDIGO cohort but overlapping the code-based cohort at Jaccard 0.06. Its members have 6.7% mortality (1 death) against 16–25% for the other AKI definitions, and every ratio of mortality ORs against it excludes 1. With one death the intervals are very wide (up to about 100), and the comparison group includes the sicker patients the definition excludes (see Limitations).
- **Even one paper's own baselines disagree on who has AKI.** Kamel Rahimi et al.'s three baselines flag 18, 16 and 15 demo admissions, the same order as the incidences the paper reports on full MIMIC-IV (21.0%, 18.3%, 16.7%; the paper's percentages are of its eligible cohort, the demo's of all admissions). They share only 62–82% of their combined members (Jaccard 0.62–0.82); their mortality associations cannot be told apart with 1–2 deaths each.
- **Otherwise, no disagreement in the mortality association can be shown at this size.** The other AKI ORs range from 9.4 to 14.3 and the diabetes ORs other than eMERGE from 0.45 to 1.32, and their ratio intervals include 1, some 20-fold wide.

With 100 patients, cohorts are small and intervals wide; these numbers show the tool runs on real data, not how much definitions disagree in practice.

### Scale check

Full MIMIC-IV (about 546,000 admissions) will be timed once credentialed.

| Data | Condition | Admissions | Wall time (s) | Machine |
| --- | --- | --- | --- | --- |
| MIMIC-IV demo | aki / diabetes / readmission | 275 | 1.6 / 1.5 / 1.3 (includes 1,000 bootstrap resamples and Python start-up) | Intel i7-12800HX, 64 GB RAM, Windows |

### Extension: LLM-drafted definitions (planned)

Not started. Planned on branch `cohort-diff-llm` after v0.1.0: pass rates of LLM-drafted definitions on the oracle tests for 3+ models on a 20-item labeled set, with 95% intervals and every failure categorized.

### Correctness

111 tests pass with 99% line coverage on Python 3.11–3.13 (CI). Deliberate breaks show what each kind of test catches:

| Deliberate break | Caught by | Not caught by |
| --- | --- | --- |
| Remove the rounding from the KDIGO 0.3 mg/dL comparison in both the SQL and the oracle | The hand-picked boundary test (0.9 → 1.2 and 1.1 → 1.4 missed) | Every SQL-vs-oracle test, because both shared the bug |
| KDIGO window 48 h → 24 h | SQL vs oracle on synthetic data, and the Hypothesis property test (shrunk to creatinine 1.0 then 2.0 mg/dL, 25 hours apart) | (nothing missed) |
| mimic-code KDIGO without the ICU-discharge bound | SQL vs oracle on synthetic data, the hand-made ICU-window test, and the Hypothesis property test (shrunk to an ICU stay from hour 0 to 6, creatinine 0.5 then 1.0 at hour 7) | (nothing missed) |
| Kamel Rahimi 2023 Baseline 3 with the “corrected” MDRD exponent (−0.867 instead of the printed −0.887) | The hand-made exponent test: creatinine 1.605 in a 60-year-old man is wrongly flagged as AKI | (nothing missed) |
| Kamel Rahimi 2023 Baseline 2 judging day 1 against the day-1 minimum instead of MDRD (so it silently becomes Baseline 1) | The hand-made MDRD test: a woman of 60 with day-1 creatinine 1.3 (above 1.5 × MDRD = 1.23) is wrongly included | (nothing missed) |
| Cheng 2025 diabetes without the ICD-10 version check (`icd_code LIKE 'E11%'` only) | The hand-made code test: an E11 code labelled ICD-9 is wrongly included ({4, 5, 11} instead of {4, 5}) | (nothing missed) |
| eMERGE without the glucose outlier filter (`< 1000` removed) | The hand-made test (lab glucose 1000 with metformin wrongly a case) and the Hypothesis property test (shrunk to one patient with code 25000, no drugs, chart glucose 1000.0) | (nothing missed) |

## Discussion

On synthetic data, where the structure is known, definitions of the same condition overlap little when they use different sources (codes vs labs, Jaccard 0.09–0.16; H1), and four of six pairs disagree about the mortality association beyond sampling noise (ratio intervals excluding 1; H3). High overlap does not guarantee agreement: the two KDIGO rules share 88% of admissions but their ORs differ about threefold.

The open demo shows the same pattern in membership on real data: AKI definitions with almost identical prevalence share at most 56% of their admissions, and diabetes by HbA1c overlaps the other definitions at about 0.12 (H1). The medication phenotype captures the most admissions, as expected (H2). The published diabetes definitions differ mostly in two choices: which side of the 2015 ICD-9/ICD-10 switch their codes cover (Cheng's ICD-10-only rule misses 50 ICD-9-only admissions), and how they treat insulin (eMERGE counts it as a type 1 drug, which removes most coded inpatients). For AKI, H2 was not supported on the demo: the lab rule flagged the same share as the codes (25%), and the synthetic data's 78% came from the generator. Whether the mortality association itself changes with the definition (H3) can mostly not be tested with 100 patients: every ratio interval among the textbook definitions includes 1. The exception is a published one: the mimic-code KDIGO definition, anchored to ICU stays, gives a mortality OR about half that of the hospital-wide rule (ratio 0.51 [0.36, 0.71]). Readmission definitions exclude deaths by construction, so they cannot answer a mortality question at all (H4).

**Strengths.** Definitions are versioned, cited SQL rather than prose; each is checked against an independent implementation and by property tests; known-structure validation on synthetic data; installable with `pip`; reproducible by anyone from open data, a lock file and CI on Python 3.11–3.13.

## Limitations

- **No real-world estimate of disagreement.** The demo has 100 patients; its cohorts and intervals are too small to say how much definitions disagree in practice.
- **Synthetic structure is planted.** Overlaps on synthetic data reflect the generator's assumptions, not real coding or lab practice.
- **KDIGO is creatinine-only** (no urine output) with an in-admission baseline; many studies use pre-admission baselines.
- **Readmission definitions are simplified**; the CMS planned-readmission algorithm is far more detailed.
- **The downstream comparison is members vs all other admissions.** For definitions with their own eligibility rules (such as Kamel Rahimi et al.'s first-ICU-stay, day-1-AKI-excluded cohort), the non-members include patients the paper excluded, so the odds ratio is not the comparison the paper made. Restricting the comparison to each definition's eligible population is a planned extension.
- **Per-patient phenotypes are compared admission by admission.** eMERGE classifies patients and returns all their admissions, so its cohort is weighted toward patients with many admissions (51 admissions from 9 patients on the demo), and its overlap with admission-level definitions mixes the two units.
- **The odds ratio is unadjusted.** It shows how a reported association can move with the definition, not a causal effect.

## Trial and error

What went wrong while building this, and what changed as a result. Analysis problems come first because they affect results; engineering problems follow because they affect reproducibility.

### Analysis and data

| Problem | Why it matters | How it was handled |
| --- | --- | --- |
| A creatinine rise of exactly 0.3 mg/dL can be missed: in floating point, 1.2 − 0.9 = 0.29999999999999993 | KDIGO's 0.3 mg/dL threshold is clinically exact; a naive `>= 0.3` silently drops true AKI cases | The SQL and the oracle round the difference to 6 decimals. Removing the rounding from *both* left every SQL-vs-oracle test green (shared bug); only the hand-picked boundary test failed, on 0.9 → 1.2 and 1.1 → 1.4 (0.7 → 1.0 happens to round correctly) |
| KDIGO-48h flagged 78% of synthetic admissions but 25% of demo admissions | A planted generator artifact (creatinine every 12 h with SD 0.3 mg/dL noise) looked like a property of the rule | Reported both; the synthetic over-capture is attributed to the generator, and synthetic overlaps are used only to validate the tool |
| `dm_hba1c` has no deaths on the demo (17 admissions) | Its odds ratio and every ratio involving it come only from the 0.5 zero-cell correction | Flagged as zero-cell in the Results tables and not interpreted |
| mimic-code compares `creat >= baseline + 0.3` without rounding, so a true 0.3 mg/dL rise from 1.1 to 1.4 is missed (1.1 + 0.3 = 1.4000000000000001), while 0.9 → 1.2 is caught | A faithful reproduction of a published definition must keep its choices, including ones you'd make differently | Implemented as the source states and pinned by a test that expects the miss; the built-in `aki_kdigo_48h` rounds and catches all three cases. The difference is documented in the SQL header |
| The Baseline 1 header said a day-1 "rise" to 1.5 × the day-1 minimum excludes an admission, while another line compared results with the baseline in any order | The two readings differ for a falling day-1 series (2.0 then 1.0): on synthetic data the stricter reading would add 13–21% to the cohort | Found by Claude Code while implementing the definition. Kept the any-order reading (a high, falling day-1 creatinine is AKI already present at ICU admission, which the paper means to exclude), made it the one `Assumed:` line, and added a test |
| Creatinine of 0 (or below) would make every later result "AKI" in Baselines 1 and 2, and distort Baseline 3's pre-ICU mean and 48 h comparison | One impossible value can move a patient in or out of a cohort | Found by Claude Code. Values ≤ 0 are dropped in all three Rahimi baselines (an `Assumed:` line, with tests for each path). The MIMIC-IV demo has none (3,003 creatinine results, minimum 0.1), so demo results are unchanged and differences from other definitions don't come from this filter |
| An ICD-10-only definition (Cheng 2025) and an ICD-9-only one (Zhang & Cao 2023) each describe "type 2 diabetes in MIMIC-IV" | MIMIC-IV spans the October 2015 switch from ICD-9 to ICD-10, so a rule using one version's codes can miss the other part of the timeline | Measured with `notes/check_diabetes_codes.py` (counts only): of 51 code-defined diabetes admissions Cheng's rule misses on the demo, 50 are coded only in ICD-9 |
| Predicted that eMERGE, with ICD-9 codes only, would miss the ICD-10 years the way Cheng misses the ICD-9 ones | A definition's code list is not its cohort: drug + lab paths and the per-patient unit pull in admissions the codes never touch | The demo compare contradicted it (31 of eMERGE's 51 admissions are in the ICD-10 Cheng cohort). `notes/check_emerge.py` then split cases by path and misses by reason (counts only; it asserts its labels reproduce the eMERGE SQL) before any explanation was written. Lesson: measure, then explain |
| eMERGE counts insulin as a type 1 drug | In hospital most people with type 2 diabetes get insulin, so 53 of the 65 coded admissions eMERGE misses are lost to its insulin rules, and no demo case qualified by path 1 | Kept as published, since the point is to reproduce the definition; reported in Results as a property of applying a longitudinal-EHR rule to inpatient data |
| `dm_zhang2023_emerge` has no deaths on the demo (51 admissions, 9 patients) | Two of its ratio intervals exclude 1 only because of the zero-cell correction | Marked zero-cell in the Results tables and not interpreted |
| Four demo rows (Charlson and Cheng pairs) had been placed in the synthetic pair table | A reader would compare demo intervals with synthetic ones | Moved to the demo table when the eMERGE rows were added |
| A wrong time window (24 h instead of KDIGO's 48 h) still produces a plausible-looking cohort | Window edges are where cohort SQL is most often wrong, and a smaller cohort doesn't look broken | Deliberately changing the window to 24 h failed two tests: SQL vs oracle on synthetic data (admissions missing from the SQL cohort), and the Hypothesis property test, which shrank the failure to the minimal case: creatinine 1.0 then 2.0 mg/dL, 25 hours apart |
| A definition that matched no admission still got an odds ratio of 16.16 [0.32, 823.32] | An empty cohort read as a strong, nearly significant association with death, and this is the everyday shape of the ICD-9/ICD-10 mismatch (Cheng's ICD-10-only rule on an ICD-9-era scan): Haldane's 0.5 correction answered from the group sizes after dividing by a zero margin | `odds_ratio` now needs both groups and both outcomes to be non-empty and returns NaN with the reason otherwise; the report prints `n/a` and "Odds ratio not estimable: dm_cheng2025 (no admissions in the cohort)", and the bootstrap leaves out the draws in which a cohort has no death |

### Engineering

| Part | What went wrong | Cause | Fix and lesson |
| --- | --- | --- | --- |
| Setup | The parent lab repository saw the whole Level 1 folder (both projects and the MIMIC-IV demo data) as untracked files | The parent's `.gitignore` had no rule for that folder, although earlier notes said it did | Added the folder to the parent's `.gitignore` before any commit; nothing had been committed. Lesson: verify ignore rules with `git check-ignore -v` and `git status`, not from notes |
| CLI | The Part 5 commit had 2 files instead of 3: the CI workflow still lacked the release job | One of three files to replace was skipped; the commit itself succeeded, so nothing looked wrong | Caught by `git show --stat HEAD` before pushing; replaced the workflow and folded it in with `git commit --amend`. Lesson: compare the commit's file list with the list you expected before `git push` |
| Release | Every CI job warned that Node.js 20 is deprecated | `actions/checkout@v4` and `astral-sh/setup-uv@v5` target Node.js 20, which GitHub is retiring | Warnings only (the TestPyPI rehearsal published). Bumped to `checkout@v5` and `setup-uv@v7` in the release commit, as in ehr-asof. Lesson: read CI annotations even when jobs are green |

## Conclusions

"The same" cohort is often not the same patients: on real MIMIC-IV demo data, AKI definitions agree on at most 56% of their combined admissions and diabetes definitions on as little as 6%. `cohort-diff` makes that difference measurable, with each definition as tested, cited SQL and paired, patient-level intervals for overlap and for the downstream association. Whether those differences change published associations on real data is the question for full MIMIC-IV, where the same code runs unchanged.

## Repository layout

| Path | What it does |
| --- | --- |
| `src/cohort_diff/definitions/` | One SQL file per cohort definition, with a metadata header |
| `src/cohort_diff/registry.py` | Finds and parses definitions (built-in or a path) |
| `src/cohort_diff/engine.py` | DuckDB views over MIMIC tables (folder or DataFrames) |
| `src/cohort_diff/compare.py` | Jaccard, overlap table, cohort description, mortality odds ratio (or why it has none), exclusive mortality per pair, patient-level bootstrap, markdown report |
| `src/cohort_diff/synth.py` | MIMIC-shaped synthetic data |
| `src/cohort_diff/cli.py` | `list`, `run`, `synth`, `compare` |
| `tests/` | Unit, oracle and property-based (Hypothesis) tests |
| `CLAUDE.md` | Project rules for AI coding agents (commands, testing, data safety) |
| `docs/AI_LOG.md` | What was delegated to AI tools, what they got wrong, and how it was caught |

## Reproduce

```bash
uv sync
uv run cohort-diff synth --out data/synth --patients 2000 --seed 0
uv run cohort-diff list
uv run cohort-diff compare --condition aki --data data/synth --out reports/aki.md
uv run cohort-diff compare --condition aki --data path/to/mimic-iv-clinical-database-demo-2.2
```

Development: `uv run ruff format --check src tests`, `uv run ruff check src tests`, `uv run mypy src` (strict), `uv run pytest`, `uv build`.

## Citations

**Data**

- Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2023). MIMIC-IV Clinical Database Demo (version 2.2). PhysioNet. RRID:SCR_007345. https://doi.org/10.13026/dp1f-ex47
- Johnson, A. E. W., Bulgarelli, L., Shen, L., et al. (2023). MIMIC-IV, a freely accessible electronic health record dataset. *Scientific Data*, 10, 1. https://doi.org/10.1038/s41597-022-01899-x
- Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026). PhysioNet as a global platform for biomedical research. *Nature Health*. https://doi.org/10.1038/s44360-026-00096-z

**Published cohort definitions implemented here** (each SQL file's `reference:` line names the exact source)

- `aki_kdigo_mimiccode`: MIT-LCP mimic-code, `mimic-iv/concepts/organfailure/kdigo_creatinine.sql` and `kdigo_stages.sql`, https://github.com/MIT-LCP/mimic-code (read 2026-11-04). Johnson, A. E. W., Stone, D. J., Celi, L. A., & Pollard, T. J. (2018). The MIMIC Code Repository: enabling reproducibility in critical care research. *Journal of the American Medical Informatics Association*, 25(1), 32–39. https://doi.org/10.1093/jamia/ocx084
- `aki_rahimi2023_b1`, `_b2`, `_b3`: Kamel Rahimi, A., Ghadimi, M., van der Vegt, A. H., Canfell, O. J., Pole, J. D., Sullivan, C., & Shrapnel, S. (2023). Machine learning clinical prediction models for acute kidney injury: the impact of baseline creatinine on prediction efficacy. *BMC Medical Informatics and Decision Making*, 23, 207. https://doi.org/10.1186/s12911-023-02306-0

- `dm_charlson_mimiccode`: MIT-LCP mimic-code, `mimic-iv/concepts/comorbidity/charlson.sql`, https://github.com/MIT-LCP/mimic-code (read 2026-11-05); Johnson et al. (2018), above. Codes from Quan, H., Sundararajan, V., Halfon, P., et al. (2005). Coding algorithms for defining comorbidities in ICD-9-CM and ICD-10 administrative data. *Medical Care*, 43(11), 1130–1139.
- `dm_cheng2025`: Cheng, J., Cheng, Q., Wu, Y., Yin, J., & He, F. (2025). Association between triglyceride-glucose-body mass index and adverse prognosis in elderly patients with severe heart failure and type 2 diabetes: a retrospective study based on the MIMIC-IV database. *Cardiovascular Diabetology*, 24, 299. https://doi.org/10.1186/s12933-025-02870-x
- `dm_zhang2023_emerge`: Zhang, W., & Cao, T. (2023). Automated type 2 diabetes case and control identification from the MIMIC-IV database. *AMIA Joint Summits on Translational Science Proceedings*, 2023, 602–611. PMCID: PMC10283086. Algorithm: Kho, A. N., Hayes, M. G., Rasmussen-Torvik, L., et al. (2012). Use of diverse electronic medical record systems to identify genetic risk for type 2 diabetes within a genome-wide association study. *Journal of the American Medical Informatics Association*, 19(2), 212–218. https://doi.org/10.1136/amiajnl-2011-000439

**Clinical criteria behind the built-in definitions**

- Kidney Disease: Improving Global Outcomes (KDIGO) Acute Kidney Injury Work Group (2012). KDIGO Clinical Practice Guideline for Acute Kidney Injury. *Kidney International Supplements*, 2(1), 1–138.

## License

Code: MIT. The MIMIC-IV demo data is distributed by PhysioNet under the Open Data Commons Open Database License v1.0 and is not included in this repository.
