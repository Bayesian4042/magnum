"""
pipeline/calculate.py
---------------------
Core S&OP calculations:
  - Rolling inventory projection (supply - demand + prior inventory)
  - MATDI (Moving Annual Total Days of Inventory)
  - DOH (Days on Hand, monthly)
  - Bandwidth / Season Readiness traffic light
"""

import pandas as pd
import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_config(filename: str) -> dict:
    with open(CONFIG_DIR / filename) as f:
        return yaml.safe_load(f)


def project_inventory(
    master: pd.DataFrame,
    starting_inv: dict | None = None,
    actual_inv: dict | None = None,
) -> pd.DataFrame:
    """
    Project forward inventory month by month per technology.

    Matches the client's 'Inv By Tech Post Attain' sheet logic exactly:

      - Months with MBEWH actual inventory (Jan, Feb for MRF3) keep their
        actual values.
      - The first projected month (Mar for MRF3) starts from the last actual
        and rolls forward:  Inv[t] = Inv[t-1] + Supply[t] - Demand[t]

    Parameters
    ----------
    master      : consolidated master view (must have supply_cases, demand_cases, inv_cases)
    starting_inv: {main_tech: seed_cases} — Dec prior-year actuals from load_inv_seeds()
    actual_inv  : {main_tech: {month_str: cases}} — per-tech per-month MBEWH actuals.
                  When provided, these override inv_cases for actual months.
    """
    master = master.copy()
    master["month_dt"] = pd.to_datetime(master["month"], format="%Y-%m", errors="coerce")
    master = master.sort_values(["main_tech", "month_dt"])

    results = []
    for tech, group in master.groupby("main_tech"):
        group = group.copy().reset_index(drop=True)
        group["projected_inv_cases"] = 0.0

        # Override inv_cases with actual_inv if provided
        if actual_inv and tech in actual_inv:
            for idx, row in group.iterrows():
                m = row["month"]
                if m in actual_inv[tech]:
                    group.at[idx, "inv_cases"] = actual_inv[tech][m]

        # Find the last month with actual MBEWH inventory
        actual_rows = group[group["inv_cases"] > 0]

        if len(actual_rows) > 0:
            last_actual_idx = actual_rows.index[-1]
            # Actual months keep their MBEWH values
            for idx in actual_rows.index:
                group.at[idx, "projected_inv_cases"] = group.at[idx, "inv_cases"]

            # Project forward from the last actual month
            for i in range(last_actual_idx + 1, len(group)):
                prev = group.at[i - 1, "projected_inv_cases"]
                group.at[i, "projected_inv_cases"] = (
                    prev + group.at[i, "supply_cases"] - group.at[i, "demand_cases"]
                )

            # For months before the first actual, use seed if available
            first_actual_idx = actual_rows.index[0]
            if first_actual_idx > 0 and starting_inv and tech in starting_inv:
                seed = starting_inv[tech]
                group.at[0, "projected_inv_cases"] = (
                    seed + group.at[0, "supply_cases"] - group.at[0, "demand_cases"]
                )
                for i in range(1, first_actual_idx):
                    prev = group.at[i - 1, "projected_inv_cases"]
                    group.at[i, "projected_inv_cases"] = (
                        prev + group.at[i, "supply_cases"] - group.at[i, "demand_cases"]
                    )

        elif starting_inv and tech in starting_inv:
            # No actuals at all — project all months from the seed
            seed = starting_inv[tech]
            group.at[0, "projected_inv_cases"] = (
                seed + group.at[0, "supply_cases"] - group.at[0, "demand_cases"]
            )
            for i in range(1, len(group)):
                prev = group.at[i - 1, "projected_inv_cases"]
                group.at[i, "projected_inv_cases"] = (
                    prev + group.at[i, "supply_cases"] - group.at[i, "demand_cases"]
                )

        results.append(group)

    result = pd.concat(results, ignore_index=True).drop(columns=["month_dt"])
    print(f"[calculate] Inventory projected for {result['main_tech'].nunique()} technologies")
    return result


