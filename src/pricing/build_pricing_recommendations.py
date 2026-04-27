from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "processed_data"
REPORTS_DIR = REPO_ROOT / "reports"
AUDIT_REPORTS_DIR = REPORTS_DIR / "audit"
BASELINE_REPORTS_DIR = REPORTS_DIR / "baselines"
PRICING_REPORTS_DIR = REPORTS_DIR / "pricing"
FIGURES_DIR = REPORTS_DIR / "figures"

MODELING_INPUT = PROCESSED_DIR / "modeling_daily.csv"
BASELINE_PREDICTIONS_INPUT = BASELINE_REPORTS_DIR / "baseline_predictions.csv"
SENSITIVITY_SUMMARY_INPUT = BASELINE_REPORTS_DIR / "baseline_sensitivity_summary.json"
FLAGS_INPUT = AUDIT_REPORTS_DIR / "data_quality_flags.csv"

RECOMMENDATIONS_OUTPUT = PRICING_REPORTS_DIR / "pricing_recommendations.csv"
SUMMARY_OUTPUT = PRICING_REPORTS_DIR / "pricing_recommendations_summary.json"
SCENARIO_COMPARISON_OUTPUT = PRICING_REPORTS_DIR / "pricing_scenario_comparison.csv"
ADR_FIGURE_OUTPUT = FIGURES_DIR / "pricing_recommended_vs_historical_adr.png"
REVENUE_FIGURE_OUTPUT = FIGURES_DIR / "pricing_monthly_revenue_simulation.png"
SCENARIO_COMPARISON_FIGURE_OUTPUT = FIGURES_DIR / "pricing_scenario_comparison.png"

DATE_COLUMN = "business_date"
TARGET_COLUMN = "target_rooms_sold"

MIN_ADR = 75.0
MAX_ADR = 350.0
MAX_DAILY_CHANGE = 0.20

ADJUSTMENT_SCENARIOS = {
    "aggressive": {
        "very_high": 0.12,
        "high": 0.08,
        "moderately_high": 0.04,
        "neutral": 0.0,
        "moderately_low": -0.04,
        "low": -0.08,
        "very_low": -0.12,
    },
    "conservative": {
        "very_high": 0.06,
        "high": 0.04,
        "moderately_high": 0.02,
        "neutral": 0.0,
        "moderately_low": -0.02,
        "low": -0.04,
        "very_low": -0.06,
    },
}


def selected_model() -> tuple[str, dict]:
    summary = json.loads(SENSITIVITY_SUMMARY_INPUT.read_text(encoding="utf-8"))
    source = summary["preferred_pricing_model_source"]
    return source["model"], source


def demand_adjustment(forecast_occupancy: float, scenario: str) -> float:
    return ADJUSTMENT_SCENARIOS[scenario][demand_band(forecast_occupancy)]


def demand_band(forecast_occupancy: float) -> str:
    if forecast_occupancy >= 0.90:
        return "very_high"
    if forecast_occupancy >= 0.80:
        return "high"
    if forecast_occupancy >= 0.70:
        return "moderately_high"
    if forecast_occupancy <= 0.35:
        return "very_low"
    if forecast_occupancy <= 0.50:
        return "low"
    if forecast_occupancy <= 0.60:
        return "moderately_low"
    return "neutral"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    modeling = pd.read_csv(MODELING_INPUT, parse_dates=[DATE_COLUMN])
    predictions = pd.read_csv(BASELINE_PREDICTIONS_INPUT, parse_dates=[DATE_COLUMN])
    flags = pd.read_csv(FLAGS_INPUT, parse_dates=[DATE_COLUMN])
    return modeling, predictions, flags


