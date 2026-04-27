from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "processed_data"
REPORTS_DIR = REPO_ROOT / "reports"
BASELINE_REPORTS_DIR = REPORTS_DIR / "baselines"
DEEP_LEARNING_REPORTS_DIR = REPORTS_DIR / "deep_learning"
FINAL_REPORTS_DIR = REPORTS_DIR / "final"
PRICING_REPORTS_DIR = REPORTS_DIR / "pricing"

MODELING_SUMMARY_INPUT = PROCESSED_DIR / "modeling_daily_summary.json"
BASELINE_METRICS_INPUT = BASELINE_REPORTS_DIR / "baseline_metrics.csv"
SENSITIVITY_METRICS_INPUT = BASELINE_REPORTS_DIR / "baseline_sensitivity_metrics.csv"
DEEP_LEARNING_COMPARISON_INPUT = DEEP_LEARNING_REPORTS_DIR / "deep_learning_model_comparison.csv"
FEATURE_IMPORTANCE_INPUT = BASELINE_REPORTS_DIR / "xgboost_feature_importance.csv"
BUSINESS_METRICS_INPUT = PRICING_REPORTS_DIR / "pricing_business_metric_comparison.csv"
HIGH_DEMAND_EXAMPLES_INPUT = PRICING_REPORTS_DIR / "pricing_high_demand_examples.csv"
PRICING_SUMMARY_INPUT = PRICING_REPORTS_DIR / "pricing_recommendations_summary.json"
PROJECT_SUMMARY_OUTPUT = FINAL_REPORTS_DIR / "project_summary.md"

LEARNED_MODELS = {"ridge_regression", "random_forest", "xgboost"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_number(value: float | int | None, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.{digits}f}"


def fmt_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"${float(value):,.2f}"


def fmt_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2%}"


