from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover - handled at runtime.
    XGBRegressor = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.train_baselines import (  # noqa: E402
    DATE_COLUMN,
    MODELING_INPUT,
    TARGET_COLUMN,
    chronological_split,
    select_feature_columns,
)
from src.pricing.build_pricing_recommendations import build_recommendations  # noqa: E402


REPORTS_DIR = REPO_ROOT / "reports"
AUDIT_REPORTS_DIR = REPORTS_DIR / "audit"
BASELINE_REPORTS_DIR = REPORTS_DIR / "baselines"
PRICING_REPORTS_DIR = REPORTS_DIR / "pricing"
FIGURES_DIR = REPORTS_DIR / "figures"
FLAGS_INPUT = AUDIT_REPORTS_DIR / "data_quality_flags.csv"

FEATURE_IMPORTANCE_OUTPUT = BASELINE_REPORTS_DIR / "xgboost_feature_importance.csv"
FEATURE_IMPORTANCE_FIGURE = FIGURES_DIR / "xgboost_feature_importance.png"
PIPELINE_ARCHITECTURE_FIGURE = FIGURES_DIR / "final_pipeline_architecture.png"
HIGH_DEMAND_EXAMPLES_OUTPUT = PRICING_REPORTS_DIR / "pricing_high_demand_examples.csv"
BUSINESS_METRICS_OUTPUT = PRICING_REPORTS_DIR / "pricing_business_metric_comparison.csv"


def load_primary_modeling_table() -> pd.DataFrame:
    modeling = pd.read_csv(MODELING_INPUT, parse_dates=[DATE_COLUMN])
    flags = pd.read_csv(FLAGS_INPUT, parse_dates=[DATE_COLUMN])
    flagged_dates = set(flags[DATE_COLUMN])
    return modeling.loc[~modeling[DATE_COLUMN].isin(flagged_dates)].sort_values(DATE_COLUMN).reset_index(drop=True)


def build_feature_importance() -> pd.DataFrame:
    if XGBRegressor is None:
        raise RuntimeError("xgboost is required to build XGBoost feature importance.")

    modeling = load_primary_modeling_table()
    feature_columns = select_feature_columns(modeling)
    train, _, _ = chronological_split(modeling)
    train = train.dropna(subset=[TARGET_COLUMN]).copy()

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                XGBRegressor(
                    n_estimators=500,
                    max_depth=3,
                    learning_rate=0.03,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    objective="reg:squarederror",
                    random_state=561,
                ),
            ),
        ]
    )
    model.fit(train[feature_columns], train[TARGET_COLUMN])
    fitted = model.named_steps["model"]
    importance = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance": fitted.feature_importances_,
        }
    ).sort_values("importance", ascending=False)
    importance["rank"] = range(1, len(importance) + 1)
    importance.to_csv(FEATURE_IMPORTANCE_OUTPUT, index=False)

    top = importance.head(25).copy()
    sns.set_theme(style="whitegrid")
    fig, axis = plt.subplots(figsize=(10, 8))
    sns.barplot(data=top, x="importance", y="feature", ax=axis, color="#2563eb")
    axis.set_title("Top XGBoost Feature Importances")
    axis.set_xlabel("Feature importance")
    axis.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FEATURE_IMPORTANCE_FIGURE, dpi=180)
    plt.close(fig)
    return importance


def draw_pipeline_architecture() -> None:
    fig, axis = plt.subplots(figsize=(14, 7))
    axis.axis("off")

    boxes = [
        ("Raw reports\nGuestNameList, Block RoomSales,\nReservationForecast", 0.04, 0.62, 0.18, 0.22),
        ("Cleaning + dedupe\nstandardize dates, rates,\nstatus, source audits", 0.29, 0.62, 0.18, 0.22),
        ("Daily modeling table\n1,096 dates, lag/rolling,\ncalendar + guest features", 0.54, 0.62, 0.18, 0.22),
        ("Forecast models\nbaselines, XGBoost, RF,\nMLP, LSTM, GRU, Transformer", 0.79, 0.62, 0.18, 0.22),
        ("Sensitivity + model choice\nexclude flagged anomalies,\nselect XGBoost by MAE", 0.29, 0.20, 0.18, 0.22),
        ("Pricing layer\nforecast occupancy,\nbounded ADR rules", 0.54, 0.20, 0.18, 0.22),
        ("Business outputs\nrevenue, ADR, RevPAR,\nscenario examples", 0.79, 0.20, 0.18, 0.22),
    ]

    for label, x, y, width, height in boxes:
        axis.add_patch(
            plt.Rectangle(
                (x, y),
                width,
                height,
                facecolor="#eff6ff",
                edgecolor="#1f2937",
                linewidth=1.4,
            )
        )
        axis.text(x + width / 2, y + height / 2, label, ha="center", va="center", fontsize=10)

    arrows = [
        ((0.22, 0.73), (0.29, 0.73)),
        ((0.47, 0.73), (0.54, 0.73)),
        ((0.72, 0.73), (0.79, 0.73)),
        ((0.88, 0.62), (0.43, 0.42)),
        ((0.47, 0.31), (0.54, 0.31)),
        ((0.72, 0.31), (0.79, 0.31)),
    ]
    for start, end in arrows:
        axis.annotate(
            "",
            xy=end,
            xytext=start,
            arrowprops={"arrowstyle": "->", "linewidth": 1.6, "color": "#1f2937"},
        )

    axis.set_title("Hotel Demand Forecasting and Pricing MVP Pipeline", fontsize=16, weight="bold")
    fig.tight_layout()
    fig.savefig(PIPELINE_ARCHITECTURE_FIGURE, dpi=180)
    plt.close(fig)


