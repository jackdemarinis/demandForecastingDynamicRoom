from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import xgboost
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover - xgboost is optional at runtime.
    xgboost = None
    XGBRegressor = None


REPO_ROOT = Path(__file__).resolve().parents[2]
MODELING_INPUT = REPO_ROOT / "processed_data" / "modeling_daily.csv"
REPORTS_DIR = REPO_ROOT / "reports"
BASELINE_REPORTS_DIR = REPORTS_DIR / "baselines"
FIGURES_DIR = REPORTS_DIR / "figures"
MODELS_DIR = REPO_ROOT / "models" / "baselines"

PREDICTIONS_OUTPUT = BASELINE_REPORTS_DIR / "baseline_predictions.csv"
METRICS_CSV_OUTPUT = BASELINE_REPORTS_DIR / "baseline_metrics.csv"
METRICS_JSON_OUTPUT = BASELINE_REPORTS_DIR / "baseline_metrics.json"
SUMMARY_OUTPUT = BASELINE_REPORTS_DIR / "baseline_training_summary.json"
PREDICTED_ACTUAL_FIGURE = FIGURES_DIR / "baseline_predicted_vs_actual_test.png"
ERROR_FIGURE = FIGURES_DIR / "baseline_test_mae.png"

TARGET_COLUMN = "target_rooms_sold"
DATE_COLUMN = "business_date"

TRAIN_END = pd.Timestamp("2024-06-30")
VALIDATION_END = pd.Timestamp("2024-12-31")


def load_modeling_table() -> pd.DataFrame:
    frame = pd.read_csv(MODELING_INPUT, parse_dates=[DATE_COLUMN])
    return frame.sort_values(DATE_COLUMN).reset_index(drop=True)


def select_feature_columns(frame: pd.DataFrame) -> list[str]:
    date_columns = [
        column
        for column in frame.columns
        if column.startswith("date_")
        and not column.endswith("_sin")
        and not column.endswith("_cos")
    ]
    cyclical_date_columns = [
        column for column in frame.columns if column.startswith("date_") and column.endswith(("_sin", "_cos"))
    ]
    history_columns = [
        column
        for column in frame.columns
        if "_lag_" in column or "_rolling_" in column or column.endswith("_minus_7d")
    ]
    allowed = date_columns + cyclical_date_columns + history_columns

    # Keep models forecast-oriented: no same-day operational/enrichment, source/audit, or rf_* columns.
    blocked_prefixes = ("block_", "rf_", "source_", "report_")
    selected = []
    for column in allowed:
        if column == TARGET_COLUMN or column == DATE_COLUMN:
            continue
        if column.startswith(blocked_prefixes) and "_lag_" not in column and "_rolling_" not in column:
            continue
        selected.append(column)
    return sorted(set(selected))


def chronological_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame[DATE_COLUMN] <= TRAIN_END].copy()
    validation = frame.loc[
        (frame[DATE_COLUMN] > TRAIN_END) & (frame[DATE_COLUMN] <= VALIDATION_END)
    ].copy()
    test = frame.loc[frame[DATE_COLUMN] > VALIDATION_END].copy()
    return train, validation, test


def regression_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    nonzero_mask = actual_array != 0
    if nonzero_mask.any():
        mape = np.mean(np.abs((actual_array[nonzero_mask] - predicted_array[nonzero_mask]) / actual_array[nonzero_mask]))
    else:
        mape = np.nan
    return {
        "mae": float(mean_absolute_error(actual_array, predicted_array)),
        "rmse": float(np.sqrt(mean_squared_error(actual_array, predicted_array))),
        "mape": float(mape) if not np.isnan(mape) else None,
        "r2": float(r2_score(actual_array, predicted_array)),
    }


def add_prediction(
    predictions: pd.DataFrame,
    metrics: list[dict],
    split_name: str,
    model_name: str,
    split_frame: pd.DataFrame,
    predicted: np.ndarray | pd.Series,
) -> pd.DataFrame:
    predicted_series = pd.Series(predicted, index=split_frame.index, dtype=float)
    predicted_series = predicted_series.clip(lower=0, upper=split_frame["property_total_rooms"].max())
    metrics.append(
        {
            "model": model_name,
            "split": split_name,
            "row_count": int(len(split_frame)),
            **regression_metrics(split_frame[TARGET_COLUMN], predicted_series),
        }
    )
    rows = pd.DataFrame(
        {
            DATE_COLUMN: split_frame[DATE_COLUMN],
            "split": split_name,
            "model": model_name,
            "actual": split_frame[TARGET_COLUMN],
            "predicted": predicted_series,
            "absolute_error": (split_frame[TARGET_COLUMN] - predicted_series).abs(),
        }
    )
    return pd.concat([predictions, rows], ignore_index=True)


