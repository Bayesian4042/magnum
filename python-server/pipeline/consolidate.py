"""
pipeline/consolidate.py
-----------------------
Merges supply, demand, and inventory into a single master view.

The master view is at the grain: main_tech x month
(matches the PTG output structure used by stakeholders).
"""

import pandas as pd


def build_master_view(
    supply_monthly: pd.DataFrame,
    demand_monthly: pd.DataFrame,
    inventory_monthly: pd.DataFrame,
    starting_inventory: dict | None = None,
    ptg_2026_baseline: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build the consolidated monthly S&OP view by technology.

    Hybrid approach:
      1. Compute supply from raw inputs (SAP actuals + RR forecast)
      2. If ptg_2026_baseline is provided, fill gaps where the raw-input
         path has zero/missing supply but the baseline has data.
         This covers techs/months where RR doesn't have forward plans
         and John uses rough cut capacity instead.

    Returns a DataFrame with columns:
      main_tech, month, supply_cases, supply_litons, supply_pallets,
      supply_source, demand_cases, demand_litons, demand_pallets,
      inv_cases, inv_litons, inv_pallets
    """
    computed = supply_monthly.groupby(
        ["main_tech", "month"], as_index=False
    ).agg(
        supply_cases=("cases_post_attain", "sum"),
        supply_litons=("litons_post_attain", "sum"),
        supply_pallets=("pallets_post_attain", "sum"),
    )
    computed["supply_source"] = "raw"

    if ptg_2026_baseline is not None:
        baseline = ptg_2026_baseline.groupby(
            ["main_tech", "month"], as_index=False
        ).agg(
            supply_cases=("cases_post_attain", "sum"),
            supply_litons=("litons_post_attain", "sum"),
            supply_pallets=("pallets_post_attain", "sum"),
        )
        baseline["supply_source"] = "baseline"

        merged = computed.merge(
            baseline, on=["main_tech", "month"], how="outer",
            suffixes=("_raw", "_base"),
        )

        has_raw = merged["supply_cases_raw"].fillna(0) > 0
        merged["supply_cases"] = merged["supply_cases_raw"].where(has_raw, merged["supply_cases_base"]).fillna(0)
        merged["supply_litons"] = merged["supply_litons_raw"].where(has_raw, merged["supply_litons_base"]).fillna(0)
        merged["supply_pallets"] = merged["supply_pallets_raw"].where(has_raw, merged["supply_pallets_base"]).fillna(0)
        merged["supply_source"] = merged["supply_source_raw"].where(has_raw, "baseline").fillna("baseline")

        n_raw = has_raw.sum()
        n_base = (~has_raw).sum()
        print(f"[consolidate] Hybrid supply: {n_raw} tech-months from raw inputs, {n_base} filled from baseline")

        supply_tech = merged[["main_tech", "month", "supply_cases", "supply_litons", "supply_pallets", "supply_source"]].copy()
    else:
        supply_tech = computed

    # Aggregate demand to tech + month
    demand_tech = demand_monthly.groupby(["main_tech", "month"], as_index=False).agg(
        demand_cases=("cases", "sum"),
        demand_litons=("litons_post_attain", "sum"),
        demand_pallets=("pallets_post_attain", "sum"),
    )

    # Aggregate inventory to tech + month
    inv_tech = inventory_monthly.groupby(["main_tech", "month"], as_index=False).agg(
        inv_cases=("cases", "sum"),
        inv_litons=("inv_litons", "sum"),
        inv_pallets=("inv_pallets", "sum"),
    )

    # Build full month x tech grid via outer join
    master = supply_tech.merge(demand_tech, on=["main_tech", "month"], how="outer")
    master = master.merge(inv_tech, on=["main_tech", "month"], how="outer")
    master = master.fillna(0)

    # Keep only 2026 months for the S&OP view
    master = master[master["month"].str.startswith("2026")].copy()

    # Sort by tech and month for readability
    master["month_sort"] = pd.to_datetime(master["month"], format="%Y-%m", errors="coerce")
    master = master.sort_values(["main_tech", "month_sort"]).drop(columns=["month_sort"])
    master = master.reset_index(drop=True)

    print(f"[consolidate] Master view: {len(master)} rows, {master['main_tech'].nunique()} technologies, "
          f"{master['month'].nunique()} months")
    return master


def build_site_supply_view(supply_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Build a supply summary by site + tech + month.
    Used for tonnage reporting sent to manufacturing sites.
    """
    site_view = supply_monthly.groupby(["site", "site_name", "main_tech", "month"], as_index=False).agg(
        supply_cases=("cases_post_attain", "sum"),
        supply_litons=("litons_post_attain", "sum"),
        supply_pallets=("pallets_post_attain", "sum"),
    )
    site_view["month_sort"] = pd.to_datetime(site_view["month"], format="%Y-%m", errors="coerce")
    site_view = site_view.sort_values(["site", "main_tech", "month_sort"]).drop(columns=["month_sort"])
    print(f"[consolidate] Site supply view: {len(site_view)} rows")
    return site_view


def build_sku_level_view(
    supply_monthly: pd.DataFrame,
    demand_monthly: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a DU (SKU) level supply vs demand view for detailed analysis.
    """
    supply_sku = supply_monthly.groupby(["du", "main_tech", "month"], as_index=False).agg(
        supply_cases=("cases_post_attain", "sum"),
        supply_litons=("litons_post_attain", "sum"),
    )
    demand_sku = demand_monthly.groupby(["du", "main_tech", "month"], as_index=False).agg(
        demand_cases=("cases", "sum"),
        demand_litons=("litons_post_attain", "sum"),
    )
    sku_view = supply_sku.merge(demand_sku, on=["du", "main_tech", "month"], how="outer").fillna(0)
    sku_view["net_cases"] = sku_view["supply_cases"] - sku_view["demand_cases"]
    sku_view["month_sort"] = pd.to_datetime(sku_view["month"], format="%Y-%m", errors="coerce")
    sku_view = sku_view.sort_values(["du", "month_sort"]).drop(columns=["month_sort"])
    print(f"[consolidate] SKU view: {len(sku_view)} rows")
    return sku_view
