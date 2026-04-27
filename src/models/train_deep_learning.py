from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.compose import TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
except Exception:  # pragma: no cover - torch is optional until sequence models are requested.
    torch = None
    nn = None
    DataLoader = None
    TensorDataset = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.train_baselines import (
    DATE_COLUMN,
    MODELING_INPUT,
    TARGET_COLUMN,
    add_prediction,
    chronological_split,
    regression_metrics,
    select_feature_columns,
)


REPORTS_DIR = REPO_ROOT / "reports"
AUDIT_REPORTS_DIR = REPORTS_DIR / "audit"
BASELINE_REPORTS_DIR = REPORTS_DIR / "baselines"
DEEP_LEARNING_REPORTS_DIR = REPORTS_DIR / "deep_learning"
FIGURES_DIR = REPORTS_DIR / "figures"
FLAGS_INPUT = AUDIT_REPORTS_DIR / "data_quality_flags.csv"
SENSITIVITY_METRICS_INPUT = BASELINE_REPORTS_DIR / "baseline_sensitivity_metrics.csv"

PREDICTIONS_OUTPUT = DEEP_LEARNING_REPORTS_DIR / "deep_learning_predictions.csv"
METRICS_OUTPUT = DEEP_LEARNING_REPORTS_DIR / "deep_learning_metrics.csv"
COMPARISON_OUTPUT = DEEP_LEARNING_REPORTS_DIR / "deep_learning_model_comparison.csv"
SUMMARY_OUTPUT = DEEP_LEARNING_REPORTS_DIR / "deep_learning_summary.json"
FIGURE_OUTPUT = FIGURES_DIR / "deep_learning_model_comparison.png"

SCENARIO = "exclude_all_flagged"
REFERENCE_MODELS = ["xgboost", "random_forest"]
DEVICE = "mps" if torch is not None and torch.backends.mps.is_available() else "cpu"


def load_filtered_modeling_table() -> tuple[pd.DataFrame, list[str]]:
    modeling = pd.read_csv(MODELING_INPUT, parse_dates=[DATE_COLUMN])
    flags = pd.read_csv(FLAGS_INPUT, parse_dates=[DATE_COLUMN])
    flagged_dates = set(flags[DATE_COLUMN])
    filtered = modeling.loc[~modeling[DATE_COLUMN].isin(flagged_dates)].copy()
    filtered = filtered.sort_values(DATE_COLUMN).reset_index(drop=True)
    return filtered, sorted(value.date().isoformat() for value in flagged_dates)


def mlp_specs() -> dict[str, dict]:
    return {
        "mlp_small": {
            "hidden_layer_sizes": (32,),
            "alpha": 0.01,
            "learning_rate_init": 0.001,
        },
        "mlp_medium": {
            "hidden_layer_sizes": (64, 32),
            "alpha": 0.01,
            "learning_rate_init": 0.001,
        },
        "mlp_regularized": {
            "hidden_layer_sizes": (64, 32),
            "alpha": 0.05,
            "learning_rate_init": 0.0007,
        },
    }


def sequence_specs() -> dict[str, dict]:
    return {
        "lstm_14d_small": {
            "kind": "lstm",
            "lookback": 14,
            "hidden_size": 32,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.001,
            "weight_decay": 0.01,
            "epochs": 650,
            "patience": 90,
        },
        "lstm_28d_regularized": {
            "kind": "lstm",
            "lookback": 28,
            "hidden_size": 48,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.0008,
            "weight_decay": 0.03,
            "epochs": 750,
            "patience": 100,
        },
        "gru_14d_small": {
            "kind": "gru",
            "lookback": 14,
            "hidden_size": 32,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.001,
            "weight_decay": 0.01,
            "epochs": 650,
            "patience": 90,
        },
        "gru_28d_regularized": {
            "kind": "gru",
            "lookback": 28,
            "hidden_size": 48,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.0008,
            "weight_decay": 0.03,
            "epochs": 750,
            "patience": 100,
        },
        "gru_56d_wide": {
            "kind": "gru",
            "lookback": 56,
            "hidden_size": 64,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.0006,
            "weight_decay": 0.05,
            "epochs": 850,
            "patience": 110,
        },
        "gru_42d_balanced": {
            "kind": "gru",
            "lookback": 42,
            "hidden_size": 64,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.0007,
            "weight_decay": 0.04,
            "epochs": 850,
            "patience": 110,
        },
        "gru_56d_more_regularized": {
            "kind": "gru",
            "lookback": 56,
            "hidden_size": 64,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.0005,
            "weight_decay": 0.10,
            "epochs": 900,
            "patience": 120,
        },
        "gru_84d_compact": {
            "kind": "gru",
            "lookback": 84,
            "hidden_size": 48,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.0005,
            "weight_decay": 0.08,
            "epochs": 900,
            "patience": 120,
        },
        "lstm_56d_regularized": {
            "kind": "lstm",
            "lookback": 56,
            "hidden_size": 64,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.0005,
            "weight_decay": 0.08,
            "epochs": 900,
            "patience": 120,
        },
        "transformer_28d_small": {
            "kind": "transformer",
            "lookback": 28,
            "hidden_size": 48,
            "num_layers": 1,
            "dropout": 0.10,
            "learning_rate": 0.0005,
            "weight_decay": 0.05,
            "epochs": 850,
            "patience": 110,
            "num_heads": 4,
        },
        "transformer_56d_regularized": {
            "kind": "transformer",
            "lookback": 56,
            "hidden_size": 64,
            "num_layers": 1,
            "dropout": 0.15,
            "learning_rate": 0.0004,
            "weight_decay": 0.08,
            "epochs": 900,
            "patience": 120,
            "num_heads": 4,
        },
    }


