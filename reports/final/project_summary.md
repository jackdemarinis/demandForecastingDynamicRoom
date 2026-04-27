# Project Summary

## Data Pipeline

The final modeling table is `processed_data/modeling_daily.csv` with 1,096 daily rows and 209 columns covering 2023-01-01 through 2025-12-31. It joins cleaned room-sales history, reservation forecast fields, and guest-arrival enrichment into one date-grain table.

The operational audit flags include 2 over-capacity rows and 12 zero-room-sold rows. These rows are retained for traceability, but the primary final metric convention uses the exclude-all-flagged sensitivity scenario.

## Feature Engineering

The forecasting features combine calendar variables with lagged and rolling historical demand, ADR, revenue, and occupancy signals. Same-day operational fields and same-day guest-enrichment fields are excluded from learned model inputs to avoid leakage.

## Baseline Model Comparison

Full-data 2025 test metrics:

| Model | Rows | MAE | RMSE | R2 |
| --- | --- | --- | --- | --- |
| xgboost | 365 | 8.039 | 11.210 | 0.539 |
| random_forest | 365 | 8.062 | 10.870 | 0.567 |
| seasonal_previous_week | 365 | 9.551 | 13.438 | 0.338 |
| naive_previous_day | 365 | 11.307 | 15.987 | 0.063 |
| rolling_7d_mean | 365 | 12.528 | 15.107 | 0.164 |
| ridge_regression | 365 | 12.744 | 14.938 | 0.182 |
| rolling_28d_mean | 365 | 13.511 | 16.073 | 0.053 |

On the full test set, the best learned model by MAE is `xgboost` (MAE 8.039, RMSE 11.210, R2 0.539).

## Sensitivity Analysis

Best learned model by test MAE under each data-quality convention:

| Scenario | Model | Rows | MAE | RMSE | R2 |
| --- | --- | --- | --- | --- | --- |
| exclude_all_flagged | xgboost | 354 | 7.443 | 9.927 | 0.585 |
| exclude_over_capacity_only | random_forest | 365 | 8.019 | 10.757 | 0.576 |
| full_data_reference | xgboost | 365 | 8.039 | 11.210 | 0.539 |

Primary reported model result: `xgboost` on `exclude_all_flagged`, with MAE 7.443, RMSE 9.927, and R2 0.585 across 354 test rows. Full-data metrics should also be reported as a reference because they show the model's behavior before anomaly exclusion.

## Feature Importance

Top XGBoost features in the primary exclude-all-flagged training setup:

| Rank | Feature | Importance |
| --- | --- | --- |
| 1 | `target_rooms_sold_lag_7d` | 0.1978 |
| 2 | `target_rooms_sold_lag_14d` | 0.1185 |
| 3 | `block_room_revenue_net_lag_7d` | 0.1046 |
| 4 | `date_day_of_week_cos` | 0.0375 |
| 5 | `block_room_revenue_net_lag_1d` | 0.0331 |
| 6 | `target_rooms_sold_rolling_7d_mean` | 0.0316 |
| 7 | `target_rooms_sold_lag_1d` | 0.0257 |
| 8 | `block_adr_net_rolling_28d_std` | 0.0255 |

The leading predictors are mostly recent same-week and two-week historical demand/revenue features, which is consistent with hotel demand having strong weekly seasonality and short-term persistence.

## Deep Learning Comparison

Exclude-all-flagged 2025 test comparison:

| Model | Rows | MAE | RMSE | R2 |
| --- | --- | --- | --- | --- |
| xgboost | 354 | 7.443 | 9.927 | 0.585 |
| random_forest | 354 | 7.466 | 9.834 | 0.593 |
| gru_56d_wide | 354 | 7.813 | 10.588 | 0.528 |
| gru_56d_more_regularized | 354 | 7.822 | 10.616 | 0.525 |
| transformer_28d_small | 354 | 7.835 | 10.305 | 0.553 |
| gru_42d_balanced | 354 | 7.937 | 10.587 | 0.528 |
| transformer_56d_regularized | 354 | 7.945 | 10.561 | 0.530 |
| gru_84d_compact | 354 | 8.380 | 10.784 | 0.510 |

The best neural-network model is `gru_56d_wide` with MAE 7.813, RMSE 10.588, and R2 0.528. It does not beat the best overall comparison model, `xgboost` (MAE 7.443).

This supports the interpretation that sequence neural networks can get close on this daily demand task, but tree-based tabular models still generalize slightly better on the small dataset. The MLP variants remain materially weaker than the LSTM, GRU, and Transformer variants.

## Pipeline Diagram

The final report figure `reports/figures/final_pipeline_architecture.png` summarizes the full pipeline from raw operational reports through cleaning, modeling, sensitivity analysis, pricing, and business outputs.

## Pricing Recommendation Method

The pricing layer uses the `xgboost` forecast selected from `exclude_all_flagged`. It computes forecast occupancy as forecast rooms sold divided by total property rooms, then applies bounded ADR adjustments to a historical-reference ADR.

Static unflagged 2025 pricing comparison:

| Scenario | Rows | Historical Revenue | Simulated Revenue | Delta | Delta % | Avg Recommended ADR |
| --- | --- | --- | --- | --- | --- | --- |
| aggressive | 354 | $2,018,024.11 | $2,106,125.49 | $88,101.38 | 4.37% | $142.83 |
| conservative | 354 | $2,018,024.11 | $2,062,116.46 | $44,092.35 | 2.18% | $141.46 |

The aggressive scenario uses 4%, 8%, and 12% bands; the conservative scenario uses 2%, 4%, and 6% bands. Both simulations apply recommended ADR to actual realized rooms, so the result is a static counterfactual rather than a demand-response estimate.

Business metric comparison on unflagged 2025 test days:

| Scenario | Actual Occ. | Forecast Occ. | Static Occ. Delta | Historical RevPAR | Simulated RevPAR | RevPAR Delta |
| --- | --- | --- | --- | --- | --- | --- |
| aggressive | 63.63% | 66.13% | 0.00% | $95.01 | $99.16 | $4.15 |
| conservative | 63.63% | 66.13% | 0.00% | $95.01 | $97.09 | $2.08 |

The occupancy delta is intentionally zero in the static pricing simulation because the scenario applies new ADRs to realized rooms sold rather than estimating price elasticity or demand response.

High-demand weekend scenario examples:

| Date | Day | Actual Rooms | Forecast Rooms | Hist. ADR | Aggressive ADR | Conservative ADR | Aggressive Delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-10-25 | Saturday | 59 | 60.0 | $218.36 | $244.56 | $231.46 | $1,545.61 |
| 2025-08-09 | Saturday | 57 | 60.0 | $173.94 | $194.81 | $184.38 | $1,189.38 |
| 2025-11-15 | Saturday | 59 | 60.0 | $166.05 | $185.98 | $176.01 | $1,176.15 |
| 2025-12-06 | Saturday | 60 | 60.0 | $160.63 | $179.91 | $170.27 | $1,156.63 |
| 2025-11-22 | Saturday | 58 | 60.0 | $161.24 | $180.59 | $170.91 | $1,122.11 |
| 2025-05-24 | Saturday | 57 | 59.9 | $237.02 | $265.46 | $251.24 | $1,621.31 |

## Limitations

- Pricing simulations assume rooms sold stay fixed after ADR changes.
- The model does not estimate price elasticity, competitor response, or channel-mix changes.
- January 2025 zero-room-sold flagged dates should be excluded from primary business claims or explained as anomalies.
- The dataset is small for deep learning; tree-based models currently provide stronger and more interpretable MVP results.
