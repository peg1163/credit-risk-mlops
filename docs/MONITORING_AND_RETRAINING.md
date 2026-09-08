# Monitoring and retraining policy

## Data controls per batch

Fail the batch for schema/type mismatch, duplicate `(account_id, trans_id)`, future transaction dates, checksum mismatch, non-monotonic replay, or missing required columns. Alert for volume outside 50–150% of recent median, null-rate change above 5 percentage points, unseen categories, or implausible negative amounts.

## Model monitoring

- Every batch: score distribution, decision rate, feature null/range checks, PSI against train and prior three months.
- When six-month labels mature: ROC-AUC, PR-AUC, KS, Brier and calibration deciles overall, monthly and by loan-amount segment.
- Investigate PSI >= 0.10; treat >= 0.25 as material. These are investigation thresholds, not automatic retraining triggers.
- Investigate OOT ROC-AUC below 0.75, KS below 0.30, Brier deterioration >25% relative to the 0.0449 test reference, or recall below 0.15 at the fixed threshold for two mature cohorts.

Data drift is a change in inputs; prediction drift is a change in scores; concept drift is a change in the relationship between inputs and outcome; performance degradation is the measured loss once labels mature. Only the last two provide direct scientific evidence that the model relationship has weakened.

## Challenger acceptance

Train only after data-quality review and enough matured events. A challenger must use the same OOT cohorts, pass inference/schema tests, show no material segment regression, maintain or improve calibration, and demonstrate an operationally meaningful benefit. A higher aggregate AUC alone is insufficient. Promotion requires human approval; retain champion artifact, threshold, image digest, data ID and rollback procedure.

