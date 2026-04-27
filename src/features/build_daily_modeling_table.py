from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
CLEANED_DIR = REPO_ROOT / "cleaned_data"
PROCESSED_DIR = REPO_ROOT / "processed_data"

BLOCK_DAILY_INPUT = CLEANED_DIR / "block_roomsales_daily_totals_cleaned.csv"
RESERVATION_FORECAST_INPUT = CLEANED_DIR / "reservation_forecast_daily_cleaned.csv"
GUEST_DAILY_INPUT = PROCESSED_DIR / "guest_daily_enrichment.csv"

MODELING_OUTPUT = PROCESSED_DIR / "modeling_daily.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "modeling_daily_summary.json"

TARGET_COLUMN = "target_rooms_sold"
LAG_BASE_COLUMNS = [
    "target_rooms_sold",
    "block_adr_net",
    "block_room_revenue_net",
    "block_occupancy_rate_reported",
]
LAG_DAYS = [1, 7, 14, 28, 365]
ROLLING_WINDOWS = [7, 14, 28, 56]


def read_daily_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["business_date"])
    if frame["business_date"].duplicated().any():
        duplicate_dates = (
            frame.loc[frame["business_date"].duplicated(), "business_date"]
            .dt.date.astype(str)
            .unique()
            .tolist()
        )
        raise ValueError(f"{path.name} has duplicate business_date values: {duplicate_dates[:10]}")
    return frame.sort_values("business_date").reset_index(drop=True)


def missing_daily_dates(dates: pd.Series) -> list[str]:
    if dates.empty:
        return []
    full_range = pd.date_range(dates.min(), dates.max(), freq="D")
    missing = full_range.difference(pd.DatetimeIndex(dates))
    return [value.date().isoformat() for value in missing]


def build_block_spine(block_daily: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "source_file": "block_source_file",
        "source_sheet": "block_source_sheet",
        "source_row": "block_source_row",
        "report_period_start": "block_report_period_start",
        "report_period_end": "block_report_period_end",
        "occupancy_rate_reported": "block_occupancy_rate_reported",
        "rooms_sold": TARGET_COLUMN,
        "transient_rooms": "block_transient_rooms",
        "group_rooms": "block_group_rooms",
        "day_use_rooms": "block_day_use_rooms",
        "comp_rooms": "block_comp_rooms",
        "out_of_order_rooms": "block_out_of_order_rooms",
        "on_market_rooms": "block_on_market_rooms",
        "room_revenue_gross": "block_room_revenue_gross",
        "adr_gross": "block_adr_gross",
        "revpar_gross": "block_revpar_gross",
        "room_revenue_net": "block_room_revenue_net",
        "adr_net": "block_adr_net",
        "revpar_net": "block_revpar_net",
    }
    keep_columns = ["business_date", "property_total_rooms", *rename_map.keys()]
    return block_daily[keep_columns].rename(columns=rename_map)


def build_reservation_features(reservation_daily: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "source_file": "rf_source_file",
        "source_sheet": "rf_source_sheet",
        "source_row": "rf_source_row",
        "report_period_start": "rf_report_period_start",
        "report_period_end": "rf_report_period_end",
        "arrivals": "rf_arrivals",
        "departures": "rf_departures",
        "stayovers": "rf_stayovers",
        "projected_walk_ins": "rf_projected_walk_ins",
        "projected_cxl_no_show_rate": "rf_projected_cxl_no_show_rate",
        "rooms_sold": "rf_rooms_sold",
        "total_comp_rooms": "rf_total_comp_rooms",
        "out_of_order_rooms": "rf_out_of_order_rooms",
        "occupancy_rate_reported": "rf_occupancy_rate_reported",
        "room_revenue_net": "rf_room_revenue_net",
        "adr_reported": "rf_adr_reported",
        "revpar_reported": "rf_revpar_reported",
        "transient_rooms": "rf_transient_rooms",
        "group_rooms_picked_up": "rf_group_rooms_picked_up",
        "group_rooms_not_picked_up": "rf_group_rooms_not_picked_up",
        "group_room_revenue_net": "rf_group_room_revenue_net",
        "group_adr_reported": "rf_group_adr_reported",
        "group_non_gtd_arrivals": "rf_group_non_gtd_arrivals",
        "group_gtd_arrivals": "rf_group_gtd_arrivals",
        "group_comp_rooms": "rf_group_comp_rooms",
        "total_group_guests_in_house": "rf_total_group_guests_in_house",
    }
    keep_columns = ["business_date", *rename_map.keys()]
    return reservation_daily[keep_columns].rename(columns=rename_map)