def scenario_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for scenario in ("aggressive", "conservative"):
        recommendations, _ = build_recommendations(scenario)
        frames[scenario] = recommendations
    return frames


def build_high_demand_examples(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    aggressive = frames["aggressive"].copy()
    conservative = frames["conservative"][
        [DATE_COLUMN, "recommended_adr", "simulated_revenue_at_actual_rooms"]
    ].rename(
        columns={
            "recommended_adr": "conservative_recommended_adr",
            "simulated_revenue_at_actual_rooms": "conservative_simulated_revenue_at_actual_rooms",
        }
    )
    examples = aggressive.merge(conservative, on=DATE_COLUMN, how="left", validate="1:1")
    examples["day_of_week"] = examples[DATE_COLUMN].dt.day_name()
    examples["is_weekend"] = examples[DATE_COLUMN].dt.dayofweek.isin([5, 6])
    examples = examples.loc[
        examples["is_flagged_quality_row"].eq(0)
        & examples["is_weekend"]
        & examples["demand_band"].isin(["high", "very_high"])
    ].copy()
    examples["forecast_rooms_sold_rounded"] = examples["forecast_rooms_sold"].round(1)
    examples["forecast_occupancy_pct"] = (examples["forecast_occupancy_rate"] * 100).round(1)
    examples["actual_occupancy_pct"] = (
        examples[TARGET_COLUMN] / examples["property_total_rooms"] * 100
    ).round(1)
    examples["conservative_simulated_revenue_delta_at_actual_rooms"] = (
        examples["conservative_simulated_revenue_at_actual_rooms"]
        - examples["historical_room_revenue_net"]
    ).round(2)

    output_columns = [
        DATE_COLUMN,
        "day_of_week",
        "demand_band",
        TARGET_COLUMN,
        "forecast_rooms_sold_rounded",
        "actual_occupancy_pct",
        "forecast_occupancy_pct",
        "historical_adr_net",
        "recommended_adr",
        "conservative_recommended_adr",
        "historical_room_revenue_net",
        "simulated_revenue_delta_at_actual_rooms",
        "conservative_simulated_revenue_delta_at_actual_rooms",
    ]
    examples = examples.sort_values(
        ["forecast_occupancy_rate", "simulated_revenue_delta_at_actual_rooms"],
        ascending=[False, False],
    ).head(12)
    examples = examples[output_columns]
    examples.to_csv(HIGH_DEMAND_EXAMPLES_OUTPUT, index=False, date_format="%Y-%m-%d")
    return examples


def metric_summary_for_frame(frame: pd.DataFrame, scenario: str, row_scope: str) -> dict:
    available_room_nights = float(frame["property_total_rooms"].sum())
    actual_rooms = float(frame[TARGET_COLUMN].sum())
    forecast_rooms = float(frame["forecast_rooms_sold"].sum())
    historical_revenue = float(frame["historical_room_revenue_net"].sum())
    simulated_revenue = float(frame["simulated_revenue_at_actual_rooms"].sum())
    return {
        "scenario": scenario,
        "row_scope": row_scope,
        "rows": int(len(frame)),
        "available_room_nights": round(available_room_nights, 2),
        "actual_rooms_sold": round(actual_rooms, 2),
        "forecast_rooms_sold": round(forecast_rooms, 2),
        "actual_occupancy_rate": round(actual_rooms / available_room_nights, 6),
        "forecast_occupancy_rate": round(forecast_rooms / available_room_nights, 6),
        "static_simulated_occupancy_delta": 0.0,
        "historical_revenue_net": round(historical_revenue, 2),
        "simulated_revenue_at_actual_rooms": round(simulated_revenue, 2),
        "simulated_revenue_delta": round(simulated_revenue - historical_revenue, 2),
        "historical_revpar_net": round(historical_revenue / available_room_nights, 4),
        "simulated_revpar_at_actual_rooms": round(simulated_revenue / available_room_nights, 4),
        "simulated_revpar_delta": round((simulated_revenue - historical_revenue) / available_room_nights, 4),
        "historical_adr_net_total": round(historical_revenue / actual_rooms, 4) if actual_rooms else None,
        "simulated_adr_at_actual_rooms": round(simulated_revenue / actual_rooms, 4) if actual_rooms else None,
    }


def build_business_metric_comparison(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for scenario, frame in frames.items():
        rows.append(metric_summary_for_frame(frame, scenario, "all_test_days"))
        rows.append(
            metric_summary_for_frame(
                frame.loc[frame["is_flagged_quality_row"].eq(0)].copy(),
                scenario,
                "unflagged_test_days",
            )
        )
    metrics = pd.DataFrame(rows)
    metrics.to_csv(BUSINESS_METRICS_OUTPUT, index=False)
    return metrics


def main() -> None:
    BASELINE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PRICING_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    build_feature_importance()
    draw_pipeline_architecture()
    frames = scenario_frames()
    build_high_demand_examples(frames)
    build_business_metric_comparison(frames)

    print(f"Wrote {FEATURE_IMPORTANCE_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {FEATURE_IMPORTANCE_FIGURE.relative_to(REPO_ROOT)}")
    print(f"Wrote {PIPELINE_ARCHITECTURE_FIGURE.relative_to(REPO_ROOT)}")
    print(f"Wrote {HIGH_DEMAND_EXAMPLES_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {BUSINESS_METRICS_OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
