from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.features.build_daily_modeling_table import add_date_features, add_history_features
from src.models.train_baselines import DATE_COLUMN, MODELING_INPUT, TARGET_COLUMN
from src.pricing.build_pricing_recommendations import apply_pricing_rule


REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "models"
BASELINE_MODELS_DIR = MODELS_DIR / "baselines"
DEEP_LEARNING_MODELS_DIR = MODELS_DIR / "deep_learning"
FLAGS_INPUT = REPO_ROOT / "reports" / "audit" / "data_quality_flags.csv"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_modeling_table() -> pd.DataFrame:
    return pd.read_csv(MODELING_INPUT, parse_dates=[DATE_COLUMN]).sort_values(DATE_COLUMN).reset_index(drop=True)


def _load_unflagged_modeling_table() -> pd.DataFrame:
    modeling = _load_modeling_table()
    if not FLAGS_INPUT.exists():
        return modeling

    flags = pd.read_csv(FLAGS_INPUT, parse_dates=[DATE_COLUMN])
    flagged_dates = set(flags[DATE_COLUMN])
    return modeling.loc[~modeling[DATE_COLUMN].isin(flagged_dates)].copy().reset_index(drop=True)


def _target_dates_frame(modeling: pd.DataFrame, target_dates: pd.DatetimeIndex | list | tuple) -> pd.DataFrame:
    dates = pd.to_datetime(pd.Index(target_dates)).normalize()
    frame = modeling.copy()
    frame[DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN]).dt.normalize()
    return frame.loc[frame[DATE_COLUMN].isin(set(dates))].sort_values(DATE_COLUMN).reset_index(drop=True)


def _default_property_total_rooms(modeling: pd.DataFrame) -> float:
    mode = modeling["property_total_rooms"].dropna().mode()
    return float(mode.iloc[0]) if len(mode) else 60.0


def _future_reference_adr(current_date: pd.Timestamp, history: pd.DataFrame) -> float:
    nonzero_history = history.loc[history["block_adr_net"] > 0, [DATE_COLUMN, "block_adr_net"]].copy()
    if nonzero_history.empty:
        return 150.0

    seasonal = nonzero_history.loc[
        (nonzero_history[DATE_COLUMN].dt.month == current_date.month)
        & (nonzero_history[DATE_COLUMN].dt.day == current_date.day),
        "block_adr_net",
    ]
    if not seasonal.empty:
        return float(seasonal.median())

    recent = nonzero_history["block_adr_net"].tail(28).median()
    if not pd.isna(recent):
        return float(recent)
    return float(nonzero_history["block_adr_net"].median())


def _minimum_forecast_history(modeling: pd.DataFrame, max_future_date: pd.Timestamp) -> pd.DataFrame:
    """Build a daily future shell with base values needed for lag features."""
    working = modeling.sort_values(DATE_COLUMN).reset_index(drop=True).copy()
    working[DATE_COLUMN] = pd.to_datetime(working[DATE_COLUMN]).dt.normalize()
    property_total_rooms = _default_property_total_rooms(working)
    last_date = working[DATE_COLUMN].max()
    if max_future_date <= last_date:
        return working

    future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), end=max_future_date, freq="D")
    future_rows = []
    for current_date in future_dates:
        reference_adr = _future_reference_adr(current_date, working)
        future_rows.append(
            {
                DATE_COLUMN: current_date,
                "property_total_rooms": property_total_rooms,
                TARGET_COLUMN: np.nan,
                "block_adr_net": reference_adr,
                "block_room_revenue_net": np.nan,
                "block_occupancy_rate_reported": np.nan,
            }
        )
    return pd.concat([working, pd.DataFrame(future_rows)], ignore_index=True, sort=False)


