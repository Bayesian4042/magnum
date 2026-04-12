"""
pipeline/validate.py
--------------------
Compare computed production against the client's "2026" sheet baseline.

Shows two comparisons:
  1. Raw-only supply (SAP + RR) vs baseline — reveals where data gaps are
  2. Hybrid supply (raw + baseline fallback) vs baseline — confirms pipeline output matches

Usage:
  uv run python -m pipeline.validate
"""

import pandas as pd

from pipeline import extract, transform, consolidate


def _compare(computed: pd.DataFrame, baseline: pd.DataFrame, label: str) -> int:
    """Print a comparison report. Returns number of matching technologies."""
    comparison = computed.merge(baseline, on=["main_tech", "month"], how="outer").fillna(0)
    comparison["diff"] = comparison["computed_cases"] - comparison["baseline_cases"]
    comparison["pct_diff"] = comparison.apply(
        lambda r: (r["diff"] / r["baseline_cases"] * 100) if r["baseline_cases"] != 0 else 0,
        axis=1,
    )
    comparison = comparison.sort_values(["main_tech", "month"]).reset_index(drop=True)

    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")

    techs = sorted(comparison["main_tech"].unique())
    n_match = 0
    for tech in techs:
        tech_rows = comparison[comparison["main_tech"] == tech]
        total_computed = tech_rows["computed_cases"].sum()
        total_baseline = tech_rows["baseline_cases"].sum()
        total_diff = total_computed - total_baseline
        pct = (total_diff / total_baseline * 100) if total_baseline != 0 else 0
        match = abs(pct) < 1.0
        if match:
            n_match += 1
        tag = "MATCH" if match else "MISMATCH"
        print(f"  {tech:<20}  computed={total_computed:>12,.0f}  baseline={total_baseline:>12,.0f}"
              f"  diff={total_diff:>+12,.0f}  ({pct:>+.1f}%)  [{tag}]")

    print(f"\n  Summary: {n_match}/{len(techs)} technologies within 1% of baseline\n")
    return n_match


def validate_against_ptg() -> None:
    """Run both raw-only and hybrid comparisons."""

    # --- Extract ---
    print("Loading data...")
    conv_table = extract.load_conversion_table()
    attain_table = extract.load_attainment_table()
    tmicc = extract.load_actual_supply_tmicc()
    cm = extract.load_actual_supply_cm()
    rr = extract.load_rr_supply()
    manual_supply = extract.load_manual_supply_adjustments()
    ptg_baseline = extract.load_ptg_2026_baseline()
    inventory = extract.load_actual_inventory()
    demand = extract.load_demand()

    # --- Transform ---
    supply_monthly = transform.prepare_supply(
        tmicc, cm, rr, conv_table, attain_table,
        manual_df=manual_supply,
    )
    demand_monthly = transform.prepare_demand(demand, conv_table)
    inventory_monthly = transform.prepare_inventory(inventory, conv_table)

    # --- Baseline aggregated ---
    baseline = ptg_baseline.groupby(
        ["main_tech", "month"], as_index=False
    ).agg(baseline_cases=("cases_post_attain", "sum"))
    baseline = baseline[baseline["month"].str.startswith("2026")]

    # --- Comparison 1: Raw-only ---
    raw_computed = supply_monthly.groupby(
        ["main_tech", "month"], as_index=False
    ).agg(computed_cases=("cases_post_attain", "sum"))
    raw_computed = raw_computed[raw_computed["month"].str.startswith("2026")]

    _compare(raw_computed, baseline, "RAW INPUTS ONLY (SAP + RR) vs Baseline")

    # --- Comparison 2: Hybrid (what the pipeline actually produces) ---
    master = consolidate.build_master_view(
        supply_monthly, demand_monthly, inventory_monthly,
        ptg_2026_baseline=ptg_baseline,
    )
    hybrid_computed = master[["main_tech", "month", "supply_cases"]].rename(
        columns={"supply_cases": "computed_cases"}
    )

    _compare(hybrid_computed, baseline, "HYBRID (raw + baseline fallback) vs Baseline")


if __name__ == "__main__":
    validate_against_ptg()