def build_mlp_model(spec: dict) -> TransformedTargetRegressor:
    regressor = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                MLPRegressor(
                    hidden_layer_sizes=spec["hidden_layer_sizes"],
                    activation="relu",
                    solver="adam",
                    alpha=spec["alpha"],
                    learning_rate_init=spec["learning_rate_init"],
                    max_iter=2500,
                    n_iter_no_change=80,
                    tol=1e-5,
                    random_state=561,
                ),
            ),
        ]
    )
    return TransformedTargetRegressor(regressor=regressor, transformer=StandardScaler())


def train_mlp_models(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    metrics: list[dict] = []
    predictions = pd.DataFrame()
    train_model_frame = train.dropna(subset=[TARGET_COLUMN]).copy()
    split_frames = {"validation": validation, "test": test}

    for model_name, spec in mlp_specs().items():
        model = build_mlp_model(spec)
        model.fit(train_model_frame[feature_columns], train_model_frame[TARGET_COLUMN])
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
    best_validation_model = (
        metrics_frame.loc[metrics_frame["split"].eq("validation")]
        .sort_values(["mae", "rmse"])
        .iloc[0]["model"]
    )
    return predictions, metrics_frame, str(best_validation_model)


class SequenceRegressor(nn.Module):
    def __init__(
        self,
        input_size: int,
        kind: str,
        hidden_size: int,
        num_layers: int,
        dropout: float,
        num_heads: int = 4,
        lookback: int = 1,
    ) -> None:
        super().__init__()
        self.kind = kind
        if kind in {"lstm", "gru"}:
            recurrent_layer = nn.LSTM if kind == "lstm" else nn.GRU
            self.input_projection = None
            self.position_embedding = None
            self.sequence_layer = recurrent_layer(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0.0,
            )
        elif kind == "transformer":
            self.input_projection = nn.Linear(input_size, hidden_size)
            self.position_embedding = nn.Parameter(torch.zeros(1, lookback, hidden_size))
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_size,
                nhead=num_heads,
                dim_feedforward=hidden_size * 2,
                dropout=dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.sequence_layer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        else:
            raise ValueError(f"Unsupported sequence model kind: {kind}")
        self.head = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(32, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        if self.kind == "transformer":
            projected = self.input_projection(features)
            positioned = projected + self.position_embedding[:, : projected.shape[1], :]
            output = self.sequence_layer(positioned)
        else:
            output, _ = self.sequence_layer(features)
        return self.head(output[:, -1, :]).squeeze(-1)


def scaled_arrays(
    modeling: pd.DataFrame,
    train: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[np.ndarray, np.ndarray, SimpleImputer, StandardScaler, StandardScaler]:
    imputer = SimpleImputer(strategy="median")
    feature_scaler = StandardScaler()
    target_scaler = StandardScaler()

    train_features = train[feature_columns]
    imputer.fit(train_features)
    feature_scaler.fit(imputer.transform(train_features))
    target_scaler.fit(train[[TARGET_COLUMN]])

    all_features = feature_scaler.transform(imputer.transform(modeling[feature_columns])).astype(np.float32)
    all_targets = target_scaler.transform(modeling[[TARGET_COLUMN]]).reshape(-1).astype(np.float32)
    return all_features, all_targets, imputer, feature_scaler, target_scaler


def sequence_tensors(
    features: np.ndarray,
    targets: np.ndarray,
    split_frame: pd.DataFrame,
    lookback: int,
) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
    sequences = []
    labels = []
    endpoint_indices = []
    for index in split_frame.index:
        if index < lookback - 1:
            continue
        sequences.append(features[index - lookback + 1 : index + 1])
        labels.append(targets[index])
        endpoint_indices.append(index)

    if not sequences:
        raise ValueError(f"No sequence rows available for lookback={lookback}")

    return (
        torch.tensor(np.stack(sequences), dtype=torch.float32),
        torch.tensor(np.asarray(labels), dtype=torch.float32),
        endpoint_indices,
    )


def train_one_sequence_model(
    model_name: str,
    spec: dict,
    features: np.ndarray,
    targets: np.ndarray,
    target_scaler: StandardScaler,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[dict, dict[str, np.ndarray], dict[str, list[int]]]:
    if torch is None:
        raise RuntimeError("PyTorch is required for LSTM/GRU sequence models.")

    torch.manual_seed(561)
    np.random.seed(561)

    lookback = spec["lookback"]
    x_train, y_train, train_indices = sequence_tensors(features, targets, train, lookback)
    x_validation, y_validation, validation_indices = sequence_tensors(features, targets, validation, lookback)
    x_test, y_test, test_indices = sequence_tensors(features, targets, test, lookback)

    model = SequenceRegressor(
        input_size=features.shape[1],
        kind=spec["kind"],
        hidden_size=spec["hidden_size"],
        num_layers=spec["num_layers"],
        dropout=spec["dropout"],
        num_heads=spec.get("num_heads", 4),
        lookback=lookback,
    ).to(DEVICE)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=spec["learning_rate"],
        weight_decay=spec["weight_decay"],
    )
    loss_function = nn.SmoothL1Loss()
    train_loader = DataLoader(
        TensorDataset(x_train, y_train),
        batch_size=min(64, len(x_train)),
        shuffle=True,
        generator=torch.Generator().manual_seed(561),
    )

    best_state = None
    best_validation_loss = float("inf")
    best_epoch = 0
    patience_remaining = spec["patience"]

    x_validation_device = x_validation.to(DEVICE)
    y_validation_device = y_validation.to(DEVICE)
    for epoch in range(1, spec["epochs"] + 1):
        model.train()
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(DEVICE)
            batch_y = batch_y.to(DEVICE)
            optimizer.zero_grad()
            loss = loss_function(model(batch_x), batch_y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            validation_loss = loss_function(model(x_validation_device), y_validation_device).item()
        if validation_loss + 1e-5 < best_validation_loss:
            best_validation_loss = validation_loss
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            patience_remaining = spec["patience"]
        else:
            patience_remaining -= 1
            if patience_remaining <= 0:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    predictions = {}
    endpoint_indices = {
        "validation": validation_indices,
        "test": test_indices,
    }
    for split_name, x_split in (("validation", x_validation), ("test", x_test)):
        model.eval()
        with torch.no_grad():
            scaled_prediction = model(x_split.to(DEVICE)).cpu().numpy().reshape(-1, 1)
        predictions[split_name] = target_scaler.inverse_transform(scaled_prediction).reshape(-1)

    metadata = {
        "model": model_name,
        "kind": spec["kind"],
        "lookback": lookback,
        "hidden_size": spec["hidden_size"],
        "num_layers": spec["num_layers"],
        "dropout": spec["dropout"],
        "learning_rate": spec["learning_rate"],
        "weight_decay": spec["weight_decay"],
        "num_heads": spec.get("num_heads"),
        "best_epoch": best_epoch,
        "best_validation_loss_scaled": best_validation_loss,
        "train_sequence_rows": len(train_indices),
    }
    return metadata, predictions, endpoint_indices


def add_sequence_prediction(
    predictions: pd.DataFrame,
    metrics: list[dict],
    split_name: str,
    model_name: str,
    modeling: pd.DataFrame,
    endpoint_indices: list[int],
    predicted: np.ndarray,
) -> pd.DataFrame:
    split_frame = modeling.loc[endpoint_indices]
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


def train_sequence_models(
    modeling: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, str, list[dict]]:
    if torch is None:
        return pd.DataFrame(), pd.DataFrame(), "", []

    features, targets, _, _, target_scaler = scaled_arrays(modeling, train, feature_columns)
    metrics: list[dict] = []
    predictions = pd.DataFrame()
    model_metadata = []

    for model_name, spec in sequence_specs().items():
        metadata, model_predictions, endpoint_indices = train_one_sequence_model(
            model_name,
            spec,
            features,
            targets,
            target_scaler,
            train,
            validation,
            test,
        )
        model_metadata.append(metadata)
        for split_name in ("validation", "test"):
            predictions = add_sequence_prediction(
                predictions,
                metrics,
                split_name,
                model_name,
                modeling,
                endpoint_indices[split_name],
                model_predictions[split_name],
            )

    metrics_frame = pd.DataFrame(metrics).sort_values(["split", "mae", "rmse"]).reset_index(drop=True)
    best_validation_model = (
        metrics_frame.loc[metrics_frame["split"].eq("validation")]
        .sort_values(["mae", "rmse"])
        .iloc[0]["model"]
    )
    return predictions, metrics_frame, str(best_validation_model), model_metadata


def build_comparison(metrics: pd.DataFrame) -> pd.DataFrame:
    baseline_metrics = pd.read_csv(SENSITIVITY_METRICS_INPUT)
    baseline_test = baseline_metrics.loc[
        baseline_metrics["scenario"].eq(SCENARIO)
        & baseline_metrics["split"].eq("test")
        & baseline_metrics["model"].isin(REFERENCE_MODELS)
    ].copy()
    baseline_test = baseline_test[
        ["scenario", "model", "split", "row_count", "mae", "rmse", "mape", "r2"]
    ]
    baseline_test["model_family"] = "tree_baseline"

    deep_test = metrics.loc[metrics["split"].eq("test")].copy()
    deep_test.insert(0, "scenario", SCENARIO)
    deep_test["model_family"] = deep_test["model"].map(
        lambda value: "sequence_neural_network" if value.startswith(("lstm_", "gru_", "transformer_")) else "neural_network"
    )

    comparison = pd.concat([baseline_test, deep_test], ignore_index=True)
    return comparison.sort_values(["mae", "rmse"]).reset_index(drop=True)


def plot_comparison(comparison: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid")
    fig, axis = plt.subplots(figsize=(9, 5))
    sns.barplot(
        data=comparison.sort_values("mae"),
        x="mae",
        y="model",
        hue="model_family",
        dodge=False,
        ax=axis,
        palette={
            "tree_baseline": "#2563eb",
            "neural_network": "#059669",
            "sequence_neural_network": "#7c3aed",
        },
    )
    axis.set_title("Exclude-All-Flagged Test MAE: Tree Models vs MLP")
    axis.set_xlabel("Mean absolute error, rooms sold")
    axis.set_ylabel("")
    axis.legend(title="")
    fig.tight_layout()
    fig.savefig(FIGURE_OUTPUT, dpi=180)
    plt.close(fig)


def build_summary(
    modeling: pd.DataFrame,
    excluded_dates: list[str],
    feature_columns: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    metrics: pd.DataFrame,
    comparison: pd.DataFrame,
    best_mlp_model: str,
    best_sequence_model: str,
    sequence_metadata: list[dict],
) -> dict:
    best_mlp_test = metrics.loc[
        metrics["split"].eq("test") & metrics["model"].eq(best_mlp_model)
    ].iloc[0].to_dict()
    best_sequence_test = None
    if best_sequence_model:
        best_sequence_test = metrics.loc[
            metrics["split"].eq("test") & metrics["model"].eq(best_sequence_model)
        ].iloc[0].to_dict()
    sequence_test_metrics = metrics.loc[
        metrics["split"].eq("test") & metrics["model"].str.startswith(("lstm_", "gru_", "transformer_"))
    ].sort_values(["mae", "rmse"])
    best_sequence_test_by_mae = sequence_test_metrics.iloc[0].to_dict() if len(sequence_test_metrics) else None
    best_overall = comparison.iloc[0].to_dict()
    return {
        "scenario": SCENARIO,
        "input_file": str(MODELING_INPUT.relative_to(REPO_ROOT)),
        "flags_file": str(FLAGS_INPUT.relative_to(REPO_ROOT)),
        "excluded_dates": excluded_dates,
        "rows_after_exclusion": int(len(modeling)),
        "target": TARGET_COLUMN,
        "feature_count": len(feature_columns),
        "splits": {
            "train": {
                "rows": int(len(train)),
                "start": train[DATE_COLUMN].min().date().isoformat(),
                "end": train[DATE_COLUMN].max().date().isoformat(),
            },
            "validation": {
                "rows": int(len(validation)),
                "start": validation[DATE_COLUMN].min().date().isoformat(),
                "end": validation[DATE_COLUMN].max().date().isoformat(),
            },
            "test": {
                "rows": int(len(test)),
                "start": test[DATE_COLUMN].min().date().isoformat(),
                "end": test[DATE_COLUMN].max().date().isoformat(),
            },
        },
        "modeling_note": (
            "The MLP uses the same tabular lag, rolling, and calendar features as the tree baselines. "
            "LSTM and GRU models use sequences of those same leakage-safe feature rows ending on each prediction date. "
            "The best neural configurations are selected by validation MAE, then reported on the held-out 2025 test set."
        ),
        "framework_note": (
            f"PyTorch is used for LSTM/GRU sequence models. Training device: {DEVICE}."
        ),
        "outputs": {
            "predictions": str(PREDICTIONS_OUTPUT.relative_to(REPO_ROOT)),
            "metrics": str(METRICS_OUTPUT.relative_to(REPO_ROOT)),
            "comparison": str(COMPARISON_OUTPUT.relative_to(REPO_ROOT)),
            "summary": str(SUMMARY_OUTPUT.relative_to(REPO_ROOT)),
            "figure": str(FIGURE_OUTPUT.relative_to(REPO_ROOT)),
        },
        "best_mlp_model_by_validation_mae": best_mlp_model,
        "best_sequence_model_by_validation_mae": best_sequence_model,
        "best_mlp_test_metrics": best_mlp_test,
        "best_sequence_test_metrics_for_validation_selected_model": best_sequence_test,
        "best_sequence_test_metrics_by_mae": best_sequence_test_by_mae,
        "best_overall_test_model_in_comparison": best_overall,
        "sequence_model_metadata": sequence_metadata,
        "all_deep_learning_metrics": metrics.to_dict(orient="records"),
        "comparison": comparison.to_dict(orient="records"),
    }


def main() -> None:
    DEEP_LEARNING_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    modeling, excluded_dates = load_filtered_modeling_table()
    feature_columns = select_feature_columns(modeling)
    train, validation, test = chronological_split(modeling)

    mlp_predictions, mlp_metrics, best_mlp_model = train_mlp_models(train, validation, test, feature_columns)
    sequence_predictions, sequence_metrics, best_sequence_model, sequence_metadata = train_sequence_models(
        modeling,
        train,
        validation,
        test,
        feature_columns,
    )
    predictions = pd.concat([mlp_predictions, sequence_predictions], ignore_index=True)
    metrics = pd.concat([mlp_metrics, sequence_metrics], ignore_index=True)
    metrics = metrics.sort_values(["split", "mae", "rmse"]).reset_index(drop=True)
    comparison = build_comparison(metrics)
    summary = build_summary(
        modeling,
        excluded_dates,
        feature_columns,
        train,
        validation,
        test,
        metrics,
        comparison,
        best_mlp_model,
        best_sequence_model,
        sequence_metadata,
    )

    predictions.insert(0, "scenario", SCENARIO)
    predictions.to_csv(PREDICTIONS_OUTPUT, index=False, date_format="%Y-%m-%d")
    metrics.to_csv(METRICS_OUTPUT, index=False)
    comparison.to_csv(COMPARISON_OUTPUT, index=False)
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot_comparison(comparison)

    mlp_test = summary["best_mlp_test_metrics"]
    sequence_test = summary["best_sequence_test_metrics_for_validation_selected_model"]
    best_sequence_test_by_mae = summary["best_sequence_test_metrics_by_mae"]
    best_overall = summary["best_overall_test_model_in_comparison"]
    print(f"Wrote {PREDICTIONS_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {METRICS_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {COMPARISON_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {SUMMARY_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {FIGURE_OUTPUT.relative_to(REPO_ROOT)}")
    print(
        "Best MLP test metrics: "
        f"{best_mlp_model} MAE={mlp_test['mae']:.3f}, "
        f"RMSE={mlp_test['rmse']:.3f}, R2={mlp_test['r2']:.3f}"
    )
    if sequence_test:
        print(
            "Validation-selected sequence test metrics: "
            f"{best_sequence_model} MAE={sequence_test['mae']:.3f}, "
            f"RMSE={sequence_test['rmse']:.3f}, R2={sequence_test['r2']:.3f}"
        )
    if best_sequence_test_by_mae:
        print(
            "Best sequence test metrics by MAE: "
            f"{best_sequence_test_by_mae['model']} MAE={best_sequence_test_by_mae['mae']:.3f}, "
            f"RMSE={best_sequence_test_by_mae['rmse']:.3f}, R2={best_sequence_test_by_mae['r2']:.3f}"
        )
    print(
        "Best overall comparison model: "
        f"{best_overall['model']} MAE={best_overall['mae']:.3f}"
    )


if __name__ == "__main__":
    main()
