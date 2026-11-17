# Human study analysis: anibench-e4-dryrun

20 clips, 60 ratings, 3 raters kept, 1 excluded by attention checks (need 4 correct). Ties in the overall majority: 0. CIs: 95% bootstrap over tasks, 10000 resamples.

## Raters

| rater | rated | attention | median s/clip | pass rate | excluded |
|---|---|---|---|---|---|
| FAKE-R1 | 25 | 5/5 | 25.45 | 0.45 |  |
| FAKE-R2 | 25 | 5/5 | 29.80 | 0.35 |  |
| FAKE-R3 | 25 | 5/5 | 26.75 | 0.50 |  |
| FAKE-R4 | 25 | 2/5 | 20.20 | 1.00 | yes |

## Inter-rater agreement

| | Fleiss' kappa | Krippendorff's alpha | items | prevalence |
|---|---|---|---|---|
| overall (broken) | 0.59 [0.23, 0.85] | 0.60 | 20 | 0.60 |
| outside_moved | 0.65 [0.30, 0.88] | 0.65 | 20 | 0.40 |
| tore_split | 0.48 [-0.03, 0.84] | 0.49 | 20 | 0.15 |
| size_shape | 0.61 [0.33, 0.86] | 0.62 | 20 | 0.40 |
| barely_moves | 1.00 [1.00, 1.00] | 1.00 | 20 | 0.05 |
| wrong_pivot | 0.47 [0.27, 0.70] | 0.48 | 20 | 0.35 |
| loop_jump | 0.56 [0.27, 0.81] | 0.57 | 20 | 0.45 |
| other | -- | -- | 20 | 0.00 |

## Agreement with the human majority (overall: broken or not)

| evaluator | n | accuracy | precision | recall | kappa |
|---|---|---|---|---|---|
| Human (one vs. rest) | 48 | 0.88 [0.73, 0.96] | 0.92 [0.75, 1.00] | 0.86 [0.63, 0.97] | 0.75 [0.37, 0.92] |
| Pixel checks | 20 | 0.95 [0.84, 1.00] | 1.00 [1.00, 1.00] | 0.92 [0.73, 1.00] | 0.90 [0.64, 1.00] |
| judge:fake-judge-1 | 20 | 0.70 [0.48, 0.89] | 0.75 [0.50, 1.00] | 0.75 [0.44, 1.00] | 0.37 [-0.05, 0.79] |

## Per defect (Cohen's kappa vs the human majority for that defect)

| defect | checks | Human (one vs. rest) | Pixel checks | judge:fake-judge-1 |
|---|---|---|---|---|
| outside_moved | G1 | 0.78 [0.36, 0.94] (n=50) | 0.80 [0.49, 1.00] (n=20) | 0.57 [0.15, 1.00] (n=20) |
| tore_split | G2/G2b | 0.56 [-0.08, 0.91] (n=52) | 1.00 [1.00, 1.00] (n=12) | 0.46 [0.00, 1.00] (n=20) |
| size_shape | G3 | 0.72 [0.00, 0.92] (n=50) | 1.00 [1.00, 1.00] (n=20) | 0.89 [0.63, 1.00] (n=20) |
| barely_moves | G4 | 1.00 [1.00, 1.00] (n=60) | 1.00 [1.00, 1.00] (n=20) | -0.05 [-0.12, 0.00] (n=20) |
| wrong_pivot | G5 | 0.45 [0.00, 0.81] (n=48) | 1.00 [1.00, 1.00] (n=15) | 0.43 [-0.04, 0.79] (n=20) |
| loop_jump | G6 | 0.67 [0.00, 0.89] (n=48) | 0.90 [0.66, 1.00] (n=20) | 0.58 [0.23, 0.89] (n=20) |
| other | -- | -- (n=60) | -- | -- (n=20) |