def _predict_future_tabular(
    model: Any,
    feature_columns: list[str],
    target_dates: pd.DatetimeIndex,
    modeling: pd.DataFrame,
) -> pd.DataFrame:
    """Recursively forecast dates beyond the observed modeling table."""
    max_future_date = target_dates.max()
    working = _minimum_forecast_history(modeling, max_future_date)
    property_total_rooms = _default_property_total_rooms(modeling)
    last_observed_date = modeling[DATE_COLUMN].max()
    requested_dates = set(target_dates)
    rows = []

    for current_date in pd.date_range(last_observed_date + pd.Timedelta(days=1), max_future_date, freq="D"):
        engineered = add_history_features(add_date_features(working.copy()))
        current_mask = engineered[DATE_COLUMN].eq(current_date)
        if not current_mask.any():
            continue

        current_features = engineered.loc[current_mask, feature_columns]
        predicted = float(np.asarray(model.predict(current_features), dtype=float)[0])
        predicted = float(np.clip(predicted, 0, property_total_rooms))

        working_mask = working[DATE_COLUMN].eq(current_date)
        reference_adr = _future_reference_adr(current_date, working)
        working.loc[working_mask, TARGET_COLUMN] = predicted
        working.loc[working_mask, "block_adr_net"] = reference_adr
        working.loc[working_mask, "block_room_revenue_net"] = predicted * reference_adr
        working.loc[working_mask, "block_occupancy_rate_reported"] = predicted / property_total_rooms

        if current_date in requested_dates:
            rows.append({DATE_COLUMN: current_date, "forecast_rooms_sold": predicted})

    return pd.DataFrame(rows, columns=[DATE_COLUMN, "forecast_rooms_sold"])


def list_persisted_models() -> list[dict[str, str]]:
    """Return models with saved artifacts that can be used for live inference."""
    persisted: list[dict[str, str]] = []

    baseline_manifest = BASELINE_MODELS_DIR / "manifest.json"
    if baseline_manifest.exists():
        manifest = _read_json(baseline_manifest)
        for model in manifest.get("models", []):
            model_file = BASELINE_MODELS_DIR / model.get("file", "")
            if model_file.exists():
                persisted.append(
                    {
                        "family": "baseline",
                        "name": model["name"],
                        "kind": model.get("kind", "sklearn_pipeline"),
                    }
                )

    deep_manifest = DEEP_LEARNING_MODELS_DIR / "manifest.json"
    if deep_manifest.exists():
        manifest = _read_json(deep_manifest)
        for model in manifest.get("models", []):
            file_name = model.get("file") or model.get("weights_file")
            model_file = DEEP_LEARNING_MODELS_DIR / str(file_name)
            if model_file.exists():
                persisted.append(
                    {
                        "family": "deep_learning",
                        "name": model["name"],
                        "kind": model.get("kind", "unknown"),
                    }
                )

    return sorted(persisted, key=lambda row: (row["family"], row["name"]))


def _predict_tabular_model(
    model_path: Path,
    feature_columns_path: Path,
    target_dates: pd.DatetimeIndex | list | tuple,
) -> pd.DataFrame:
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {model_path.relative_to(REPO_ROOT)}")
    if not feature_columns_path.exists():
        raise FileNotFoundError(f"Feature-column artifact not found: {feature_columns_path.relative_to(REPO_ROOT)}")

    model = joblib.load(model_path)
    feature_columns = json.loads(feature_columns_path.read_text(encoding="utf-8"))
    modeling = _load_modeling_table()
    modeling[DATE_COLUMN] = pd.to_datetime(modeling[DATE_COLUMN]).dt.normalize()
    dates = pd.to_datetime(pd.Index(target_dates)).normalize()

    rows = _target_dates_frame(modeling, dates)
    future_dates = pd.DatetimeIndex([value for value in dates if value > modeling[DATE_COLUMN].max()])
    if rows.empty and future_dates.empty:
        return pd.DataFrame(columns=[DATE_COLUMN, "forecast_rooms_sold"])

    outputs = []
    if not rows.empty:
        predicted = np.asarray(model.predict(rows[feature_columns]), dtype=float)
        predicted = np.clip(predicted, 0, rows["property_total_rooms"].to_numpy(dtype=float))
        outputs.append(
            pd.DataFrame(
                {
                    DATE_COLUMN: rows[DATE_COLUMN],
                    "forecast_rooms_sold": predicted,
                }
            )
        )
    if not future_dates.empty:
        outputs.append(_predict_future_tabular(model, feature_columns, future_dates, modeling))

    return pd.concat(outputs, ignore_index=True).sort_values(DATE_COLUMN).reset_index(drop=True)


