from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
CLEANED_DIR = REPO_ROOT / "cleaned_data"
PROCESSED_DIR = REPO_ROOT / "processed_data"

GUEST_STAYS_INPUT = CLEANED_DIR / "guest_stays_cleaned.csv"
GUEST_DAILY_OUTPUT = PROCESSED_DIR / "guest_daily_enrichment.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "guest_daily_enrichment_summary.json"

PII_COLUMNS_EXCLUDED = ["guest_name", "email", "comments", "confirmation_number", "folio_number", "room_number"]
STATUS_VALUES = ["Checked-Out", "Cancelled", "No-Show", "Wait List"]


def slug(value: object) -> str:
    text = "missing" if pd.isna(value) else str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "missing"


def read_guest_stays() -> pd.DataFrame:
    guest = pd.read_csv(GUEST_STAYS_INPUT, parse_dates=["arrival_date", "departure_date"])
    return guest.sort_values(["arrival_date", "departure_date"]).reset_index(drop=True)


def add_normalized_fields(guest: pd.DataFrame) -> pd.DataFrame:
    result = guest.copy()
    result["valid_rate"] = result["rate"].where(result["rate"].between(0, 1000, inclusive="both"))
    result["valid_nights"] = result["nights"].where(result["nights"] > 0)
    result["market_segment_slug"] = result["market_segment"].map(slug)
    result["room_type_slug"] = result["room_type"].map(slug)
    result["status_slug"] = result["status"].map(slug)
    return result


def top_values(frame: pd.DataFrame, column: str, *, limit: int = 12) -> list[str]:
    counts = frame[column].value_counts(dropna=False)
    return [slug(value) for value in counts.head(limit).index]


def build_arrival_features(guest: pd.DataFrame) -> pd.DataFrame:
    grouped = guest.groupby("arrival_date", dropna=False)
    daily = grouped.agg(
        guest_arrivals_total=("cleaned_record_id", "count"),
        guest_arrival_checked_out=("status", lambda values: int((values == "Checked-Out").sum())),
        guest_arrival_cancelled=("status", lambda values: int((values == "Cancelled").sum())),
        guest_arrival_no_show=("status", lambda values: int((values == "No-Show").sum())),
        guest_arrival_wait_list=("status", lambda values: int((values == "Wait List").sum())),
        guest_arrival_avg_rate=("valid_rate", "mean"),
        guest_arrival_median_rate=("valid_rate", "median"),
        guest_arrival_avg_nights=("valid_nights", "mean"),
        guest_arrival_median_nights=("valid_nights", "median"),
        guest_arrival_total_booked_room_nights=("valid_nights", "sum"),
        guest_arrival_avg_adults=("adults_raw_primary", "mean"),
        guest_arrival_duplicate_source_occurrences=("source_occurrences", "sum"),
    )
    daily.index.name = "business_date"
    daily = daily.reset_index()

    status_count_columns = [
        "guest_arrival_checked_out",
        "guest_arrival_cancelled",
        "guest_arrival_no_show",
        "guest_arrival_wait_list",
    ]
    for column in status_count_columns:
        daily[f"{column}_share"] = daily[column] / daily["guest_arrivals_total"].replace(0, np.nan)

    for category_column, prefix in [
        ("market_segment_slug", "guest_market_segment"),
        ("room_type_slug", "guest_room_type"),
    ]:
        selected_values = top_values(guest, category_column)
        pivot = (
            guest.loc[guest[category_column].isin(selected_values)]
            .pivot_table(
                index="arrival_date",
                columns=category_column,
                values="cleaned_record_id",
                aggfunc="count",
                fill_value=0,
            )
            .rename_axis(index="business_date", columns=None)
            .reset_index()
        )
        rename_map = {value: f"{prefix}_{value}_arrivals" for value in selected_values if value in pivot.columns}
        pivot = pivot.rename(columns=rename_map)
        daily = daily.merge(pivot, on="business_date", how="left")
        for count_column in rename_map.values():
            daily[count_column] = daily[count_column].fillna(0).astype(int)
            daily[count_column.replace("_arrivals", "_arrival_share")] = (
                daily[count_column] / daily["guest_arrivals_total"].replace(0, np.nan)
            )

    return daily


