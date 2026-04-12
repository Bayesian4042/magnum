"""
pipeline/transform.py
---------------------
Unit conversions and normalization applied after extraction.

Key transformations:
  1. Join supply/demand/inventory to the conversion table on DU
  2. Apply tech normalization (handle TALENTI vs Talenti, etc.)
  3. Apply attainment factor to raw supply cases
  4. Calculate: cases -> litons, cases -> pallets
"""

import pandas as pd
import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_config(filename: str) -> dict:
    with open(CONFIG_DIR / filename) as f:
        return yaml.safe_load(f)


def normalize_tech(df: pd.DataFrame, tech_col: str = "main_tech") -> pd.DataFrame:
    """Normalize technology names to canonical form using config mapping."""
    config = load_config("conversion_tables.yaml")
    norm_map = config.get("tech_normalization", {})
    df = df.copy()
    df[tech_col] = df[tech_col].replace(norm_map)
    return df


def normalize_site(df: pd.DataFrame, site_col: str = "site") -> pd.DataFrame:
    """Add a human-readable site_name column."""
    config = load_config("conversion_tables.yaml")
    site_names = config.get("site_names", {})
    df = df.copy()
    df[site_col] = df[site_col].astype(str)
    df["site_name"] = df[site_col].map(lambda s: site_names.get(int(s), s) if s.isdigit() else site_names.get(s, s))
    return df


def join_conversion_table(df: pd.DataFrame, conv_table: pd.DataFrame) -> pd.DataFrame:
    """
    Join the conversion table onto a supply/demand DataFrame.
    Adds: sub_tech, main_tech, litons, per_pallet (from conv table).
    If sub_tech/main_tech already exist (from demand file), preserve them.
    """
    df = df.copy()
    existing_tech = "main_tech" in df.columns and df["main_tech"].notna().any()

    merge_cols = ["du", "litons", "per_pallet"]
    if not existing_tech:
        merge_cols += ["sub_tech", "main_tech"]

    conv_subset = conv_table[merge_cols].copy()
    df = df.merge(conv_subset, on="du", how="left", suffixes=("", "_conv"))

    # Fill in tech from conv table if missing in source
    for col in ["sub_tech", "main_tech"]:
        conv_col = f"{col}_conv"
        if conv_col in df.columns:
            df[col] = df[col].fillna(df[conv_col])
            df = df.drop(columns=[conv_col])

    unmatched = df["litons"].isna().sum()
    if unmatched > 0:
        print(f"[transform] Warning: {unmatched} rows could not be matched to conversion table (unknown DU)")

    return df


