# Hotel Demand Forecasting and Dynamic Room Pricing

CSC 561 Final Project — Jack DeMarinis

End-to-end hotel demand forecasting and pricing-support pipeline built on real
operational hotel data (2023–2025). Raw reservation, room-sales, and
forecast reports are cleaned into a daily modeling table, classical and deep
learning models are compared on a chronological 2025 hold-out, and the
selected forecast is converted into bounded ADR recommendations.

Repository: <https://github.com/jackdemarinis/CSC_561_Final_Project>

## Headline Results

Best forecasting model on the unflagged 2025 test period
(`exclude_all_flagged` convention, 354 rows):

| Model              | MAE   | RMSE   | R²    |
|--------------------|-------|--------|-------|
| **XGBoost**        | 7.443 | 9.927  | 0.585 |
| Random Forest      | 7.466 | 9.834  | 0.593 |
| GRU 56d (wide)     | 7.813 | 10.588 | 0.528 |
| Transformer 28d    | 7.835 | 10.305 | 0.553 |

Static pricing simulation on unflagged 2025 days
(realized rooms sold held fixed):

| Scenario     | Sim. Revenue Δ | Δ %   | RevPAR Δ |
|--------------|----------------|-------|----------|
| Aggressive   | +$88,101.38    | 4.37% | +$4.15   |
| Conservative | +$44,092.35    | 2.18% | +$2.08   |

## Quick start: weights + live UI

End-to-end path that produces real model weights on disk and launches the
Streamlit demo (model + pricing UI) backed by them:

```bash
pip install -r requirements.txt

# Build the modeling table (run once on raw exports / when data changes)
python scripts/clean_new_operational_reports.py
python -m src.features.build_guest_daily_enrichment
python -m src.features.build_daily_modeling_table
python -m src.evaluation.audit_modeling_data_quality

# Train + persist weights (writes models/baselines/*.joblib and
# models/deep_learning/*.{joblib,pt,json})
python -m src.models.train_baselines
python -m src.models.train_deep_learning

# Launch the UI (forecast comparison + live inference + pricing)
streamlit run app/streamlit_app.py
```

`models/` is gitignored; the training scripts above regenerate every
artifact the UI's "Live inference + pricing" tab needs.

The live tab can score historical dates in the modeling table and, for tabular
persisted models such as XGBoost, Random Forest, Ridge, and MLP, future dates up
to one year after the last observed row. Future scoring is recursive: the model
uses calendar features plus lag/rolling features from the observed history, then
uses earlier forecasts as history for later future days. Because future dates do
not have realized hotel outcomes yet, actual rooms sold, historical ADR, and
simulated-vs-historical revenue columns are blank for those rows. The forecast
rooms, forecast occupancy, recommended ADR, and forecast revenue columns are the
usable forward-looking outputs.

## Repository Layout

```
Data/                         raw operational workbooks (input)
Documents/                    project proposal and assignment
cleaned_data/                 cleaned operational datasets
processed_data/               daily modeling table + enrichment
scripts/
  clean_new_operational_reports.py
src/
  features/
    build_guest_daily_enrichment.py
    build_daily_modeling_table.py
  models/
    train_baselines.py        Ridge, RF, XGBoost, simple baselines
    train_deep_learning.py    MLP, LSTM, GRU, Transformer
  evaluation/
    audit_modeling_data_quality.py
    run_baseline_sensitivity.py
    build_final_report_artifacts.py
    build_report_summary.py
  pricing/
    build_pricing_recommendations.py
reports/
  audit/                      data-quality flags
  baselines/                  baseline + sensitivity metrics
  deep_learning/              neural model metrics
  pricing/                    ADR recs + business metrics
  figures/                    PNG figures used in the paper
  final/                      IEEE LaTeX source, bibliography, PDF
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.10+. Core dependencies: pandas, scikit-learn, xgboost,
torch, matplotlib, seaborn, openpyxl.

## Reproducing the Pipeline

Run from the repository root, in order:

```bash
# 1. Clean raw operational exports into cleaned_data/
python scripts/clean_new_operational_reports.py

# 2. Build daily guest enrichment
python -m src.features.build_guest_daily_enrichment

# 3. Build the date-grain modeling table (processed_data/modeling_daily.csv)
python -m src.features.build_daily_modeling_table

# 4. Audit data quality (writes reports/audit/data_quality_flags.csv)
python -m src.evaluation.audit_modeling_data_quality

# 5. Train baselines (Ridge, RF, XGBoost, simple time-series baselines)
python -m src.models.train_baselines

# 6. Sensitivity across data-quality conventions
python -m src.evaluation.run_baseline_sensitivity

# 7. Train deep learning models (MLP, LSTM, GRU, Transformer)
python -m src.models.train_deep_learning

# 8. Build pricing recommendations and business metrics
python -m src.pricing.build_pricing_recommendations

# 9. Assemble final report artifacts (tables + figures)
python -m src.evaluation.build_final_report_artifacts
python -m src.evaluation.build_report_summary
```

To rebuild the IEEE PDF:

```bash
cd reports/final
pdflatex final_report_ieee.tex
bibtex   final_report_ieee
pdflatex final_report_ieee.tex
pdflatex final_report_ieee.tex
```

## Modeling Notes

- **Target:** `target_rooms_sold` (daily property-level rooms sold).
- **Modeling table:** 1,096 daily rows × 209 columns, 2023-01-01 to
  2025-12-31, no missing or duplicate business dates.
- **Splits (chronological):** train through 2024-06-30, validation
  2024-07-01 to 2024-12-31, test calendar year 2025.
- **Leakage control:** same-day operational fields, same-day guest
  enrichment, and raw future ReservationForecast values are excluded from
  learned model inputs. Lags and rolling windows are shifted so the
  current day's target never appears in features.
- **Primary convention:** `exclude_all_flagged` — drops 14 audited
  anomaly rows (12 zero-room-sold dates, 2 over-capacity dates).

## Pricing Layer

Bounded decision-support rule on top of the XGBoost forecast:

1. Convert forecast rooms sold to forecast occupancy (60-room property).
2. Choose a reference ADR from same-day historical, then rolling and
   lagged ADR fallbacks, then a median nonzero fallback.
3. Apply demand-band adjustments:
   - **Aggressive:** ±4 / ±8 / ±12 % bands.
   - **Conservative:** ±2 / ±4 / ±6 % bands.
4. Bound recommendations by min ADR, max ADR, and a 20% maximum daily
   move from the reference ADR.

Simulation is **static**: recommended ADR is applied to actual realized
rooms sold. It does not model price elasticity, competitor reaction, or
distribution effects.

## Key Artifacts

- `processed_data/modeling_daily.csv` — modeling table.
- `reports/audit/data_quality_flags.csv` — anomaly review records.
- `reports/baselines/`, `reports/deep_learning/` — model metrics.
- `reports/pricing/` — ADR recommendations, scenario comparison,
  high-demand examples.
- `reports/final/final_report_ieee.pdf` — IEEE-format report.

## Privacy

GuestNameList exports contain PII (names, emails, comments, confirmation
and folio numbers). These fields are used only for cleaning and
deduplication and are explicitly excluded from modeling features. The
daily enrichment output aggregates to non-identifying daily counts,
shares, and rates.

## Limitations

- Pricing simulation does not model demand response to price changes.
- No competitor-rate or external-event feed in the current MVP.
- Small dataset (≈3 years of daily records); deep sequence models are
  competitive but do not surpass XGBoost.
- January 2025 zero-room-sold dates are flagged as likely operational
  anomalies and should be verified before use as business evidence.
