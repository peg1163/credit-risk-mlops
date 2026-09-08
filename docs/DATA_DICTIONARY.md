# Data and feature dictionary

## Core dates

- `loan.date`: loan grant/origination date.
- `period` / `observation_date`: calendar month-end snapshot and inference cutoff.
- `data_available_date`: month-end; never later than observation date.
- `event_date`: first month with a negative balance; label-only field.
- `label_maturity_date`: observation date plus six month-ends.
- `training_cutoff`: 1995-12-31.

## Features

All rolling values include transactions no later than the observation month. Numeric nulls are median-imputed inside the model; categoricals are mode-imputed and one-hot encoded.

| Feature | Source / calculation | Window | Type | Leakage / inference |
|---|---|---:|---|---|
| loan_age_months | Months from loan grant to observation | to date | int | Safe; available |
| loan_amount | Contract principal | origination | float | Safe; available |
| loan_duration | Contract duration in months | origination | int | Safe; available |
| scheduled_payment | Contract payment | origination | float | Safe; available |
| current_balance | Last transaction balance in month | current | float | Safe at cutoff |
| balance_mean_3m | Mean of monthly mean balances | 3m | float | Past/current only |
| balance_min_3m | Minimum observed balance | 3m | float | Past/current only; eligible population excludes prior negative event |
| balance_change_3m | Current balance minus balance three months prior | 3m | float | Past/current only |
| credit_sum_3m | Credits received | 3m | float | Past/current only |
| withdrawal_sum_3m | Withdrawals | 3m | float | Past/current only |
| net_flow_3m | Credits minus withdrawals | 3m | float | Past/current only |
| transaction_count_3m | Transaction count | 3m | int | Past/current only |
| sanction_count_3m | Sanction-interest transaction count | 3m | int | Past/current only; proxy may be operationally unavailable elsewhere |
| loan_payment_sum_3m | Transactions categorized as loan payments | 3m | float | Past/current only |
| current_payment_ratio | 3m payments / (3 × scheduled payment) | 3m | float | Past/current only |
| district_id | Branch/account district | static | category | Available; geography/fairness review required |
| statement_frequency | Account statement cadence | static | category | Available |

Direct loan status, event date, maturity date and target are prohibited features.

