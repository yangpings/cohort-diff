# 18 different cohort definitions on MIMIC-IV

*Numbers come from the open MIMIC-IV demo (100 patients, 275 admissions)*

Papers say "patients with acute kidney injury in MIMIC-IV" or "type 2 diabetes in MIMIC-IV" as if that named one group of 
people, yet every paper has its own set of cohorts. 
I built [cohort-diff](https://github.com/yangpings/cohort-diff) to 
measure how much that choice matters where each definition is a small, cited SQL file with tests, and one command compares 
any set of them on the same data.

| Condition | Definitions | Admissions flagged (of 275) | Overlap between two definitions (Jaccard), as low as |
| --- | --- | --- | --- |
| Acute kidney injury | 7 (4 published) | 15 to 70 | 0.06 |
| Diabetes | 6 (3 published) | 17 to 135 | 0.06 |
| 30/90-day readmission | 5 (3 published) | 49 to 88 | 0.51 |

Jaccard is the share of the combined admissions that two definitions have in common where
1 means the same admissions, 0 means none in common. Definitions with almost the same prevalence 
can still pick different people. For example, ICD codes for AKI and the KDIGO creatinine rule 
each flag about a quarter of admissions, yet only 38% of their combined admissions are in both.

## Story 1

Many MIMIC-IV papers don't write their own AKI rule and use the community SQL in MIT-LCP's mimic-code instead. It applies the same creatinine rule as the textbook KDIGO definition only for icu stays. 
On the demo it flags 44 admissions instead of 69, and those patients are sicker: 25% die in hospital, against 16%. The mortality odds ratio for AKI is about half as large with the ICU-anchored version (ratio of odds ratios 0.51, 95% CI 0.36 to 0.71). Two studies can report "AKI and mortality in MIMIC-IV", use the same creatinine rule, and get different answers because of one line that restricts the time window.

A prediction paper (Kamel Rahimi et al., 2023) reveals its three ways of setting the baseline creatinine flag 18, 16 and 15 admissions on the demo, and they share only 62 to 82% of their members.

## Story 2

The eMERGE type 2 diabetes algorithm, adapted to MIMIC-IV by Zhang and Cao (2023), is a careful decision tree of codes, drugs and lab values. On the demo it returns 51 admissions, but they come from only 9 patients, because it classifies patients and keeps all their admissions. It misses 65 of the 111 admissions with a diabetes code, and 53 of those are lost to one rule: insulin counts as a "type 1" drug. In hospital, insulin is the usual treatment for high blood glucose, so most inpatients with type 2 diabetes look like type 1 to a rule built for longitudinal records. No case on the demo qualified through the simplest path (type 2 code plus a type 2 drug without insulin).

I first predicted the opposite failure. eMERGE uses ICD-9 codes only, and another paper's rule (Cheng et al., 2025) uses ICD-10 only: of the 51 coded admissions it misses, 50 are from before the 2015 switch to ICD-10. I expected eMERGE to be blind to the ICD-10 years. It isn't: a path that needs no code at all (a type 2 drug plus an abnormal lab) brings those years in. The lesson I took: measure first, then explain.

## Story 3

For readmission, a community pipeline's 30-day label (Gupta et al., 2022) and the simplest textbook rule pick almost exactly the same admissions (52 vs 53, Jaccard 0.98). The two 90-day papers flag 32% and 27% of admissions against 19% at 30 days. One of them (Shen et al., 2025) also excludes patients who were never readmitted, so its "not readmitted" group was readmitted later; a query can reproduce its cases, but not that comparison.

Two of Gupta et al.'s rules are not in the paper at all, only in their code: admissions ending in death are removed before readmissions are looked for, and any later admission counts, not only the next one. For a pipeline paper, the code is the definition.

## What testing caught

- **Floating point.** In Python and SQL, 1.2 − 0.9 is 0.29999999999999993, so a rise of exactly 0.3 mg/dL fails a `>= 0.3` test. A hand-made boundary test caught it; comparing my SQL with a second implementation did not, because both had the same bug.
- **A planted artifact.** On synthetic data, the 48-hour KDIGO rule flagged 78% of admissions; on real data, 25%. The synthetic data drew creatinine every 12 hours with noise, and a 0.3 mg/dL rule fires on noise.
- **A typo in a paper.** Kamel Rahimi et al. print an MDRD exponent of −0.887 where the standard formula uses −0.867. The definition keeps the printed value and says so, with a test for it.

One definition (eMERGE) was written by a coding agent from my specification and failing tests, then checked against an independent answer key. It was right, and listed seven choices the paper leaves open.

## Limits

These numbers come from 100 patients. Most mortality comparisons are too uncertain to say whether definitions disagree, and some cohorts have no deaths at all, which makes their odds ratios meaningless. Every comparison is members against all other admissions, not each paper's own control group, and the odds ratios are unadjusted. The same code runs unchanged on full MIMIC-IV, which is the real test.

## Try it

```bash
pip install cohort-diff
cohort-diff synth --out data/synth --patients 2000 --seed 0
cohort-diff compare --condition aki --data data/synth
```

Each definition names its source, quotes the rule as written, and lists every assumption I had to make. If your paper's definition isn't there, it's one SQL file and a test.