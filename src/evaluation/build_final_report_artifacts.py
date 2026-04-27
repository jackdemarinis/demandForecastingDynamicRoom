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
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    fig = plt.figure(figsize=(14, 9))
    axis = fig.add_axes((0, 0, 1, 1))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    palette = {
        "data":    {"band": "#eff6ff", "fill": "#dbeafe", "edge": "#1d4ed8", "label": "Data"},
        "model":   {"band": "#f5f3ff", "fill": "#ede9fe", "edge": "#6d28d9", "label": "Modeling"},
        "pricing": {"band": "#ecfdf5", "fill": "#d1fae5", "edge": "#047857", "label": "Pricing & Outputs"},
    }
    highlight = {"fill": "#fef3c7", "edge": "#b45309"}
    text_dark = "#0f172a"
    text_body = "#1f2937"
    arrow_color = "#475569"

    rows = {
        "data":    {"y": 0.66, "h": 0.18, "band_y": 0.625, "band_h": 0.225},
        "model":   {"y": 0.39, "h": 0.18, "band_y": 0.355, "band_h": 0.225},
        "pricing": {"y": 0.12, "h": 0.18, "band_y": 0.085, "band_h": 0.225},
    }

    layers = [
        (
            "data",
            [
                ("Raw Reports",     "GuestNameList\nBlock RoomSales\nReservationForecast"),
                ("Cleaning & Audit","Dedupe + standardize\ndates, rates, status\nflag 14 anomaly rows"),
                ("Modeling Table",  "1,096 daily rows\n2023-01 → 2025-12\nlag · rolling · calendar"),
            ],
        ),
        (
            "model",
            [
                ("Forecast Model Sweep", "Baselines · Ridge\nRandom Forest · XGBoost\nMLP · LSTM · GRU · Transformer"),
                ("Sensitivity & Selection", "3 data-quality conventions\nchronological val/test\n→ XGBoost (MAE 7.443)", True),
            ],
        ),
        (
            "pricing",
            [
                ("Pricing Layer", "Forecast → occupancy band\nreference ADR + bounds\naggressive · conservative"),
                ("Business Outputs", "Revenue · ADR · RevPAR\nscenario comparison\nhigh-demand examples"),
            ],
        ),
    ]

    band_x = 0.10
    band_w = 0.86
    box_positions = {}

    for stage_key, items in layers:
        meta = rows[stage_key]
        y, h = meta["y"], meta["h"]
        band_y, band_h = meta["band_y"], meta["band_h"]
        band_color = palette[stage_key]["band"]
        edge_color = palette[stage_key]["edge"]

        axis.add_patch(FancyBboxPatch(
            (band_x, band_y), band_w, band_h,
            boxstyle="round,pad=0.005,rounding_size=0.018",
            facecolor=band_color, edgecolor=edge_color,
            linewidth=1.0, alpha=0.95, zorder=0,
        ))
        axis.text(
            band_x - 0.012, band_y + band_h / 2,
            palette[stage_key]["label"].upper(),
            ha="center", va="center",
            fontsize=11, weight="bold", color=edge_color, rotation=90, zorder=1,
        )

        n = len(items)
        usable_w = band_w - 0.04
        gap = 0.04
        box_w = (usable_w - (n - 1) * gap) / n
        start_x = band_x + 0.02

        for i, item in enumerate(items):
            title = item[0]
            body = item[1]
            is_highlight = len(item) > 2 and item[2]

            x = start_x + i * (box_w + gap)
            fill = highlight["fill"] if is_highlight else palette[stage_key]["fill"]
            box_edge = highlight["edge"] if is_highlight else palette[stage_key]["edge"]

            axis.add_patch(FancyBboxPatch(
                (x, y), box_w, h,
                boxstyle="round,pad=0.004,rounding_size=0.014",
                facecolor=fill, edgecolor=box_edge, linewidth=1.8, zorder=2,
            ))
            axis.text(
                x + box_w / 2, y + h - 0.022, title,
                ha="center", va="top",
                fontsize=12, weight="bold", color=box_edge, zorder=3,
            )
            axis.plot(
                [x + 0.012, x + box_w - 0.012],
                [y + h - 0.052, y + h - 0.052],
                color=box_edge, linewidth=0.9, alpha=0.5, zorder=3,
            )
            axis.text(
                x + box_w / 2, y + h - 0.062, body,
                ha="center", va="top",
                fontsize=10, color=text_body, zorder=3,
            )

            box_positions[(stage_key, i)] = {
                "x": x, "y": y, "w": box_w, "h": h,
                "left":  (x, y + h / 2),
                "right": (x + box_w, y + h / 2),
                "top":   (x + box_w / 2, y + h),
                "bottom":(x + box_w / 2, y),
            }

    def horizontal_arrow(start_box, end_box, color=arrow_color):
        sx, sy = box_positions[start_box]["right"]
        ex, ey = box_positions[end_box]["left"]
        sx += 0.004
        ex -= 0.004
        axis.add_patch(FancyArrowPatch(
            (sx, sy), (ex, ey),
            arrowstyle="-|>", mutation_scale=18,
            linewidth=1.8, color=color, zorder=4,
        ))

    def vertical_band_arrow(upper_band_bottom, lower_band_top, label=None, color=arrow_color):
        sx = ex = 0.5
        sy = upper_band_bottom - 0.004
        ey = lower_band_top + 0.004
        axis.add_patch(FancyArrowPatch(
            (sx, sy), (ex, ey),
            arrowstyle="-|>", mutation_scale=22,
            linewidth=2.0, color=color, zorder=4,
        ))
        if label is not None:
            axis.text(
                sx + 0.012, (sy + ey) / 2, label,
                ha="left", va="center",
                fontsize=10, style="italic", color=color,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 3.0, "alpha": 0.95},
                zorder=5,
            )

    horizontal_arrow(("data", 0), ("data", 1))
    horizontal_arrow(("data", 1), ("data", 2))
    vertical_band_arrow(
        upper_band_bottom=rows["data"]["band_y"],
        lower_band_top=rows["model"]["band_y"] + rows["model"]["band_h"],
        label="leakage-safe features",
    )
    horizontal_arrow(("model", 0), ("model", 1))
    vertical_band_arrow(
        upper_band_bottom=rows["model"]["band_y"],
        lower_band_top=rows["pricing"]["band_y"] + rows["pricing"]["band_h"],
        label="XGBoost forecast",
    )
    horizontal_arrow(("pricing", 0), ("pricing", 1))

    axis.text(
        0.5, 0.965,
        "Hotel Demand Forecasting & Pricing MVP — Pipeline Architecture",
        ha="center", va="center",
        fontsize=16, weight="bold", color=text_dark,
    )
    axis.text(
        0.5, 0.93,
        "Three-stage flow: operational data → demand forecasting → bounded pricing recommendations",
        ha="center", va="center",
        fontsize=10.5, style="italic", color="#475569",
    )

    fig.savefig(PIPELINE_ARCHITECTURE_FIGURE, dpi=220, bbox_inches="tight")
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