def markdown_metrics_table(metrics: pd.DataFrame, include_scenario: bool = False) -> str:
    headers = ["Scenario", "Model", "Rows", "MAE", "RMSE", "R2"] if include_scenario else ["Model", "Rows", "MAE", "RMSE", "R2"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in metrics.iterrows():
        values = []
        if include_scenario:
            values.append(str(row["scenario"]))
        values.extend(
            [
                str(row["model"]),
                f"{int(row['row_count']):,}",
                fmt_number(row["mae"]),
                fmt_number(row["rmse"]),
                fmt_number(row["r2"]),
            ]
        )
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def markdown_pricing_table(pricing_summary: dict) -> str:
    rows = pricing_summary.get("scenario_comparison", [])
    if not rows:
        rows = [
            {"scenario": pricing_summary.get("scenario", "aggressive"), "row_scope": scope, **pricing_summary[scope]}
            for scope in ("all_test_days", "unflagged_test_days")
        ]

    comparison = pd.DataFrame(rows)
    comparison = comparison.loc[comparison["row_scope"].eq("unflagged_test_days")].copy()
    comparison = comparison.sort_values("scenario")

    lines = [
        "| Scenario | Rows | Historical Revenue | Simulated Revenue | Delta | Delta % | Avg Recommended ADR |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in comparison.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["scenario"]),
                    f"{int(row['rows']):,}",
                    fmt_currency(row["historical_revenue_net"]),
                    fmt_currency(row["simulated_revenue_at_actual_rooms"]),
                    fmt_currency(row["simulated_revenue_delta"]),
                    fmt_pct(row["simulated_revenue_delta_pct"]),
                    fmt_currency(row["average_recommended_adr_nonzero_actual"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def feature_importance_section() -> list[str]:
    if not FEATURE_IMPORTANCE_INPUT.exists():
        return []

    importance = pd.read_csv(FEATURE_IMPORTANCE_INPUT).head(8)
    lines = [
        "## Feature Importance",
        "",
        "Top XGBoost features in the primary exclude-all-flagged training setup:",
        "",
        "| Rank | Feature | Importance |",
        "| --- | --- | --- |",
    ]
    for _, row in importance.iterrows():
        lines.append(f"| {int(row['rank'])} | `{row['feature']}` | {fmt_number(row['importance'], 4)} |")
    lines.extend(
        [
            "",
            (
                "The leading predictors are mostly recent same-week and two-week historical demand/revenue features, "
                "which is consistent with hotel demand having strong weekly seasonality and short-term persistence."
            ),
            "",
        ]
    )
    return lines


def deep_learning_section() -> list[str]:
    if not DEEP_LEARNING_COMPARISON_INPUT.exists():
        return []

    comparison = pd.read_csv(DEEP_LEARNING_COMPARISON_INPUT).sort_values(["mae", "rmse"])
    best = comparison.iloc[0]
    neural = comparison.loc[
        comparison["model_family"].isin(["neural_network", "sequence_neural_network"])
    ].sort_values(["mae", "rmse"]).iloc[0]
    display = comparison.head(8)
    return [
        "## Deep Learning Comparison",
        "",
        "Exclude-all-flagged 2025 test comparison:",
        "",
        markdown_metrics_table(display),
        "",
        (
            f"The best neural-network model is `{neural['model']}` with MAE {fmt_number(neural['mae'])}, "
            f"RMSE {fmt_number(neural['rmse'])}, and R2 {fmt_number(neural['r2'])}. "
            f"It does not beat the best overall comparison model, `{best['model']}` "
            f"(MAE {fmt_number(best['mae'])})."
        ),
        "",
        (
            "This supports the interpretation that sequence neural networks can get close on this daily demand task, "
            "but tree-based tabular models still generalize slightly better on the small dataset. The MLP variants "
            "remain materially weaker than the LSTM, GRU, and Transformer variants."
        ),
        "",
    ]


def business_metrics_section() -> list[str]:
    if not BUSINESS_METRICS_INPUT.exists():
        return []

    metrics = pd.read_csv(BUSINESS_METRICS_INPUT)
    metrics = metrics.loc[metrics["row_scope"].eq("unflagged_test_days")].sort_values("scenario")
    lines = [
        "Business metric comparison on unflagged 2025 test days:",
        "",
        "| Scenario | Actual Occ. | Forecast Occ. | Static Occ. Delta | Historical RevPAR | Simulated RevPAR | RevPAR Delta |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in metrics.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["scenario"]),
                    fmt_pct(row["actual_occupancy_rate"]),
                    fmt_pct(row["forecast_occupancy_rate"]),
                    fmt_pct(row["static_simulated_occupancy_delta"]),
                    fmt_currency(row["historical_revpar_net"]),
                    fmt_currency(row["simulated_revpar_at_actual_rooms"]),
                    fmt_currency(row["simulated_revpar_delta"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            (
                "The occupancy delta is intentionally zero in the static pricing simulation because the scenario applies "
                "new ADRs to realized rooms sold rather than estimating price elasticity or demand response."
            ),
            "",
        ]
    )
    return lines


def high_demand_examples_section() -> list[str]:
    if not HIGH_DEMAND_EXAMPLES_INPUT.exists():
        return []

    examples = pd.read_csv(HIGH_DEMAND_EXAMPLES_INPUT).head(6)
    lines = [
        "High-demand weekend scenario examples:",
        "",
        "| Date | Day | Actual Rooms | Forecast Rooms | Hist. ADR | Aggressive ADR | Conservative ADR | Aggressive Delta |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in examples.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["business_date"]),
                    str(row["day_of_week"]),
                    f"{int(row['target_rooms_sold']):,}",
                    fmt_number(row["forecast_rooms_sold_rounded"], 1),
                    fmt_currency(row["historical_adr_net"]),
                    fmt_currency(row["recommended_adr"]),
                    fmt_currency(row["conservative_recommended_adr"]),
                    fmt_currency(row["simulated_revenue_delta_at_actual_rooms"]),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def build_summary_markdown() -> str:
    modeling_summary = load_json(MODELING_SUMMARY_INPUT)
    pricing_summary = load_json(PRICING_SUMMARY_INPUT)
    baseline_metrics = pd.read_csv(BASELINE_METRICS_INPUT)
    sensitivity_metrics = pd.read_csv(SENSITIVITY_METRICS_INPUT)

    full_test = baseline_metrics.loc[baseline_metrics["split"].eq("test")].sort_values(["mae", "rmse"])
    full_test_learned = full_test.loc[full_test["model"].isin(LEARNED_MODELS)]
    sensitivity_test = sensitivity_metrics.loc[
        sensitivity_metrics["split"].eq("test") & sensitivity_metrics["model"].isin(LEARNED_MODELS)
    ].sort_values(["scenario", "mae", "rmse"])
    sensitivity_best_by_scenario = sensitivity_test.groupby("scenario", as_index=False).first()

    primary = sensitivity_best_by_scenario.loc[
        sensitivity_best_by_scenario["scenario"].eq("exclude_all_flagged")
    ].iloc[0]
    full_best = full_test_learned.iloc[0]

    date_coverage = modeling_summary["date_coverage"]
    data_flags = modeling_summary["data_quality_flags"]
    pricing_source = pricing_summary["pricing_model_source"]

    lines = [
        "# Project Summary",
        "",
        "## Data Pipeline",
        "",
        (
            f"The final modeling table is `processed_data/modeling_daily.csv` with "
            f"{modeling_summary['row_count']:,} daily rows and {modeling_summary['column_count']:,} columns "
            f"covering {date_coverage['start']} through {date_coverage['end']}. It joins cleaned room-sales "
            "history, reservation forecast fields, and guest-arrival enrichment into one date-grain table."
        ),
        "",
        (
            "The operational audit flags include "
            f"{data_flags['block_rows_sold_gt_total_rooms']} over-capacity rows and "
            f"{data_flags['block_zero_rooms_sold_rows']} zero-room-sold rows. These rows are retained for traceability, "
            "but the primary final metric convention uses the exclude-all-flagged sensitivity scenario."
        ),
        "",
        "## Feature Engineering",
        "",
        (
            "The forecasting features combine calendar variables with lagged and rolling historical demand, ADR, "
            "revenue, and occupancy signals. Same-day operational fields and same-day guest-enrichment fields are "
            "excluded from learned model inputs to avoid leakage."
        ),
        "",
        "## Baseline Model Comparison",
        "",
        "Full-data 2025 test metrics:",
        "",
        markdown_metrics_table(full_test.head(7)),
        "",
        (
            f"On the full test set, the best learned model by MAE is `{full_best['model']}` "
            f"(MAE {fmt_number(full_best['mae'])}, RMSE {fmt_number(full_best['rmse'])}, "
            f"R2 {fmt_number(full_best['r2'])})."
        ),
        "",
        "## Sensitivity Analysis",
        "",
        "Best learned model by test MAE under each data-quality convention:",
        "",
        markdown_metrics_table(sensitivity_best_by_scenario, include_scenario=True),
        "",
        (
            f"Primary reported model result: `{primary['model']}` on `exclude_all_flagged`, "
            f"with MAE {fmt_number(primary['mae'])}, RMSE {fmt_number(primary['rmse'])}, "
            f"and R2 {fmt_number(primary['r2'])} across {int(primary['row_count']):,} test rows. "
            "Full-data metrics should also be reported as a reference because they show the model's behavior before "
            "anomaly exclusion."
        ),
        "",
        *feature_importance_section(),
        *deep_learning_section(),
        "## Pipeline Diagram",
        "",
        "The final report figure `reports/figures/final_pipeline_architecture.png` summarizes the full pipeline from raw operational reports through cleaning, modeling, sensitivity analysis, pricing, and business outputs.",
        "",
        "## Pricing Recommendation Method",
        "",
        (
            f"The pricing layer uses the `{pricing_source['model']}` forecast selected from "
            f"`{pricing_source['scenario']}`. It computes forecast occupancy as forecast rooms sold divided by "
            "total property rooms, then applies bounded ADR adjustments to a historical-reference ADR."
        ),
        "",
        "Static unflagged 2025 pricing comparison:",
        "",
        markdown_pricing_table(pricing_summary),
        "",
        (
            "The aggressive scenario uses 4%, 8%, and 12% bands; the conservative scenario uses 2%, 4%, and 6% bands. "
            "Both simulations apply recommended ADR to actual realized rooms, so the result is a static counterfactual "
            "rather than a demand-response estimate."
        ),
        "",
        *business_metrics_section(),
        *high_demand_examples_section(),
        "## Limitations",
        "",
        "- Pricing simulations assume rooms sold stay fixed after ADR changes.",
        "- The model does not estimate price elasticity, competitor response, or channel-mix changes.",
        "- January 2025 zero-room-sold flagged dates should be excluded from primary business claims or explained as anomalies.",
        "- The dataset is small for deep learning; tree-based models currently provide stronger and more interpretable MVP results.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    FINAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_SUMMARY_OUTPUT.write_text(build_summary_markdown(), encoding="utf-8")
    print(f"Wrote {PROJECT_SUMMARY_OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