def apply_pricing_rule(
    forecast: pd.DataFrame,
    scenario: str = "aggressive",
    model_name: str = "xgboost",
) -> pd.DataFrame:
    """Apply the bounded ADR pricing rule to an arbitrary forecast frame.

    ``forecast`` must contain ``business_date`` and ``forecast_rooms_sold``.
    All same-day context (historical ADR, rolling/lag fallbacks, flags) is
    pulled from the modeling table and audit flags on disk.
    """
    if scenario not in ADJUSTMENT_SCENARIOS:
        raise ValueError(f"Unknown pricing scenario: {scenario}")

    forecast = forecast[[DATE_COLUMN, "forecast_rooms_sold"]].copy()
    forecast[DATE_COLUMN] = pd.to_datetime(forecast[DATE_COLUMN])

    modeling, _predictions, flags = load_inputs()
    recommendations = forecast.merge(modeling, on=DATE_COLUMN, how="left", validate="1:1")
    flag_notes = (
        flags.groupby(DATE_COLUMN)
        .agg(
            data_quality_flag_type=("flag_type", lambda values: "|".join(sorted(set(values)))),
            data_quality_review_note=("review_note", lambda values: " | ".join(sorted(set(values)))),
        )
        .reset_index()
    )
    recommendations = recommendations.merge(flag_notes, on=DATE_COLUMN, how="left")
    recommendations["is_flagged_quality_row"] = recommendations["data_quality_flag_type"].notna().astype(int)

    property_total_rooms = modeling["property_total_rooms"].dropna().mode()
    property_total_rooms = float(property_total_rooms.iloc[0]) if len(property_total_rooms) else 60.0
    recommendations["property_total_rooms"] = recommendations["property_total_rooms"].fillna(property_total_rooms)

    historical_nonzero_adr = modeling.loc[modeling["block_adr_net"] > 0, "block_adr_net"]
    median_nonzero_adr = historical_nonzero_adr.median()
    recent_nonzero_adr = historical_nonzero_adr.tail(28).median()
    if pd.isna(recent_nonzero_adr):
        recent_nonzero_adr = median_nonzero_adr

    reference_adr = recommendations["block_adr_net"].where(recommendations["block_adr_net"] > 0)
    reference_adr = reference_adr.fillna(recommendations["block_adr_net_rolling_28d_mean"])
    reference_adr = reference_adr.fillna(recommendations["block_adr_net_rolling_14d_mean"])
    reference_adr = reference_adr.fillna(recommendations["block_adr_net_lag_7d"])
    reference_adr = reference_adr.fillna(recommendations["block_adr_net_lag_1d"])
    reference_adr = reference_adr.fillna(recent_nonzero_adr)
    reference_adr = reference_adr.where(reference_adr > 0, median_nonzero_adr)

    recommendations["pricing_model"] = model_name
    recommendations["pricing_reference_adr"] = reference_adr.round(2)
    recommendations["forecast_occupancy_rate"] = (
        recommendations["forecast_rooms_sold"] / recommendations["property_total_rooms"]
    ).clip(lower=0, upper=1.25)
    recommendations["demand_band"] = recommendations["forecast_occupancy_rate"].map(demand_band)
    recommendations["pricing_adjustment_rate"] = recommendations["forecast_occupancy_rate"].map(
        lambda value: demand_adjustment(value, scenario)
    )

    unbounded = recommendations["pricing_reference_adr"] * (1 + recommendations["pricing_adjustment_rate"])
    lower_bound = recommendations["pricing_reference_adr"] * (1 - MAX_DAILY_CHANGE)
    upper_bound = recommendations["pricing_reference_adr"] * (1 + MAX_DAILY_CHANGE)
    recommendations["recommended_adr"] = unbounded.clip(lower=lower_bound, upper=upper_bound)
    recommendations["recommended_adr"] = recommendations["recommended_adr"].clip(lower=MIN_ADR, upper=MAX_ADR).round(2)

    recommendations["historical_adr_net"] = recommendations["block_adr_net"]
    recommendations["historical_room_revenue_net"] = recommendations["block_room_revenue_net"]
    recommendations["simulated_revenue_at_actual_rooms"] = (
        recommendations["recommended_adr"] * recommendations[TARGET_COLUMN]
    ).round(2)
    recommendations["forecast_revenue_at_recommended_adr"] = (
        recommendations["recommended_adr"] * recommendations["forecast_rooms_sold"]
    ).round(2)
    recommendations["recommended_vs_reference_adr_delta"] = (
        recommendations["recommended_adr"] - recommendations["pricing_reference_adr"]
    ).round(2)
    recommendations["recommended_vs_historical_adr_delta"] = (
        recommendations["recommended_adr"] - recommendations["historical_adr_net"]
    ).round(2)
    recommendations["simulated_revenue_delta_at_actual_rooms"] = (
        recommendations["simulated_revenue_at_actual_rooms"] - recommendations["historical_room_revenue_net"]
    ).round(2)

    output_columns = [
        DATE_COLUMN,
        "pricing_model",
        "is_flagged_quality_row",
        "data_quality_flag_type",
        TARGET_COLUMN,
        "property_total_rooms",
        "forecast_rooms_sold",
        "forecast_occupancy_rate",
        "demand_band",
        "pricing_reference_adr",
        "pricing_adjustment_rate",
        "recommended_adr",
        "historical_adr_net",
        "recommended_vs_reference_adr_delta",
        "recommended_vs_historical_adr_delta",
        "historical_room_revenue_net",
        "simulated_revenue_at_actual_rooms",
        "forecast_revenue_at_recommended_adr",
        "simulated_revenue_delta_at_actual_rooms",
        "data_quality_review_note",
    ]
    return recommendations[output_columns].sort_values(DATE_COLUMN).reset_index(drop=True)


