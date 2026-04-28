# Data Examples (Sanitized Schema Samples)

The actual operational data used to build the modeling table in this project
is **not publicly available**. The raw exports come from a real independent
hotel's reservations and reporting system and contain commercially sensitive
revenue information as well as guest personally identifiable information
(names, emails, confirmation and folio numbers, free-text comments).

This folder contains **synthetic, sanitized example CSVs** that show only the
schema (column names and column types) of the cleaned and processed datasets
used by the pipeline. Every value in these examples is fabricated for
illustration. They are intended as a reference for the appendix of the IEEE
report so that a reader can understand the shape of the inputs without seeing
the underlying private data.

## Files

| File | Mirrors | Purpose |
|---|---|---|
| `block_roomsales_daily_totals_example.csv` | `cleaned_data/block_roomsales_daily_totals_cleaned.csv` | Daily property-level rooms sold, ADR, RevPAR. |
| `block_roomsales_room_type_daily_example.csv` | `cleaned_data/block_roomsales_room_type_daily_cleaned.csv` | Same daily totals broken down by room type. |
| `block_roomsales_room_class_daily_example.csv` | `cleaned_data/block_roomsales_room_class_daily_cleaned.csv` | Daily totals broken down by room class. |
| `block_roomsales_adjustments_example.csv` | `cleaned_data/block_roomsales_adjustments_cleaned.csv` | Adjustment-row exceptions in Block reports. |
| `reservation_forecast_daily_example.csv` | `cleaned_data/reservation_forecast_daily_cleaned.csv` | Daily reservation forecast metrics. |
| `guest_stays_example.csv` | `cleaned_data/guest_stays_cleaned.csv` | Reservation-level stay records (PII columns are present in the schema but contain only synthetic placeholder values here). |
| `guest_daily_enrichment_example.csv` | `processed_data/guest_daily_enrichment.csv` | Non-identifying daily aggregates from the guest stays file. |
| `modeling_daily_example.csv` | `processed_data/modeling_daily.csv` | Final date-grain modeling table used by all forecasting models. |

## What is and is not in here

- **Included:** column names, column ordering, and a small number of synthetic
  rows that demonstrate the expected dtypes (dates, integers, floats,
  categorical strings).
- **Not included:** any real business date with real rooms sold, real ADR,
  real revenue, real occupancy, or any real guest record. The examples cannot
  be used to retrain the model or to back-derive the property's performance.

## How the real data is structured

The pipeline that produces the real (private) versions of these files is
fully open and lives in:

- `scripts/clean_new_operational_reports.py` — raw `.xls`/`.xlsx` to
  `cleaned_data/`.
- `src/features/build_guest_daily_enrichment.py` — guest stays to daily
  aggregates.
- `src/features/build_daily_modeling_table.py` — joins everything into the
  final 1,096-row modeling table.

A reader who has comparable hotel operational exports can run the pipeline
unchanged and produce the same column structure.