def read_guest_daily_features() -> pd.DataFrame | None:
    if not GUEST_DAILY_INPUT.exists():
        return None
    guest_daily = pd.read_csv(GUEST_DAILY_INPUT, parse_dates=["business_date"])
    if guest_daily["business_date"].duplicated().any():
        duplicate_dates = (
            guest_daily.loc[guest_daily["business_date"].duplicated(), "business_date"]
            .dt.date.astype(str)
            .unique()
            .tolist()
        )
        raise ValueError(f"{GUEST_DAILY_INPUT.name} has duplicate business_date values: {duplicate_dates[:10]}")
    return guest_daily.sort_values("business_date").reset_index(drop=True)


def add_date_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    dates = result["business_date"]
    iso_calendar = dates.dt.isocalendar()

    result["date_year"] = dates.dt.year
    result["date_quarter"] = dates.dt.quarter
    result["date_month"] = dates.dt.month
    result["date_day"] = dates.dt.day
    result["date_day_of_week"] = dates.dt.dayofweek
    result["date_day_of_year"] = dates.dt.dayofyear
    result["date_iso_week"] = iso_calendar.week.astype(int)
    result["date_is_weekend"] = dates.dt.dayofweek.isin([5, 6]).astype(int)
    result["date_is_month_start"] = dates.dt.is_month_start.astype(int)
    result["date_is_month_end"] = dates.dt.is_month_end.astype(int)
    result["date_is_quarter_start"] = dates.dt.is_quarter_start.astype(int)
    result["date_is_quarter_end"] = dates.dt.is_quarter_end.astype(int)

    # Cyclical encodings let linear models see calendar wraparound points.
    result["date_day_of_week_sin"] = np.sin(2 * np.pi * result["date_day_of_week"] / 7)
    result["date_day_of_week_cos"] = np.cos(2 * np.pi * result["date_day_of_week"] / 7)
    result["date_month_sin"] = np.sin(2 * np.pi * result["date_month"] / 12)
    result["date_month_cos"] = np.cos(2 * np.pi * result["date_month"] / 12)
    result["date_day_of_year_sin"] = np.sin(2 * np.pi * result["date_day_of_year"] / 365.25)
    result["date_day_of_year_cos"] = np.cos(2 * np.pi * result["date_day_of_year"] / 365.25)
    return result


def add_history_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values("business_date").reset_index(drop=True).copy()

    for column in LAG_BASE_COLUMNS:
        for lag_day in LAG_DAYS:
            result[f"{column}_lag_{lag_day}d"] = result[column].shift(lag_day)

        shifted = result[column].shift(1)
        for window in ROLLING_WINDOWS:
            result[f"{column}_rolling_{window}d_mean"] = shifted.rolling(window).mean()
            result[f"{column}_rolling_{window}d_median"] = shifted.rolling(window).median()
            result[f"{column}_rolling_{window}d_std"] = shifted.rolling(window).std()

    result["target_rooms_sold_minus_7d"] = (
        result["target_rooms_sold_lag_1d"] - result["target_rooms_sold_lag_7d"]
    )
    result["block_adr_net_minus_7d"] = result["block_adr_net_lag_1d"] - result["block_adr_net_lag_7d"]
    result["block_room_revenue_net_minus_7d"] = (
        result["block_room_revenue_net_lag_1d"] - result["block_room_revenue_net_lag_7d"]
    )
    return result