def build_stay_date_features(guest: pd.DataFrame) -> pd.DataFrame:
    stay_rows: list[dict] = []
    stayed = guest.loc[
        (guest["status"] == "Checked-Out")
        & guest["arrival_date"].notna()
        & guest["departure_date"].notna()
        & (guest["departure_date"] > guest["arrival_date"])
        & (guest["valid_nights"] > 0)
    ].copy()

    for row in stayed.itertuples(index=False):
        for business_date in pd.date_range(row.arrival_date, row.departure_date - pd.Timedelta(days=1), freq="D"):
            stay_rows.append(
                {
                    "business_date": business_date,
                    "guest_stay_room_nights_proxy": 1,
                    "guest_stay_rate": row.valid_rate,
                    "guest_stay_revenue_proxy": row.valid_rate,
                    "guest_stay_adults": row.adults_raw_primary,
                }
            )

    if not stay_rows:
        return pd.DataFrame(
            columns=[
                "business_date",
                "guest_stay_room_nights_proxy",
                "guest_stay_avg_rate",
                "guest_stay_revenue_proxy",
                "guest_stay_avg_adults",
            ]
        )

    stay_frame = pd.DataFrame(stay_rows)
    daily = (
        stay_frame.groupby("business_date")
        .agg(
            guest_stay_room_nights_proxy=("guest_stay_room_nights_proxy", "sum"),
            guest_stay_avg_rate=("guest_stay_rate", "mean"),
            guest_stay_revenue_proxy=("guest_stay_revenue_proxy", "sum"),
            guest_stay_avg_adults=("guest_stay_adults", "mean"),
        )
        .reset_index()
    )
    return daily


def build_guest_daily_enrichment() -> tuple[pd.DataFrame, dict]:
    guest = add_normalized_fields(read_guest_stays())
    start_date = guest["arrival_date"].min()
    end_date = guest["arrival_date"].max()
    spine = pd.DataFrame({"business_date": pd.date_range(start_date, end_date, freq="D")})
    spine["guest_source_available"] = 1

    arrivals = build_arrival_features(guest)
    stay_dates = build_stay_date_features(guest)
    daily = spine.merge(arrivals, on="business_date", how="left").merge(stay_dates, on="business_date", how="left")

    count_like = [
        column
        for column in daily.columns
        if column.startswith("guest_")
        and (
            column.endswith("_total")
            or column.endswith("_checked_out")
            or column.endswith("_cancelled")
            or column.endswith("_no_show")
            or column.endswith("_wait_list")
            or column.endswith("_arrivals")
            or column.endswith("_room_nights_proxy")
            or column.endswith("_booked_room_nights")
            or column.endswith("_duplicate_source_occurrences")
        )
    ]
    for column in count_like:
        daily[column] = daily[column].fillna(0)

    numeric_columns = daily.select_dtypes(include=[np.number]).columns
    daily[numeric_columns] = daily[numeric_columns].round(6)

    summary = {
        "output_file": str(GUEST_DAILY_OUTPUT.relative_to(REPO_ROOT)),
        "source_file": str(GUEST_STAYS_INPUT.relative_to(REPO_ROOT)),
        "row_count": int(len(daily)),
        "column_count": int(len(daily.columns)),
        "date_coverage": {
            "start": daily["business_date"].min().date().isoformat(),
            "end": daily["business_date"].max().date().isoformat(),
        },
        "raw_guest_records": int(len(guest)),
        "pii_columns_excluded": PII_COLUMNS_EXCLUDED,
        "status_counts": guest["status"].value_counts(dropna=False).to_dict(),
        "data_quality_notes": {
            "records_with_nonpositive_nights": int((guest["nights"] <= 0).sum()),
            "records_with_rate_over_1000": int((guest["rate"] > 1000).sum()),
            "records_with_missing_market_segment": int(guest["market_segment"].isna().sum()),
            "records_with_missing_room_type": int(guest["room_type"].isna().sum()),
        },
        "feature_notes": [
            "Arrival features are grouped by arrival_date.",
            "Stay-date features use Checked-Out records with positive nights and expand each stay across arrival_date through departure_date minus one day.",
            "PII fields are not written to the daily enrichment output.",
            "The guest-list source mainly covers 2025, so these features are enrichment/context rather than fully trainable history for 2023-2024 baselines.",
        ],
    }
    return daily, summary


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    daily, summary = build_guest_daily_enrichment()
    daily.to_csv(GUEST_DAILY_OUTPUT, index=False, date_format="%Y-%m-%d")
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {GUEST_DAILY_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {SUMMARY_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Rows: {summary['row_count']:,}")
    print(
        "Coverage: "
        f"{summary['date_coverage']['start']} through {summary['date_coverage']['end']}"
    )


if __name__ == "__main__":
    main()