def fit_predict_models(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics: list[dict] = []
    predictions = pd.DataFrame()

    split_frames = {"validation": validation, "test": test}
    direct_baselines = {
        "naive_previous_day": "target_rooms_sold_lag_1d",
        "seasonal_previous_week": "target_rooms_sold_lag_7d",
        "rolling_7d_mean": "target_rooms_sold_rolling_7d_mean",
        "rolling_28d_mean": "target_rooms_sold_rolling_28d_mean",
    }

    for split_name, split_frame in split_frames.items():
        for model_name, column in direct_baselines.items():
            predictions = add_prediction(
                predictions,
                metrics,
                split_name,
                model_name,
                split_frame,
                split_frame[column],
            )

    train_model_frame = train.dropna(subset=[TARGET_COLUMN]).copy()
    model_specs = {
        "ridge_regression": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=10.0)),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=500,
                        min_samples_leaf=5,
                        random_state=561,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }
    if XGBRegressor is not None:
        model_specs["xgboost"] = Pipeline(
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

    x_train = train_model_frame[feature_columns]
    y_train = train_model_frame[TARGET_COLUMN]

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    persisted_models: dict[str, str] = {}
    for model_name, model in model_specs.items():
        model.fit(x_train, y_train)
        artifact_path = MODELS_DIR / f"{model_name}.joblib"
        joblib.dump(model, artifact_path)
        persisted_models[model_name] = str(artifact_path.relative_to(REPO_ROOT))
        for split_name, split_frame in split_frames.items():
            predicted = model.predict(split_frame[feature_columns])
            predictions = add_prediction(
                predictions,
                metrics,
                split_name,
                model_name,
                split_frame,
                predicted,
            )

    metrics_frame = pd.DataFrame(metrics).sort_values(["split", "mae", "rmse"]).reset_index(drop=True)
    metrics_frame.attrs["persisted_models"] = persisted_models
    return predictions, metrics_frame


def plot_predicted_vs_actual(predictions: pd.DataFrame, metrics: pd.DataFrame) -> None:
    test_metrics = metrics.loc[metrics["split"] == "test"].sort_values("mae")
    selected_models = test_metrics["model"].head(4).tolist()
    plot_frame = predictions.loc[
        (predictions["split"] == "test") & (predictions["model"].isin(selected_models))
    ].copy()

    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(len(selected_models), 1, figsize=(14, 3.2 * len(selected_models)), sharex=True)
    if len(selected_models) == 1:
        axes = [axes]

    for axis, model_name in zip(axes, selected_models):
        model_frame = plot_frame.loc[plot_frame["model"] == model_name]
        axis.plot(model_frame[DATE_COLUMN], model_frame["actual"], label="Actual", color="#1f2937", linewidth=1.8)
        axis.plot(
            model_frame[DATE_COLUMN],
            model_frame["predicted"],
            label="Predicted",
            color="#2563eb",
            linewidth=1.4,
        )
        metric_row = test_metrics.loc[test_metrics["model"] == model_name].iloc[0]
        axis.set_title(f"{model_name} test forecast, MAE={metric_row['mae']:.2f}, RMSE={metric_row['rmse']:.2f}")
        axis.set_ylabel("Rooms sold")
        axis.legend(loc="upper right")

    axes[-1].set_xlabel("Business date")
    fig.tight_layout()
    fig.savefig(PREDICTED_ACTUAL_FIGURE, dpi=180)
    plt.close(fig)


def plot_test_mae(metrics: pd.DataFrame) -> None:
    test_metrics = metrics.loc[metrics["split"] == "test"].sort_values("mae").copy()
    sns.set_theme(style="whitegrid")
    fig, axis = plt.subplots(figsize=(10, 5))
    sns.barplot(data=test_metrics, x="mae", y="model", ax=axis, color="#2563eb")
    axis.set_title("Baseline Test MAE")
    axis.set_xlabel("Mean absolute error, rooms sold")
    axis.set_ylabel("")
    fig.tight_layout()
    fig.savefig(ERROR_FIGURE, dpi=180)
    plt.close(fig)


def write_outputs(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    feature_columns: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> None:
    BASELINE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    (MODELS_DIR / "feature_columns.json").write_text(
        json.dumps(feature_columns, indent=2), encoding="utf-8"
    )
    persisted_models = metrics.attrs.get("persisted_models", {})
    manifest = {
        "family": "baseline",
        "target": TARGET_COLUMN,
        "feature_columns_file": "feature_columns.json",
        "train_window": {
            "start": train[DATE_COLUMN].min().date().isoformat(),
            "end": train[DATE_COLUMN].max().date().isoformat(),
            "rows": int(len(train)),
        },
        "library_versions": {
            "sklearn": sklearn.__version__,
            "xgboost": xgboost.__version__ if xgboost is not None else None,
        },
        "models": [
            {"name": name, "kind": "sklearn_pipeline", "file": Path(path).name}
            for name, path in persisted_models.items()
        ],
    }
    (MODELS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    predictions.to_csv(PREDICTIONS_OUTPUT, index=False, date_format="%Y-%m-%d")
    metrics.to_csv(METRICS_CSV_OUTPUT, index=False)

    summary = {
        "input_file": str(MODELING_INPUT.relative_to(REPO_ROOT)),
        "target": TARGET_COLUMN,
        "feature_policy": (
            "Learned models use date features and shifted historical lag/rolling features only. "
            "Same-day Block operational fields, same-day GuestNameList enrichment fields, and all "
            "ReservationForecast fields are excluded from model inputs to avoid leakage and "
            "unavailable-future features."
        ),
        "feature_count": len(feature_columns),
        "feature_columns": feature_columns,
        "splits": {
            "train": {
                "start": train[DATE_COLUMN].min().date().isoformat(),
                "end": train[DATE_COLUMN].max().date().isoformat(),
                "rows": int(len(train)),
            },
            "validation": {
                "start": validation[DATE_COLUMN].min().date().isoformat(),
                "end": validation[DATE_COLUMN].max().date().isoformat(),
                "rows": int(len(validation)),
            },
            "test": {
                "start": test[DATE_COLUMN].min().date().isoformat(),
                "end": test[DATE_COLUMN].max().date().isoformat(),
                "rows": int(len(test)),
            },
        },
        "outputs": {
            "predictions": str(PREDICTIONS_OUTPUT.relative_to(REPO_ROOT)),
            "metrics_csv": str(METRICS_CSV_OUTPUT.relative_to(REPO_ROOT)),
            "metrics_json": str(METRICS_JSON_OUTPUT.relative_to(REPO_ROOT)),
            "predicted_vs_actual_figure": str(PREDICTED_ACTUAL_FIGURE.relative_to(REPO_ROOT)),
            "test_mae_figure": str(ERROR_FIGURE.relative_to(REPO_ROOT)),
        },
        "best_test_model_by_mae": metrics.loc[metrics["split"] == "test"].sort_values("mae").iloc[0].to_dict(),
        "metrics": metrics.to_dict(orient="records"),
    }
    METRICS_JSON_OUTPUT.write_text(json.dumps(metrics.to_dict(orient="records"), indent=2), encoding="utf-8")
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    plot_predicted_vs_actual(predictions, metrics)
    plot_test_mae(metrics)


def main() -> None:
    frame = load_modeling_table()
    feature_columns = select_feature_columns(frame)
    train, validation, test = chronological_split(frame)

    predictions, metrics = fit_predict_models(train, validation, test, feature_columns)
    write_outputs(predictions, metrics, feature_columns, train, validation, test)

    best_test = metrics.loc[metrics["split"] == "test"].sort_values("mae").iloc[0]
    print(f"Wrote {METRICS_CSV_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {PREDICTIONS_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {PREDICTED_ACTUAL_FIGURE.relative_to(REPO_ROOT)}")
    print(
        "Best test model by MAE: "
        f"{best_test['model']} MAE={best_test['mae']:.3f}, RMSE={best_test['rmse']:.3f}, "
        f"R2={best_test['r2']:.3f}"
    )


if __name__ == "__main__":
    main()
