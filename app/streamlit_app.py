"""Streamlit demo UI for the CSC 561 hotel demand & pricing project.

Loads the real per-model prediction artifacts produced by the training
pipeline and runs the real pricing module live for the chosen scenario.
No placeholders: every number shown comes from artifacts in ``reports/``
or from calling ``src.pricing.build_pricing_recommendations``.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pricing.build_pricing_recommendations import (  # noqa: E402
    build_recommendations,
    simulation_summary,
)
from src.models.predict import (  # noqa: E402
    list_persisted_models,
    predict_with_pricing,
)

REPORTS = REPO_ROOT / "reports"
BASELINE_METRICS = REPORTS / "baselines" / "baseline_metrics.csv"
BASELINE_PREDICTIONS = REPORTS / "baselines" / "baseline_predictions.csv"
DL_METRICS = REPORTS / "deep_learning" / "deep_learning_metrics.csv"
DL_PREDICTIONS = REPORTS / "deep_learning" / "deep_learning_predictions.csv"
SCENARIO_COMPARISON = REPORTS / "pricing" / "pricing_scenario_comparison.csv"
PRICING_SUMMARY = REPORTS / "pricing" / "pricing_recommendations_summary.json"
FINAL_PDF = REPORTS / "final" / "final_report_ieee.pdf"

DL_SCENARIO_PRIMARY = "exclude_all_flagged"


@st.cache_data
def load_baseline_metrics() -> pd.DataFrame:
    df = pd.read_csv(BASELINE_METRICS)
    df["family"] = "baseline"
    return df


@st.cache_data
def load_dl_metrics() -> pd.DataFrame:
    df = pd.read_csv(DL_METRICS)
    df["family"] = "deep_learning"
    return df


@st.cache_data
def load_baseline_predictions() -> pd.DataFrame:
    return pd.read_csv(BASELINE_PREDICTIONS, parse_dates=["business_date"])


@st.cache_data
def load_dl_predictions() -> pd.DataFrame:
    df = pd.read_csv(DL_PREDICTIONS, parse_dates=["business_date"])
    return df.loc[df["scenario"].eq(DL_SCENARIO_PRIMARY)].drop(columns=["scenario"])


@st.cache_data
def load_pricing_recommendations(scenario: str):
    recs, summary = build_recommendations(scenario)
    return recs, summary


def model_predictions(model: str, family: str) -> pd.DataFrame:
    if family == "baseline":
        df = load_baseline_predictions()
    else:
        df = load_dl_predictions()
    return df.loc[df["model"].eq(model)].sort_values("business_date").reset_index(drop=True)


def fmt_money(x: float) -> str:
    return f"${x:,.2f}"


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="Hotel Demand & Pricing â€” CSC 561",
    page_icon=None,
    layout="wide",
)

st.title("Hotel Demand Forecasting & Dynamic Pricing")
st.caption(
    "CSC 561 Final Project â€” Jack DeMarinis. "
    "Real predictions and pricing artifacts from the trained pipeline "
    "(2023â€“2025 daily property data, chronological 2025 hold-out)."
)

baseline_metrics = load_baseline_metrics()
dl_metrics = load_dl_metrics()
all_metrics = pd.concat([baseline_metrics, dl_metrics], ignore_index=True)
test_metrics = all_metrics.loc[all_metrics["split"].eq("test")].copy()

tab_overview, tab_models, tab_pricing, tab_live = st.tabs(
    [
        "Overview",
        "Forecast model comparison",
        "Pricing recommendations",
        "Live inference + pricing",
    ]
)

# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
with tab_overview:
    st.subheader("What this project does")
    st.markdown(
        """
- Cleans real reservation, room-sales, and forecast exports (2023â€“2025) into
  a 1,096-row daily modeling table (209 features).
- Trains classical baselines (Ridge, Random Forest, XGBoost, naive / rolling
  / seasonal references) and deep sequence models (MLP, LSTM, GRU,
  Transformer) on a chronological split, evaluating on calendar-year 2025.