def compute_matdi(
    master: pd.DataFrame,
    client_doh_data: dict | None = None,
    doh_target_override: float | None = None,
) -> pd.DataFrame:
    """
    Compute MATDI and DOH for each tech x month.

    MATDI = (Projected_Inv / Rolling_12M_Demand) * 365

    DOH: The client's DOH uses a trailing 12-month demand that includes 2025
    historical actuals from SAP (not available in MRF3 Demand alone).
    When client_doh_data is provided (from extract.load_client_doh_and_targets),
    we use the client's exact DOH values.  Otherwise we approximate with
    the 2026-only rolling demand.

    When doh_target_override is set, client_doh_data is ignored so that
    the what-if scenario recomputes DOH from the formula.

    Parameters
    ----------
    master              : master view with projected_inv_cases
    client_doh_data     : output of extract.load_client_doh_and_targets()
    doh_target_override : if set, overrides the config DOH target and forces
                          formula-based DOH computation (ignores client DOH).
    """
    master = master.copy()
    master["month_dt"] = pd.to_datetime(master["month"], format="%Y-%m", errors="coerce")
    master = master.sort_values(["main_tech", "month_dt"])

    master["rolling_12m_demand"] = (
        master.groupby("main_tech")["demand_cases"]
        .transform(lambda x: x.rolling(window=12, min_periods=1).sum())
    )

    inv_col = "projected_inv_cases" if "projected_inv_cases" in master.columns else "inv_cases"

    master["matdi"] = (
        master[inv_col].where(master["rolling_12m_demand"] > 0, other=0)
        / master["rolling_12m_demand"].replace(0, float("nan"))
        * 365
    ).fillna(0)

    use_client = client_doh_data if doh_target_override is None else None

    if use_client:
        master["doh"] = 0.0
        for idx, row in master.iterrows():
            tech = row["main_tech"]
            month = row["month"]
            if tech in use_client and month in use_client[tech]["doh"]:
                master.at[idx, "doh"] = use_client[tech]["doh"][month]
            elif row["rolling_12m_demand"] > 0:
                master.at[idx, "doh"] = row[inv_col] / row["rolling_12m_demand"] * 365
    else:
        master["doh"] = (
            master[inv_col].where(master["rolling_12m_demand"] > 0, other=0)
            / master["rolling_12m_demand"].replace(0, float("nan"))
            * 365
        ).fillna(0)

    config = load_config("manual_adjustments.yaml")
    master["doh_target"] = doh_target_override if doh_target_override is not None else config.get("doh_target", 45)

    master = master.drop(columns=["month_dt"]).reset_index(drop=True)
    print(f"[calculate] MATDI/DOH computed for {master['main_tech'].nunique()} technologies")
    return master


