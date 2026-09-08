# Model Card — logistic regression v0.1.0

## Intended use

Educational ranking of active loan accounts by probability of first severe financial distress (negative balance) in the next six months. Not validated for real credit decisions, Czech banking today, mortgages, or 90+ DPD.

## Training design

- Train: through 1995-12, 2,726 snapshots / 45 events.
- Validation: 1996, 2,906 / 57.
- Test OOT: 1997, 4,583 / 64.
- Replay: 1998. Labels through 1998-06 can mature; later observations are censored.
- Model: standardized/imputed logistic regression, `C=0.5`, balanced class weights, seed 42.
- Decision threshold: 0.75, selected by validation F1 only. This is a demonstration operating point, not a business-approved cutoff.

## Executed metrics

| Split | ROC-AUC | KS | PR-AUC | Brier | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| Train | 0.9853 | 0.9575 | 0.3590 | 0.0471 | 0.3385 | 0.9778 |
| Validation | 0.8167 | 0.4809 | 0.1974 | 0.0415 | 0.2687 | 0.3158 |
| Test OOT | 0.8637 | 0.6257 | 0.0745 | 0.0449 | 0.0923 | 0.1875 |

Test confusion matrix: TN 4,401; FP 118; FN 52; TP 12. Detailed monthly, amount-segment, score and calibration results are in `artifacts/detailed_evaluation.json`.

## Limitations and risks

The sample is small, old, from one Czech bank, and contains repeated snapshots per account. Overlapping six-month horizons make rows dependent; metrics are therefore descriptive and not confidence intervals. Balanced class weights produce poor probability calibration (top score decile mean 0.569 versus event rate 0.061). The model is useful for MLOps exercises, not probability-based decisions. Train-to-validation degradation suggests temporal shift/overfit. `district_id` can encode geography and requires fairness/governance review. The target is a proxy and cannot be compared with mortgage 90+ DPD.

