from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PRED = REPO_ROOT / "reports" / "baselines" / "baseline_sensitivity_predictions.csv"
DEEP_PRED = REPO_ROOT / "reports" / "deep_learning" / "deep_learning_predictions.csv"
OUTPUT_CSV = REPO_ROOT / "reports" / "deep_learning" / "paired_bootstrap_vs_xgboost.csv"
OUTPUT_JSON = REPO_ROOT / "reports" / "deep_learning" / "paired_bootstrap_vs_xgboost.json"

REFERENCE_MODEL = "xgboost"
SCENARIO = "exclude_all_flagged"
SPLIT = "test"
COMPARISONS = [
    ("random_forest",          "tree_baseline"),
    ("gru_56d_wide",           "best_gru"),
    ("transformer_28d_small",  "best_transformer"),
    ("lstm_56d_regularized",   "best_lstm"),
    ("mlp_medium",             "best_mlp"),
]
N_BOOTSTRAP = 10_000
SEED = 561


def load_aligned_errors() -> pd.DataFrame:
    baseline = pd.read_csv(BASELINE_PRED, parse_dates=["business_date"])
    baseline = baseline.loc[
        baseline["scenario"].eq(SCENARIO) & baseline["split"].eq(SPLIT)
    ].copy()
    deep = pd.read_csv(DEEP_PRED, parse_dates=["business_date"])
    deep = deep.loc[deep["split"].eq(SPLIT)].copy()
    deep["scenario"] = SCENARIO
    combined = pd.concat([baseline, deep], ignore_index=True)

    needed_models = {REFERENCE_MODEL} | {m for m, _ in COMPARISONS}
    combined = combined.loc[combined["model"].isin(needed_models)].copy()
    pivot = combined.pivot_table(
        index="business_date",
        columns="model",
        values="absolute_error",
        aggfunc="first",
    ).dropna()
    return pivot


def paired_bootstrap_ci(
    errors: np.ndarray,
    rng: np.random.Generator,
    n_bootstrap: int = N_BOOTSTRAP,
) -> tuple[float, float, float]:
    """Returns (point_estimate_delta_mae, ci_low, ci_high) for MAE_other - MAE_xgboost.

    Positive delta means the other model has higher MAE (worse) than XGBoost.
    Errors is shape (n_rows, 2): [:,0] is xgboost AE, [:,1] is other AE.
    """
    n_rows = errors.shape[0]
    deltas = np.empty(n_bootstrap, dtype=np.float64)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n_rows, size=n_rows)
        sample = errors[idx]
        deltas[i] = sample[:, 1].mean() - sample[:, 0].mean()
    point = errors[:, 1].mean() - errors[:, 0].mean()
    low, high = np.quantile(deltas, [0.025, 0.975])
    return float(point), float(low), float(high)


def main() -> None:
    pivot = load_aligned_errors()
    rng = np.random.default_rng(SEED)

    rows: list[dict] = []
    n_rows = len(pivot)
    xgb_mae = float(pivot[REFERENCE_MODEL].mean())
    for model_name, label in COMPARISONS:
        if model_name not in pivot.columns:
            continue
        errors = pivot[[REFERENCE_MODEL, model_name]].to_numpy()
        point, low, high = paired_bootstrap_ci(errors, rng)
        other_mae = float(pivot[model_name].mean())
        rows.append({
            "comparison": label,
            "model": model_name,
            "n_rows": n_rows,
            "xgboost_mae": round(xgb_mae, 4),
            "other_mae": round(other_mae, 4),
            "delta_mae_other_minus_xgb": round(point, 4),
            "ci_low_95": round(low, 4),
            "ci_high_95": round(high, 4),
            "ci_excludes_zero": bool(low > 0 or high < 0),
        })

    frame = pd.DataFrame(rows)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_CSV, index=False)
    OUTPUT_JSON.write_text(json.dumps({
        "scenario": SCENARIO,
        "split": SPLIT,
        "reference_model": REFERENCE_MODEL,
        "n_test_rows": n_rows,
        "n_bootstrap": N_BOOTSTRAP,
        "seed": SEED,
        "results": rows,
    }, indent=2))

    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
