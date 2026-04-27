from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
MODELING_INPUT = REPO_ROOT / "processed_data" / "modeling_daily.csv"
REPORTS_DIR = REPO_ROOT / "reports"
AUDIT_REPORTS_DIR = REPORTS_DIR / "audit"
FLAGS_OUTPUT = AUDIT_REPORTS_DIR / "data_quality_flags.csv"
SUMMARY_OUTPUT = AUDIT_REPORTS_DIR / "data_quality_flags_summary.json"


def build_flags(modeling: pd.DataFrame) -> pd.DataFrame:
    flagged = []
    base_columns = [
        "business_date",
        "property_total_rooms",
        "target_rooms_sold",
        "block_occupancy_rate_reported",
        "block_on_market_rooms",
        "block_out_of_order_rooms",
        "block_room_revenue_net",
        "block_adr_net",
        "block_source_file",
    ]

    for row in modeling.loc[modeling["target_rooms_sold"] > modeling["property_total_rooms"], base_columns].itertuples(index=False):
        record = row._asdict()
        record["flag_type"] = "rooms_sold_gt_property_total"
        record["review_note"] = (
            "Rooms sold exceeds inferred 60-room property capacity. Treat as a raw report anomaly "
            "or over-capacity operational edge case until verified."
        )
        flagged.append(record)

    for row in modeling.loc[modeling["target_rooms_sold"] == 0, base_columns].itertuples(index=False):
        record = row._asdict()
        record["flag_type"] = "zero_rooms_sold"
        if record["block_room_revenue_net"] != 0:
            record["review_note"] = (
                "Zero rooms sold but nonzero net room revenue; likely revenue adjustment, late posting, "
                "or report anomaly."
            )
        elif record["block_out_of_order_rooms"] > 0:
            record["review_note"] = "Zero rooms sold with out-of-order rooms present; possible partial closure or outage period."
        else:
            record["review_note"] = "Zero rooms sold and zero revenue; possible closure, outage, or raw report anomaly."
        flagged.append(record)

    flags = pd.DataFrame(flagged)
    if not flags.empty:
        flags = flags[
            [
                "flag_type",
                "business_date",
                "property_total_rooms",
                "target_rooms_sold",
                "block_occupancy_rate_reported",
                "block_on_market_rooms",
                "block_out_of_order_rooms",
                "block_room_revenue_net",
                "block_adr_net",
                "block_source_file",
                "review_note",
            ]
        ].sort_values(["business_date", "flag_type"])
    return flags


def main() -> None:
    AUDIT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    modeling = pd.read_csv(MODELING_INPUT, parse_dates=["business_date"])
    flags = build_flags(modeling)
    flags.to_csv(FLAGS_OUTPUT, index=False, date_format="%Y-%m-%d")

    summary = {
        "input_file": str(MODELING_INPUT.relative_to(REPO_ROOT)),
        "output_file": str(FLAGS_OUTPUT.relative_to(REPO_ROOT)),
        "flagged_rows": int(len(flags)),
        "flag_counts": flags["flag_type"].value_counts().to_dict() if not flags.empty else {},
        "notes": [
            "Flags are review records, not automatic corrections.",
            "No modeling table values are changed by this audit.",
            "The flagged rows should be resolved or documented before final report metrics are treated as final.",
        ],
    }
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {FLAGS_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {SUMMARY_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Flagged rows: {summary['flagged_rows']}")
    print(f"Flag counts: {summary['flag_counts']}")


if __name__ == "__main__":
    main()