def apply_attainment(
    df: pd.DataFrame,
    attain_table: pd.DataFrame,
    attainment_overrides: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Apply attainment % to supply cases.
    - Forecast rows (source_type == "RR"): cases_post_attain = cases * attain_pct
    - Actual rows (TMICC, CM, Import, Manual): cases_post_attain = cases (no adjustment)
    Joins on main_tech; falls back to default attainment if tech not found.

    attainment_overrides: optional {main_tech: pct} dict from dashboard
    sliders that patches the attain_map before applying.
    """
    config = load_config("manual_adjustments.yaml")
    default_attain = config["attainment_factors"].get("default", 0.96)

    df = df.copy()
    attain_map = dict(zip(attain_table["main_tech"], attain_table["attain_pct"]))
    if attainment_overrides:
        attain_map.update(attainment_overrides)

    df["attain_pct"] = df["main_tech"].map(lambda t: attain_map.get(t, default_attain)).fillna(default_attain)

    is_forecast = df["source_type"] == "RR"
    df["cases_post_attain"] = df["cases"].astype(float)
    df.loc[is_forecast, "cases_post_attain"] = df.loc[is_forecast, "cases"] * df.loc[is_forecast, "attain_pct"]

    n_actual = (~is_forecast).sum()
    n_forecast = is_forecast.sum()
    print(f"[transform] Attainment: {n_actual} actual rows (pass-through), {n_forecast} forecast rows (attainment applied)")
    return df


def convert_units(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate litons and pallets from cases using conversion table values.
    Requires columns: cases_post_attain (or cases), litons, per_pallet.
    Adds: litons_post_attain, pallets_post_attain
    """
    df = df.copy()
    case_col = "cases_post_attain" if "cases_post_attain" in df.columns else "cases"

    df["litons_post_attain"] = df[case_col] * df["litons"].fillna(0)
    df["pallets_post_attain"] = df.apply(
        lambda r: r[case_col] / r["per_pallet"] if pd.notna(r["per_pallet"]) and r["per_pallet"] > 0 else 0,
        axis=1,
    )
    return df


def aggregate_to_monthly(df: pd.DataFrame, group_cols: list[str], value_cols: list[str]) -> pd.DataFrame:
    """
    Aggregate weekly/daily data to monthly buckets.
    group_cols: e.g. ["du", "site", "month", "main_tech"]
    value_cols: e.g. ["cases", "litons_post_attain", "pallets_post_attain"]
    """
    agg = {col: "sum" for col in value_cols}
    result = df.groupby(group_cols, as_index=False).agg(agg)
    return result


def _apply_actual_forecast_cutover(
    actuals_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    cutover_month: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Prevent double-counting by splitting actuals and forecasts at a cutover month.
    - Actuals: keep rows where month <= cutover_month
    - Forecasts: keep rows where month > cutover_month

    If cutover_month is None, auto-detect as the latest month in actuals.
    """
    if cutover_month is None:
        if len(actuals_df) > 0:
            cutover_month = actuals_df["month"].max()
        else:
            return actuals_df, forecast_df

    actuals_filtered = actuals_df[actuals_df["month"] <= cutover_month].copy()
    forecast_filtered = forecast_df[forecast_df["month"] > cutover_month].copy()

    n_act_dropped = len(actuals_df) - len(actuals_filtered)
    n_fc_dropped = len(forecast_df) - len(forecast_filtered)
    print(f"[transform] Cutover at {cutover_month}: "
          f"actuals kept={len(actuals_filtered)} (dropped {n_act_dropped}), "
          f"forecast kept={len(forecast_filtered)} (dropped {n_fc_dropped})")
    return actuals_filtered, forecast_filtered


def prepare_supply(
    tmicc_df: pd.DataFrame,
    cm_df: pd.DataFrame,
    rr_df: pd.DataFrame,
    conv_table: pd.DataFrame,
    attain_table: pd.DataFrame,
    manual_df: pd.DataFrame | None = None,
    cutover_month: str | None = None,
    attainment_overrides: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Full supply transformation pipeline:
      1. Apply actual/forecast cutover to prevent double-counting
      2. Combine TMICC + CM actuals + RR forward supply + manual adjustments
      3. Join conversion table
      4. Apply attainment (forecast only; actuals pass through)
      5. Convert to litons + pallets
      6. Aggregate to monthly
    Returns tidy monthly supply DataFrame.
    """
    common_cols = ["du", "site", "month", "cases", "description", "source_type"]

    actuals = pd.concat([
        tmicc_df[common_cols],
        cm_df[common_cols],
    ], ignore_index=True)

    forecast = rr_df[common_cols].copy()

    actuals, forecast = _apply_actual_forecast_cutover(actuals, forecast, cutover_month)

    parts = [actuals, forecast]
    if manual_df is not None and len(manual_df) > 0:
        parts.append(manual_df[common_cols])
        print(f"[transform] Including {len(manual_df)} manual supply adjustment rows")

    supply = pd.concat(parts, ignore_index=True)

    supply = join_conversion_table(supply, conv_table)
    supply = normalize_tech(supply)
    supply = normalize_site(supply)
    supply = apply_attainment(supply, attain_table, attainment_overrides=attainment_overrides)
    supply = convert_units(supply)

    monthly = aggregate_to_monthly(
        supply,
        group_cols=["du", "site", "site_name", "month", "main_tech", "sub_tech", "source_type"],
        value_cols=["cases", "cases_post_attain", "litons_post_attain", "pallets_post_attain"],
    )
    print(f"[transform] Supply prepared: {len(monthly)} monthly rows, {monthly['du'].nunique()} DUs")
    return monthly


def prepare_demand(demand_df: pd.DataFrame, conv_table: pd.DataFrame) -> pd.DataFrame:
    """
    Demand transformation pipeline:
      1. Join conversion table for litons/per_pallet (demand file has its own tech already)
      2. Convert to litons + pallets
    Returns tidy monthly demand DataFrame.
    """
    demand = join_conversion_table(demand_df, conv_table)
    demand = normalize_tech(demand)
    demand = convert_units(demand)
    # For demand, no attainment factor; cases = cases_post_attain
    demand["cases_post_attain"] = demand["cases"]

    monthly = aggregate_to_monthly(
        demand,
        group_cols=["du", "month", "main_tech", "sub_tech"],
        value_cols=["cases", "litons_post_attain", "pallets_post_attain"],
    )
    print(f"[transform] Demand prepared: {len(monthly)} monthly rows")
    return monthly


def prepare_inventory(inv_df: pd.DataFrame, conv_table: pd.DataFrame) -> pd.DataFrame:
    """
    Inventory transformation pipeline:
      1. Join conversion table for litons
      2. Calculate inventory litons
    Returns tidy inventory DataFrame aggregated by tech + month.
    """
    inv = inv_df.copy()
    inv = inv.rename(columns={"tech": "main_tech"})
    inv = join_conversion_table(inv, conv_table)
    inv = normalize_tech(inv)

    # Calculate inventory litons using conv table litons
    inv["inv_litons"] = inv["cases"] * inv["litons"].fillna(0)
    inv["inv_pallets"] = inv.apply(
        lambda r: r["cases"] / r["per_pallet"] if pd.notna(r["per_pallet"]) and r["per_pallet"] > 0 else r.get("pallets", 0),
        axis=1,
    )

    monthly = aggregate_to_monthly(
        inv,
        group_cols=["du", "site", "month", "main_tech"],
        value_cols=["cases", "inv_litons", "inv_pallets"],
    )
    print(f"[transform] Inventory prepared: {len(monthly)} monthly rows")
    return monthly