def add_definition_checks(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["block_occupancy_calc_on_total_rooms"] = (
        result[TARGET_COLUMN] / result["property_total_rooms"]
    ).round(4)
    result["block_occupancy_calc_on_market_rooms"] = (
        result[TARGET_COLUMN] / result["block_on_market_rooms"].replace(0, np.nan)
    ).round(4)
    result["block_reported_occ_minus_total_room_calc"] = (
        result["block_occupancy_rate_reported"] - result["block_occupancy_calc_on_total_rooms"]
    ).round(4)
    result["block_reported_occ_minus_on_market_calc"] = (
        result["block_occupancy_rate_reported"] - result["block_occupancy_calc_on_market_rooms"]
    ).round(4)
    result["rf_available"] = result["rf_rooms_sold"].notna().astype(int)
    result["rf_rooms_sold_matches_block"] = (
        result["rf_rooms_sold"].notna() & (result["rf_rooms_sold"] == result[TARGET_COLUMN])
    ).astype(int)
    result["rf_revenue_matches_block"] = (
        result["rf_room_revenue_net"].notna()
        & np.isclose(result["rf_room_revenue_net"], result["block_room_revenue_net"], atol=0.01)
    ).astype(int)
    result["rf_reported_occ_minus_block_reported_occ"] = (
        result["rf_occupancy_rate_reported"] - result["block_occupancy_rate_reported"]
    ).round(4)
    return result


def build_modeling_table() -> tuple[pd.DataFrame, dict]:
    block_daily = read_daily_csv(BLOCK_DAILY_INPUT)
    reservation_daily = read_daily_csv(RESERVATION_FORECAST_INPUT)
    guest_daily = read_guest_daily_features()

    block_spine = build_block_spine(block_daily)
    reservation_features = build_reservation_features(reservation_daily)
    modeling = block_spine.merge(reservation_features, on="business_date", how="left", validate="1:1")
    if guest_daily is not None:
        modeling = modeling.merge(guest_daily, on="business_date", how="left", validate="1:1")
        modeling["guest_source_available"] = modeling["guest_source_available"].fillna(0).astype(int)

    modeling = add_date_features(modeling)
    modeling = add_history_features(modeling)
    modeling = add_definition_checks(modeling)

    modeling = modeling.sort_values("business_date").reset_index(drop=True)

    summary = {
        "output_file": str(MODELING_OUTPUT.relative_to(REPO_ROOT)),
        "source_files": [
            str(BLOCK_DAILY_INPUT.relative_to(REPO_ROOT)),
            str(RESERVATION_FORECAST_INPUT.relative_to(REPO_ROOT)),
            *([str(GUEST_DAILY_INPUT.relative_to(REPO_ROOT))] if guest_daily is not None else []),
        ],
        "row_count": int(len(modeling)),
        "column_count": int(len(modeling.columns)),
        "date_coverage": {
            "start": modeling["business_date"].min().date().isoformat(),
            "end": modeling["business_date"].max().date().isoformat(),
            "missing_business_dates": missing_daily_dates(modeling["business_date"]),
            "duplicate_business_dates": int(modeling["business_date"].duplicated().sum()),
        },
        "target": TARGET_COLUMN,
        "reservation_forecast_join": {
            "rows_with_reservation_forecast": int(modeling["rf_available"].sum()),
            "rows_without_reservation_forecast": int((modeling["rf_available"] == 0).sum()),
            "reservation_forecast_date_range": {
                "start": reservation_daily["business_date"].min().date().isoformat(),
                "end": reservation_daily["business_date"].max().date().isoformat(),
            },
            "rooms_sold_match_count": int(modeling["rf_rooms_sold_matches_block"].sum()),
            "revenue_match_count": int(modeling["rf_revenue_matches_block"].sum()),
        },
        "guest_daily_join": {
            "guest_daily_file_present": guest_daily is not None,
            "rows_with_guest_source_available": int(modeling.get("guest_source_available", pd.Series(dtype=int)).sum())
            if guest_daily is not None
            else 0,
            "guest_daily_date_range": {
                "start": guest_daily["business_date"].min().date().isoformat(),
                "end": guest_daily["business_date"].max().date().isoformat(),
            }
            if guest_daily is not None
            else None,
            "guest_columns_joined": [
                column for column in modeling.columns if column.startswith("guest_")
            ]
            if guest_daily is not None
            else [],
        },
        "feature_groups": {
            "date_features": [column for column in modeling.columns if column.startswith("date_")],
            "lag_days": LAG_DAYS,
            "rolling_windows_days": ROLLING_WINDOWS,
            "history_base_columns": LAG_BASE_COLUMNS,
            "occupancy_definition_columns": [
                "block_occupancy_rate_reported",
                "rf_occupancy_rate_reported",
                "block_occupancy_calc_on_total_rooms",
                "block_occupancy_calc_on_market_rooms",
                "block_reported_occ_minus_total_room_calc",
                "block_reported_occ_minus_on_market_calc",
                "rf_reported_occ_minus_block_reported_occ",
            ],
        },
        "data_quality_flags": {
            "block_rows_sold_gt_total_rooms": int(
                (modeling[TARGET_COLUMN] > modeling["property_total_rooms"]).sum()
            ),
            "block_reported_occupancy_gt_1": int((modeling["block_occupancy_rate_reported"] > 1).sum()),
            "block_negative_net_revenue_rows": int((modeling["block_room_revenue_net"] < 0).sum()),
            "block_zero_rooms_sold_rows": int((modeling[TARGET_COLUMN] == 0).sum()),
        },
    }
    return modeling, summary


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    modeling, summary = build_modeling_table()
    modeling.to_csv(MODELING_OUTPUT, index=False, date_format="%Y-%m-%d")
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {MODELING_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {SUMMARY_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Rows: {summary['row_count']:,}")
    print(f"Columns: {summary['column_count']:,}")
    print(
        "Coverage: "
        f"{summary['date_coverage']['start']} through {summary['date_coverage']['end']}"
    )


if __name__ == "__main__":
    main()