def compute_bandwidth(
    master: pd.DataFrame,
    client_doh_data: dict | None = None,
    doh_target_override: float | None = None,
    peak_month: str = "2026-08",
    season_start: str = "2026-05",
    season_end: str = "2026-09",
) -> pd.DataFrame:
    """
    Compute bandwidth (season readiness) for each technology.

    Matches the client's formula from "Inv By Tech Post Attain":
      1. Excess DOH days = Peak_DOH - DOH_target  (e.g. 71.17 - 45 = 26.17)
      2. Excess cases    = excess_days * (Peak_Inv / Peak_DOH)
      3. Bandwidth       = excess_cases / Season_Demand (May-Sep)

    When client_doh_data is provided AND doh_target_override is None,
    uses the client's exact DOH and BW values.  When doh_target_override
    is set, always recomputes from the formula so the what-if takes effect.

    Returns a summary DataFrame with one row per tech.
    """
    config = load_config("manual_adjustments.yaml")
    thresholds = config.get("bandwidth_thresholds", {})
    default_thresh = thresholds.get("default", {"green": 0.10, "yellow": 0.05})
    doh_target = doh_target_override if doh_target_override is not None else config.get("doh_target", 45)
    inv_targets = config.get("inventory_case_targets", {})

    use_client = client_doh_data if doh_target_override is None else None

    inv_col = "projected_inv_cases" if "projected_inv_cases" in master.columns else "inv_cases"

    summary_rows = []
    for tech, group in master.groupby("main_tech"):
        annual_demand = group["demand_cases"].sum()
        if annual_demand == 0:
            continue

        if use_client and tech in use_client and use_client[tech].get("bandwidth") is not None:
            bandwidth = use_client[tech]["bandwidth"]
            tech_doh_target = use_client[tech].get("doh_target", doh_target)
        else:
            peak_row = group[group["month"] == peak_month]
            if len(peak_row) > 0:
                peak_inv = peak_row[inv_col].iloc[0]
                peak_doh = peak_row["doh"].iloc[0] if "doh" in peak_row.columns else 0

                if peak_doh > 0:
                    excess_days = peak_doh - doh_target
                    daily_rate = peak_inv / peak_doh
                    excess_cases = excess_days * daily_rate

                    season_demand = group[
                        (group["month"] >= season_start) & (group["month"] <= season_end)
                    ]["demand_cases"].sum()

                    bandwidth = excess_cases / season_demand if season_demand > 0 else 0
                else:
                    bandwidth = 0
            else:
                bandwidth = 0
            tech_doh_target = doh_target

        peak_inv = group[group["month"] <= peak_month][inv_col].max()
        trough_inv = group[inv_col].min()

        peak_row = group[group["month"] == peak_month]
        peak_doh = peak_row["doh"].iloc[0] if len(peak_row) > 0 and "doh" in peak_row.columns else 0
        doh_over_under = peak_doh - tech_doh_target

        inv_target_aug = inv_targets.get("Aug", 0)
        inv_over_under = (peak_row[inv_col].iloc[0] - inv_target_aug) if len(peak_row) > 0 and inv_target_aug else 0

        thresh = thresholds.get(tech, default_thresh)
        if bandwidth >= thresh["green"]:
            status = "Green"
        elif bandwidth >= thresh["yellow"]:
            status = "Yellow"
        else:
            status = "Red"

        summary_rows.append({
            "main_tech": tech,
            "peak_inv_cases": peak_inv,
            "trough_inv_cases": trough_inv,
            "annual_demand_cases": annual_demand,
            "bandwidth": round(bandwidth, 4),
            "peak_doh": round(peak_doh, 2),
            "doh_target": tech_doh_target,
            "doh_over_under": round(doh_over_under, 2),
            "season_readiness": status,
        })

    bw_df = pd.DataFrame(summary_rows)
    print(f"[calculate] Bandwidth computed: {len(bw_df)} technologies")
    green = (bw_df["season_readiness"] == "Green").sum()
    yellow = (bw_df["season_readiness"] == "Yellow").sum()
    red = (bw_df["season_readiness"] == "Red").sum()
    print(f"[calculate]   Green={green}  Yellow={yellow}  Red={red}")
    return bw_df


def compare_to_matdi_targets(master: pd.DataFrame) -> pd.DataFrame:
    """
    Compare MATDI projections against configured targets at key months (Apr, Aug, EOY).
    Returns a DataFrame with: main_tech, month, projected_matdi, target_matdi, diff, status
    """
    if "matdi" not in master.columns:
        raise ValueError("Run compute_matdi() before compare_to_matdi_targets()")

    config = load_config("manual_adjustments.yaml")
    targets = config.get("matdi_targets", {})

    # Build month->target mapping using year from data
    years = master["month"].str[:4].unique()
    year = sorted(years)[-1] if len(years) > 0 else "2026"

    month_map = {
        f"{year}-04": targets.get("Apr"),
        f"{year}-08": targets.get("Aug"),
        f"{year}-12": targets.get("Dec"),
    }

    rows = []
    for month, target in month_map.items():
        if target is None:
            continue
        month_data = master[master["month"] == month]
        for _, row in month_data.iterrows():
            diff = row["matdi"] - target
            status = "On Track" if diff >= 0 else "At Risk"
            rows.append({
                "main_tech": row["main_tech"],
                "month": month,
                "projected_matdi": round(row["matdi"], 2),
                "target_matdi": target,
                "diff": round(diff, 2),
                "status": status,
            })

    result = pd.DataFrame(rows)
    print(f"[calculate] MATDI vs target: {len(result)} checkpoints evaluated")
    return result
