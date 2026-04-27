from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.train_baselines import (
    DATE_COLUMN,
    MODELING_INPUT,
    TARGET_COLUMN,
    chronological_split,
    fit_predict_models,
    select_feature_columns,
)


REPORTS_DIR = REPO_ROOT / "reports"
AUDIT_REPORTS_DIR = REPORTS_DIR / "audit"
BASELINE_REPORTS_DIR = REPORTS_DIR / "baselines"
FIGURES_DIR = REPORTS_DIR / "figures"
FLAGS_INPUT = AUDIT_REPORTS_DIR / "data_quality_flags.csv"

METRICS_OUTPUT = BASELINE_REPORTS_DIR / "baseline_sensitivity_metrics.csv"
PREDICTIONS_OUTPUT = BASELINE_REPORTS_DIR / "baseline_sensitivity_predictions.csv"
SUMMARY_OUTPUT = BASELINE_REPORTS_DIR / "baseline_sensitivity_summary.json"
FIGURE_OUTPUT = FIGURES_DIR / "baseline_sensitivity_test_mae.png"

LEARNED_MODELS = {"ridge_regression", "random_forest", "xgboost"}


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    modeling = pd.read_csv(MODELING_INPUT, parse_dates=[DATE_COLUMN])
    flags = pd.read_csv(FLAGS_INPUT, parse_dates=[DATE_COLUMN])
    return modeling.sort_values(DATE_COLUMN).reset_index(drop=True), flags


def scenario_dates(flags: pd.DataFrame) -> dict[str, set[pd.Timestamp]]:
    over_capacity = set(
        flags.loc[flags["flag_type"].eq("rooms_sold_gt_property_total"), DATE_COLUMN]
    )
    all_flagged = set(flags[DATE_COLUMN])
    return {
        "full_data_reference": set(),
        "exclude_over_capacity_only": over_capacity,
        "exclude_all_flagged": all_flagged,
    }


def run_scenario(
    name: str,
    excluded_dates: set[pd.Timestamp],
    modeling: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    scenario_frame = modeling.loc[~modeling[DATE_COLUMN].isin(excluded_dates)].copy()
    train, validation, test = chronological_split(scenario_frame)
    predictions, metrics = fit_predict_models(train, validation, test, feature_columns)
    predictions.insert(0, "scenario", name)
    metrics.insert(0, "scenario", name)

    details = {
        "scenario": name,
        "excluded_dates": [value.date().isoformat() for value in sorted(excluded_dates)],
        "excluded_row_count": int(len(excluded_dates)),
        "rows_after_exclusion": int(len(scenario_frame)),
        "splits": {
            "train": {"rows": int(len(train)), "start": train[DATE_COLUMN].min().date().isoformat(), "end": train[DATE_COLUMN].max().date().isoformat()},
            "validation": {"rows": int(len(validation)), "start": validation[DATE_COLUMN].min().date().isoformat(), "end": validation[DATE_COLUMN].max().date().isoformat()},
            "test": {"rows": int(len(test)), "start": test[DATE_COLUMN].min().date().isoformat(), "end": test[DATE_COLUMN].max().date().isoformat()},
        },
        "best_test_model_by_mae": metrics.loc[metrics["split"].eq("test")].sort_values("mae").iloc[0].to_dict(),
        "best_test_learned_model_by_mae": metrics.loc[
            metrics["split"].eq("test") & metrics["model"].isin(LEARNED_MODELS)
        ].sort_values("mae").iloc[0].to_dict(),
    }
    return predictions, metrics, details


def plot_sensitivity(metrics: pd.DataFrame) -> None:
    test_metrics = metrics.loc[metrics["split"].eq("test")].copy()
    sns.set_theme(style="whitegrid")
    fig, axis = plt.subplots(figsize=(12, 6))
    sns.barplot(data=test_metrics, x="mae", y="model", hue="scenario", ax=axis)
    axis.set_title("Baseline Test MAE Sensitivity to Flagged Row Exclusion")
    axis.set_xlabel("Mean absolute error, rooms sold")
    axis.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURE_OUTPUT, dpi=180)
    plt.close(fig)


def main() -> None:
    BASELINE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    modeling, flags = load_inputs()
    feature_columns = select_feature_columns(modeling)

    all_predictions = []
    all_metrics = []
    scenarios = []
    for name, excluded_dates in scenario_dates(flags).items():
        predictions, metrics, details = run_scenario(name, excluded_dates, modeling, feature_columns)
        all_predictions.append(predictions)
        all_metrics.append(metrics)
        scenarios.append(details)

    predictions = pd.concat(all_predictions, ignore_index=True)
    metrics = pd.concat(all_metrics, ignore_index=True).sort_values(["scenario", "split", "mae"])
    predictions.to_csv(PREDICTIONS_OUTPUT, index=False, date_format="%Y-%m-%d")
    metrics.to_csv(METRICS_OUTPUT, index=False)

    preferred = next(item for item in scenarios if item["scenario"] == "exclude_all_flagged")
    summary = {
        "input_file": str(MODELING_INPUT.relative_to(REPO_ROOT)),
        "flags_file": str(FLAGS_INPUT.relative_to(REPO_ROOT)),
        "metrics_file": str(METRICS_OUTPUT.relative_to(REPO_ROOT)),
        "predictions_file": str(PREDICTIONS_OUTPUT.relative_to(REPO_ROOT)),
        "figure_file": str(FIGURE_OUTPUT.relative_to(REPO_ROOT)),
        "target": TARGET_COLUMN,
        "feature_count": len(feature_columns),
        "scenarios": scenarios,
        "preferred_pricing_model_source": {
            "scenario": preferred["scenario"],
            "model": preferred["best_test_learned_model_by_mae"]["model"],
            "reason": "Best learned model by test MAE after excluding all currently flagged operational rows.",
            "metrics": preferred["best_test_learned_model_by_mae"],
        },
    }
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot_sensitivity(metrics)

    best = summary["preferred_pricing_model_source"]
    print(f"Wrote {METRICS_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {PREDICTIONS_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {FIGURE_OUTPUT.relative_to(REPO_ROOT)}")
    print(
        "Preferred pricing model after sensitivity: "
        f"{best['model']} from {best['scenario']} "
        f"MAE={best['metrics']['mae']:.3f}"
    )


if __name__ == "__main__":
    main()