def build_recommendations(scenario: str = "aggressive") -> tuple[pd.DataFrame, dict]:
    if scenario not in ADJUSTMENT_SCENARIOS:
        raise ValueError(f"Unknown pricing scenario: {scenario}")

    model_name, model_source = selected_model()
    _modeling, predictions, _flags = load_inputs()
    forecast = predictions.loc[
        predictions["split"].eq("test") & predictions["model"].eq(model_name),
        [DATE_COLUMN, "predicted"],
    ].rename(columns={"predicted": "forecast_rooms_sold"})

    recommendations = apply_pricing_rule(forecast, scenario=scenario, model_name=model_name)
    summary = build_summary(recommendations, model_source, scenario)
    return recommendations, summary


def simulation_summary(frame: pd.DataFrame) -> dict:
    historical_revenue = float(frame["historical_room_revenue_net"].sum())
    simulated_revenue = float(frame["simulated_revenue_at_actual_rooms"].sum())
    delta = simulated_revenue - historical_revenue
    nonzero_actual = frame.loc[frame[TARGET_COLUMN] > 0]
    return {
        "rows": int(len(frame)),
        "historical_revenue_net": round(historical_revenue, 2),
        "simulated_revenue_at_actual_rooms": round(simulated_revenue, 2),
        "simulated_revenue_delta": round(delta, 2),
        "simulated_revenue_delta_pct": round(delta / historical_revenue, 6) if historical_revenue else None,
        "average_historical_adr_nonzero_actual": round(float(nonzero_actual["historical_adr_net"].mean()), 4)
        if len(nonzero_actual)
        else None,
        "average_recommended_adr_nonzero_actual": round(float(nonzero_actual["recommended_adr"].mean()), 4)
        if len(nonzero_actual)
        else None,
        "average_absolute_adr_change_vs_reference": round(
            float(frame["recommended_vs_reference_adr_delta"].abs().mean()), 4
        ),
    }


def build_summary(recommendations: pd.DataFrame, model_source: dict, scenario: str) -> dict:
    unflagged = recommendations.loc[recommendations["is_flagged_quality_row"].eq(0)]
    return {
        "output_file": str(RECOMMENDATIONS_OUTPUT.relative_to(REPO_ROOT)),
        "scenario": scenario,
        "pricing_model_source": model_source,
        "rule": {
            "reference_adr": "Historical same-day net ADR, then 28-day rolling net ADR, 14-day rolling net ADR, 7-day lag, 1-day lag, then median nonzero ADR fallback.",
            "forecast_signal": "forecast_rooms_sold / property_total_rooms",
            "adjustments": scenario_adjustment_description(scenario),
            "bounds": {
                "min_adr": MIN_ADR,
                "max_adr": MAX_ADR,
                "max_daily_change_from_reference": MAX_DAILY_CHANGE,
            },
        },
        "simulation_caveat": (
            "This is a static academic counterfactual. It starts from historical same-day ADR, applies "
            "bounded demand-based adjustments, then applies recommended ADR to actual realized rooms. "
            "It does not estimate demand response to price changes."
        ),
        "all_test_days": simulation_summary(recommendations),
        "unflagged_test_days": simulation_summary(unflagged),
        "flagged_rows_in_pricing_period": int(recommendations["is_flagged_quality_row"].sum()),
        "demand_band_counts": recommendations["demand_band"].value_counts().to_dict(),
    }


def scenario_adjustment_description(scenario: str) -> dict:
    adjustments = ADJUSTMENT_SCENARIOS[scenario]
    return {
        "very_high_occupancy_gte_0.90": adjustments["very_high"],
        "high_occupancy_gte_0.80": adjustments["high"],
        "moderately_high_occupancy_gte_0.70": adjustments["moderately_high"],
        "moderately_low_occupancy_lte_0.60": adjustments["moderately_low"],
        "low_occupancy_lte_0.50": adjustments["low"],
        "very_low_occupancy_lte_0.35": adjustments["very_low"],
    }