- Wraps the best forecast (XGBoost) in a bounded ADR pricing rule with
  aggressive and conservative demand-band variants.

This UI loads each model's actual saved 2025 predictions and runs the
pricing module live. Nothing on this page is hard-coded.
        """.strip()
    )

    test_summary = (
        test_metrics.sort_values("mae")
        .loc[:, ["family", "model", "row_count", "mae", "rmse", "mape", "r2"]]
        .reset_index(drop=True)
    )
    st.markdown("**All trained models â€” 2025 test metrics (sorted by MAE)**")
    st.dataframe(
        test_summary.style.format(
            {"mae": "{:.3f}", "rmse": "{:.3f}", "mape": "{:.3f}", "r2": "{:.3f}"}
        ),
        width="stretch",
        hide_index=True,
    )

    if SCENARIO_COMPARISON.exists():
        st.markdown("**Pricing scenario comparison (saved artifact)**")
        st.dataframe(
            pd.read_csv(SCENARIO_COMPARISON), width="stretch", hide_index=True
        )

    if FINAL_PDF.exists():
        st.caption(f"Full IEEE write-up: `{FINAL_PDF.relative_to(REPO_ROOT)}`")

# --------------------------------------------------------------------------- #
# Forecast model comparison
# --------------------------------------------------------------------------- #
with tab_models:
    st.subheader("Pick a trained model and inspect its 2025 forecasts")

    options = (
        test_metrics.assign(
            label=lambda d: d["family"] + " / " + d["model"]
            + "  (MAE " + d["mae"].round(3).astype(str) + ")"
        )
        .sort_values(["family", "mae"])
        .reset_index(drop=True)
    )
    default_idx = int(options["mae"].idxmin())
    choice = st.selectbox(
        "Model",
        options=options.index,
        index=default_idx,
        format_func=lambda i: options.loc[i, "label"],
    )
    chosen = options.loc[choice]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("MAE (rooms/day)", f"{chosen['mae']:.3f}")
    c2.metric("RMSE", f"{chosen['rmse']:.3f}")
    c3.metric("MAPE", f"{chosen['mape']:.3f}")
    c4.metric("RÂ²", f"{chosen['r2']:.3f}")

    preds = model_predictions(chosen["model"], chosen["family"])
    test_preds = preds.loc[preds["split"].eq("test")].copy()

    if test_preds.empty:
        st.warning("No saved test predictions for this model.")
    else:
        st.markdown("**Actual vs predicted rooms sold â€” 2025 test set**")
        chart_df = test_preds.set_index("business_date")[["actual", "predicted"]]
        st.line_chart(chart_df, height=320)

        st.markdown("**Daily predictions**")
        st.dataframe(
            test_preds[["business_date", "actual", "predicted", "absolute_error"]]
            .assign(
                predicted=lambda d: d["predicted"].round(2),
                absolute_error=lambda d: d["absolute_error"].round(2),
            ),
            width="stretch",
            hide_index=True,
        )

        csv_bytes = test_preds.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download these predictions (CSV)",
            data=csv_bytes,
            file_name=f"{chosen['model']}_2025_predictions.csv",
            mime="text/csv",
        )

# --------------------------------------------------------------------------- #
# Pricing recommendations
# --------------------------------------------------------------------------- #
with tab_pricing:
    st.subheader("Bounded ADR recommendations from the XGBoost forecast")
    st.caption(
        "Computed live by `src.pricing.build_pricing_recommendations."
        "build_recommendations(scenario)`. Recommended ADR is bounded to "
        "$75â€“$350 with a max Â±20% daily move from the reference ADR."
    )

    scenario = st.radio(
        "Pricing scenario",
        options=["aggressive", "conservative"],
        horizontal=True,
        help=(
            "Aggressive uses Â±4 / Â±8 / Â±12 % demand-band moves. "
            "Conservative uses Â±2 / Â±4 / Â±6 %."
        ),
    )

    with st.spinner("Running pricing module..."):
        recs, summary = load_pricing_recommendations(scenario)

    unflagged = recs.loc[recs["is_flagged_quality_row"].eq(0)]
    sim = simulation_summary(unflagged)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Test days (unflagged)", f"{sim['rows']:,}")
    c2.metric(
        "Simulated revenue Î”",
        fmt_money(sim["simulated_revenue_delta"]),
        f"{sim['simulated_revenue_delta_pct']:.2%}"
        if sim["simulated_revenue_delta_pct"] is not None
        else None,
    )
    c3.metric(
        "Avg historical ADR",
        fmt_money(sim["average_historical_adr_nonzero_actual"] or 0.0),
    )
    c4.metric(
        "Avg recommended ADR",
        fmt_money(sim["average_recommended_adr_nonzero_actual"] or 0.0),
    )

    min_date = recs["business_date"].min().date()
    max_date = recs["business_date"].max().date()
    date_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        view = recs.loc[
            (recs["business_date"].dt.date >= start)
            & (recs["business_date"].dt.date <= end)
        ].copy()
    else:
        view = recs.copy()

    show_flagged = st.checkbox("Include data-quality-flagged days", value=False)
    if not show_flagged:
        view = view.loc[view["is_flagged_quality_row"].eq(0)]

    st.markdown("**Recommended ADR vs historical ADR**")
    adr_chart = view.set_index("business_date")[["historical_adr_net", "recommended_adr"]]
    st.line_chart(adr_chart, height=300)

    st.markdown("**Forecast rooms vs actual rooms sold**")
    rooms_chart = view.set_index("business_date")[
        ["target_rooms_sold", "forecast_rooms_sold"]
    ].rename(columns={"target_rooms_sold": "actual_rooms_sold"})
    st.line_chart(rooms_chart, height=300)

    table_cols = [
        "business_date",
        "forecast_rooms_sold",
        "forecast_occupancy_rate",
        "demand_band",
        "pricing_reference_adr",
        "pricing_adjustment_rate",
        "recommended_adr",
        "historical_adr_net",
        "target_rooms_sold",
        "historical_room_revenue_net",
        "simulated_revenue_at_actual_rooms",
        "simulated_revenue_delta_at_actual_rooms",
    ]
    st.markdown("**Daily pricing recommendations**")
    st.dataframe(
        view[table_cols].assign(
            forecast_rooms_sold=lambda d: d["forecast_rooms_sold"].round(2),
            forecast_occupancy_rate=lambda d: (d["forecast_occupancy_rate"] * 100).round(1),
        ),
        width="stretch",
        hide_index=True,
    )

    st.download_button(
        f"Download {scenario} recommendations (CSV)",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name=f"pricing_recommendations_{scenario}.csv",
        mime="text/csv",
    )

    if PRICING_SUMMARY.exists():
        with st.expander("Pricing summary JSON (saved artifact)"):
            st.json(json.loads(PRICING_SUMMARY.read_text(encoding="utf-8")))

# --------------------------------------------------------------------------- #
# Live inference + pricing
# --------------------------------------------------------------------------- #
with tab_live:
    st.subheader("Score any date with persisted model weights")
    st.caption(
        "Loads the actual fitted weights from `models/` and runs them through "
        "`src.models.predict.predict_with_pricing`. Future dates use recursive "
        "lag/rolling features from the observed history, so actual outcome and "
        "historical revenue columns stay blank until those dates exist in the data."
    )

    persisted = list_persisted_models()
    if not persisted:
        st.warning(
            "No persisted models found in `models/`. Run "
            "`python -m src.models.train_baselines` and "
            "`python -m src.models.train_deep_learning` to generate weights."
        )
    else:
        modeling_df = pd.read_csv(REPO_ROOT / "processed_data" / "modeling_daily.csv",
                                   parse_dates=["business_date"])
        min_date = modeling_df["business_date"].min().date()
        max_date = modeling_df["business_date"].max().date()
        future_max_date = max_date + timedelta(days=365)
        default_start = min(max(date.today(), max_date + timedelta(days=1)), future_max_date)
        default_end = min(default_start + timedelta(days=13), future_max_date)

        labels = {
            f"{m['family']} / {m['name']}": m["name"] for m in persisted
        }
        default_label = next(
            (label for label, name in labels.items() if name == "xgboost"),
            list(labels.keys())[0],
        )
        chosen_label = st.selectbox(
            "Persisted model",
            options=list(labels.keys()),
            index=list(labels.keys()).index(default_label),
        )
        chosen_name = labels[chosen_label]

        live_scenario = st.radio(
            "Pricing scenario",
            options=["aggressive", "conservative"],
            horizontal=True,
            key="live_scenario",
        )

        live_range = st.date_input(
            "Date range to score",
            value=(default_start, default_end),
            min_value=min_date,
            max_value=future_max_date,
            key="live_range",
        )
        if isinstance(live_range, tuple) and len(live_range) == 2:
            start, end = live_range
        else:
            start = end = live_range

        run_live = st.button("Run model + pricing", type="primary")
        if run_live:
            target_dates = pd.date_range(start=start, end=end, freq="D")
            try:
                with st.spinner("Loading weights and scoring..."):
                    live_recs = predict_with_pricing(
                        chosen_name, target_dates, scenario=live_scenario
                    )
            except Exception as exc:  # noqa: BLE001 - surface any inference error to the UI
                st.error(f"{type(exc).__name__}: {exc}")
            else:
                if live_recs.empty:
                    st.warning(
                        "No rows returned. Sequence models need observed feature rows "
                        "for their lookback window; use XGBoost, Random Forest, Ridge, "
                        "or MLP for future-date scoring."
                    )
                else:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Days scored", f"{len(live_recs):,}")
                    c2.metric(
                        "Avg recommended ADR",
                        fmt_money(float(live_recs["recommended_adr"].mean())),
                    )
                    c3.metric(
                        "Avg forecast occupancy",
                        f"{(live_recs['forecast_occupancy_rate'] * 100).mean():.1f}%",
                    )
                    c4.metric(
                        "Forecast revenue",
                        fmt_money(float(live_recs["forecast_revenue_at_recommended_adr"].sum())),
                    )

                    st.markdown("**Forecast vs actual rooms sold**")
                    rooms = live_recs.set_index("business_date")[
                        ["target_rooms_sold", "forecast_rooms_sold"]
                    ].rename(columns={"target_rooms_sold": "actual_rooms_sold"})
                    st.line_chart(rooms, height=280)

                    st.markdown("**Recommended ADR vs historical ADR**")
                    adr = live_recs.set_index("business_date")[
                        ["historical_adr_net", "recommended_adr"]
                    ]
                    st.line_chart(adr, height=280)

                    st.markdown("**Daily output**")
                    st.dataframe(
                        live_recs[
                            [
                                "business_date",
                                "forecast_rooms_sold",
                                "forecast_occupancy_rate",
                                "demand_band",
                                "pricing_reference_adr",
                                "recommended_adr",
                                "historical_adr_net",
                                "target_rooms_sold",
                                "forecast_revenue_at_recommended_adr",
                                "simulated_revenue_at_actual_rooms",
                                "simulated_revenue_delta_at_actual_rooms",
                            ]
                        ].assign(
                            forecast_rooms_sold=lambda d: d["forecast_rooms_sold"].round(2),
                            forecast_occupancy_rate=lambda d: (
                                d["forecast_occupancy_rate"] * 100
                            ).round(1),
                        ),
                        width="stretch",
                        hide_index=True,
                    )

                    st.download_button(
                        f"Download {chosen_name} {live_scenario} recommendations (CSV)",
                        data=live_recs.to_csv(index=False).encode("utf-8"),
                        file_name=f"live_{chosen_name}_{live_scenario}.csv",
                        mime="text/csv",
                    )