def _predict_sequence_model(model_name: str, target_dates: pd.DatetimeIndex | list | tuple) -> pd.DataFrame:
    try:
        import torch

        from src.models.train_deep_learning import DEVICE, SequenceRegressor
    except Exception as exc:  # pragma: no cover - depends on optional torch install.
        raise RuntimeError("PyTorch is required for live sequence-model inference.") from exc

    spec_path = DEEP_LEARNING_MODELS_DIR / f"{model_name}.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"Sequence spec not found: {spec_path.relative_to(REPO_ROOT)}")
    spec = _read_json(spec_path)

    preprocessors_path = DEEP_LEARNING_MODELS_DIR / spec["preprocessors_file"]
    weights_path = DEEP_LEARNING_MODELS_DIR / spec["weights_file"]
    if not preprocessors_path.exists():
        raise FileNotFoundError(f"Sequence preprocessors not found: {preprocessors_path.relative_to(REPO_ROOT)}")
    if not weights_path.exists():
        raise FileNotFoundError(f"Sequence weights not found: {weights_path.relative_to(REPO_ROOT)}")

    preprocessors = joblib.load(preprocessors_path)
    feature_columns = preprocessors["feature_columns"]
    modeling = _load_unflagged_modeling_table()
    modeling[DATE_COLUMN] = pd.to_datetime(modeling[DATE_COLUMN]).dt.normalize()

    features = preprocessors["feature_scaler"].transform(
        preprocessors["imputer"].transform(modeling[feature_columns])
    ).astype(np.float32)

    requested_dates = set(pd.to_datetime(pd.Index(target_dates)).normalize())
    lookback = int(spec["lookback"])
    sequences: list[np.ndarray] = []
    endpoint_rows: list[pd.Series] = []
    for index, row in modeling.iterrows():
        if row[DATE_COLUMN] not in requested_dates or index < lookback - 1:
            continue
        sequences.append(features[index - lookback + 1 : index + 1])
        endpoint_rows.append(row)

    if not sequences:
        return pd.DataFrame(columns=[DATE_COLUMN, "forecast_rooms_sold"])

    model = SequenceRegressor(
        input_size=int(spec["input_size"]),
        kind=spec["kind"],
        hidden_size=int(spec["hidden_size"]),
        num_layers=int(spec["num_layers"]),
        dropout=float(spec["dropout"]),
        num_heads=int(spec.get("num_heads", 4)),
        lookback=lookback,
    ).to(DEVICE)
    state = torch.load(weights_path, map_location=DEVICE)
    model.load_state_dict(state)
    model.eval()

    with torch.no_grad():
        batch = torch.tensor(np.stack(sequences), dtype=torch.float32).to(DEVICE)
        scaled_prediction = model(batch).cpu().numpy().reshape(-1, 1)
    predicted = preprocessors["target_scaler"].inverse_transform(scaled_prediction).reshape(-1)

    rows = pd.DataFrame(endpoint_rows).reset_index(drop=True)
    predicted = np.clip(predicted, 0, rows["property_total_rooms"].to_numpy(dtype=float))
    return pd.DataFrame(
        {
            DATE_COLUMN: rows[DATE_COLUMN],
            "forecast_rooms_sold": predicted,
        }
    )


def predict_rooms_sold(model_name: str, target_dates: pd.DatetimeIndex | list | tuple) -> pd.DataFrame:
    """Run live demand inference for one persisted model."""
    baseline_path = BASELINE_MODELS_DIR / f"{model_name}.joblib"
    if baseline_path.exists():
        return _predict_tabular_model(
            baseline_path,
            BASELINE_MODELS_DIR / "feature_columns.json",
            target_dates,
        )

    deep_joblib_path = DEEP_LEARNING_MODELS_DIR / f"{model_name}.joblib"
    if deep_joblib_path.exists():
        return _predict_tabular_model(
            deep_joblib_path,
            DEEP_LEARNING_MODELS_DIR / "feature_columns.json",
            target_dates,
        )

    deep_sequence_path = DEEP_LEARNING_MODELS_DIR / f"{model_name}.pt"
    if deep_sequence_path.exists():
        return _predict_sequence_model(model_name, target_dates)

    available = ", ".join(model["name"] for model in list_persisted_models()) or "none"
    raise ValueError(f"No persisted model named '{model_name}'. Available models: {available}")


def predict_with_pricing(
    model_name: str,
    target_dates: pd.DatetimeIndex | list | tuple,
    scenario: str = "aggressive",
) -> pd.DataFrame:
    """Run demand inference and convert the forecast into ADR recommendations."""
    forecast = predict_rooms_sold(model_name, target_dates)
    if forecast.empty:
        return apply_pricing_rule(forecast, scenario=scenario, model_name=model_name)
    return apply_pricing_rule(forecast, scenario=scenario, model_name=model_name)