def build_scenario_comparison(summaries: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for scenario, summary in summaries.items():
        for row_scope in ("all_test_days", "unflagged_test_days"):
            metrics = summary[row_scope]
            rows.append(
                {
                    "scenario": scenario,
                    "row_scope": row_scope,
                    "rows": metrics["rows"],
                    "historical_revenue_net": metrics["historical_revenue_net"],
                    "simulated_revenue_at_actual_rooms": metrics["simulated_revenue_at_actual_rooms"],
                    "simulated_revenue_delta": metrics["simulated_revenue_delta"],
                    "simulated_revenue_delta_pct": metrics["simulated_revenue_delta_pct"],
                    "average_historical_adr_nonzero_actual": metrics["average_historical_adr_nonzero_actual"],
                    "average_recommended_adr_nonzero_actual": metrics["average_recommended_adr_nonzero_actual"],
                    "average_absolute_adr_change_vs_reference": metrics["average_absolute_adr_change_vs_reference"],
                }
            )
    return pd.DataFrame(rows)


def plot_scenario_comparison(comparison: pd.DataFrame) -> None:
    plot_frame = comparison.loc[comparison["row_scope"].eq("unflagged_test_days")].copy()
    plot_frame["simulated_revenue_delta_pct_label"] = plot_frame["simulated_revenue_delta_pct"] * 100

    sns.set_theme(style="whitegrid")
    fig, axis = plt.subplots(figsize=(9, 5))
    sns.barplot(
        data=plot_frame,
        x="scenario",
        y="simulated_revenue_delta",
        ax=axis,
        hue="scenario",
        palette={"aggressive": "#2563eb", "conservative": "#059669"},
        legend=False,
    )
    axis.axhline(0, color="#111827", linewidth=1)
    axis.set_title("Static Revenue Lift by Pricing Scenario, Unflagged 2025 Test Days")
    axis.set_xlabel("")
    axis.set_ylabel("Simulated revenue delta at actual rooms")
    for container in axis.containers:
        axis.bar_label(container, fmt="$%.0f", padding=3)
    fig.tight_layout()
    fig.savefig(SCENARIO_COMPARISON_FIGURE_OUTPUT, dpi=180)
    plt.close(fig)


def plot_recommendations(recommendations: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid")
    fig, axis = plt.subplots(figsize=(14, 5))
    axis.plot(recommendations[DATE_COLUMN], recommendations["historical_adr_net"], label="Historical ADR", color="#1f2937")
    axis.plot(recommendations[DATE_COLUMN], recommendations["recommended_adr"], label="Recommended ADR", color="#2563eb")
    axis.set_title("Recommended ADR vs Historical ADR, 2025 Test Period")
    axis.set_xlabel("Business date")
    axis.set_ylabel("ADR")
    axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(ADR_FIGURE_OUTPUT, dpi=180)
    plt.close(fig)

    monthly = recommendations.copy()
    monthly["month"] = monthly[DATE_COLUMN].dt.to_period("M").dt.to_timestamp()
    monthly = (
        monthly.groupby("month")
        .agg(
            historical_room_revenue_net=("historical_room_revenue_net", "sum"),
            simulated_revenue_at_actual_rooms=("simulated_revenue_at_actual_rooms", "sum"),
        )
        .reset_index()
    )
    long = monthly.melt(
        id_vars="month",
        value_vars=["historical_room_revenue_net", "simulated_revenue_at_actual_rooms"],
        var_name="series",
        value_name="revenue",
    )
    fig, axis = plt.subplots(figsize=(14, 5))
    sns.barplot(data=long, x="month", y="revenue", hue="series", ax=axis)
    axis.set_title("Historical vs Simulated Monthly Room Revenue")
    axis.set_xlabel("Month")
    axis.set_ylabel("Room revenue")
    axis.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(REVENUE_FIGURE_OUTPUT, dpi=180)
    plt.close(fig)


def main() -> None:
    PRICING_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    recommendations, summary = build_recommendations("aggressive")
    _, conservative_summary = build_recommendations("conservative")
    scenario_comparison = build_scenario_comparison(
        {"aggressive": summary, "conservative": conservative_summary}
    )
    summary["scenario_comparison_file"] = str(SCENARIO_COMPARISON_OUTPUT.relative_to(REPO_ROOT))
    summary["scenario_comparison_figure"] = str(SCENARIO_COMPARISON_FIGURE_OUTPUT.relative_to(REPO_ROOT))
    summary["scenario_comparison"] = scenario_comparison.to_dict(orient="records")

    recommendations.to_csv(RECOMMENDATIONS_OUTPUT, index=False, date_format="%Y-%m-%d")
    scenario_comparison.to_csv(SCENARIO_COMPARISON_OUTPUT, index=False)
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot_recommendations(recommendations)
    plot_scenario_comparison(scenario_comparison)

    unflagged = summary["unflagged_test_days"]
    conservative_unflagged = conservative_summary["unflagged_test_days"]
    print(f"Wrote {RECOMMENDATIONS_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {SCENARIO_COMPARISON_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {SUMMARY_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {ADR_FIGURE_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {SCENARIO_COMPARISON_FIGURE_OUTPUT.relative_to(REPO_ROOT)}")
    print(
        "Aggressive unflagged simulated revenue delta: "
        f"{unflagged['simulated_revenue_delta']:.2f} "
        f"({unflagged['simulated_revenue_delta_pct']:.2%})"
    )
    print(
        "Conservative unflagged simulated revenue delta: "
        f"{conservative_unflagged['simulated_revenue_delta']:.2f} "
        f"({conservative_unflagged['simulated_revenue_delta_pct']:.2%})"
    )


if __name__ == "__main__":
    main()
