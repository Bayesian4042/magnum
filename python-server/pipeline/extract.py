"""
pipeline/extract.py
-------------------
Reads all source xlsx files into clean, normalized DataFrames.

Each function returns a tidy DataFrame with standardized column names:
  du          - 8-digit SKU/material code (int)
  site        - plant/site code (str, normalized)
  date        - datetime
  month       - period string "YYYY-MM"
  cases       - quantity in cases
  description - product description
"""

from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"

FILES = {
    "supply_actuals": DATA_DIR
    / "PTG 2026 Actuals TMICC and CM or IMports 3.25.26--Converting Actual Supply Info.xlsx",
    "inventory_actuals": DATA_DIR
    / "Feb 2026 Inventory -- Actual Inventory Conversion.xlsx",
    "demand_conversion": DATA_DIR
    / "Converting MRF File to PTG 2025-2026 MRF3- Demand Conversion.xlsx",
    "rr_supply": DATA_DIR
    / "Converting 3pm-Import and all RR to PTG MRF 3--Rapid Response Conversion.xlsx",
    "ptg_master": DATA_DIR / "PTG for 2026_MRF3_Send To Plants.xlsx",
}


def _read(file_key: str, sheet: str, header: int = 0) -> pd.DataFrame:
    return pd.read_excel(
        FILES[file_key], sheet_name=sheet, header=header, engine="openpyxl"
    )


# ---------------------------------------------------------------------------
# Conversion / Reference Tables
# ---------------------------------------------------------------------------


def load_conversion_table() -> pd.DataFrame:
    """
    Load the master DU -> Tech/Litons/Per Pallet conversion table.
    Source: Demand Conversion file, 'Tech Pallet' sheet.
    Returns columns: du, sub_tech, main_tech, liters_per_case, litons, per_pallet
    """
    df = _read("demand_conversion", "Tech Pallet")
    df = df.rename(
        columns={
            "DU": "du",
            "Sub Tech": "sub_tech",
            "Main Tech": "main_tech",
            "Liters per case": "liters_per_case",
            "Litons": "litons",
            "Per Pallet": "per_pallet",
        }
    )
    df["du"] = pd.to_numeric(df["du"], errors="coerce").dropna()
    df = df[
        ["du", "sub_tech", "main_tech", "liters_per_case", "litons", "per_pallet"]
    ].copy()
    df = df.dropna(subset=["du"])
    df["du"] = df["du"].astype(int)
    # Drop duplicate DUs, keep first
    df = df.drop_duplicates(subset=["du"])
    print(f"[extract] Conversion table loaded: {len(df)} DUs")
    return df


def load_attainment_table() -> pd.DataFrame:
    """
    Load attainment % factors by technology.
    Source: PTG master, 'Attain %' sheet.
    Returns columns: main_tech, attain_pct
    """
    df = _read("ptg_master", "Attain %")
    df = df[["Tech", "Attain %"]].rename(
        columns={"Tech": "main_tech", "Attain %": "attain_pct"}
    )
    df = df.dropna(subset=["main_tech"])
    print(f"[extract] Attainment table loaded: {len(df)} tech entries")
    return df


# ---------------------------------------------------------------------------
# Actual Supply (SAP)
# ---------------------------------------------------------------------------


def load_actual_supply_tmicc() -> pd.DataFrame:
    """
    Load SAP TMICC actuals (manufacturing output).
    Source: Supply Actuals file, 'TMICC' sheet.
    Returns columns: du, site, date, month, cases, description
    """
    df = _read("supply_actuals", "TMICC")
    df = df.rename(
        columns={
            "Material": "du",
            "Plant": "site",
            "Quantity": "cases",
            "Pstng Date": "date",
            "Description": "description",
        }
    )
    df["du"] = pd.to_numeric(df["du"], errors="coerce")
    df["cases"] = pd.to_numeric(df["cases"], errors="coerce").fillna(0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["site"] = df["site"].astype(str)
    df["source_type"] = "TMICC"
    df = df[
        ["du", "site", "date", "month", "cases", "description", "source_type"]
    ].copy()
    df = df.dropna(subset=["du", "date"])
    df["du"] = df["du"].astype(int)
    print(f"[extract] TMICC actuals loaded: {len(df)} rows, {df['du'].nunique()} DUs")
    return df


def load_actual_supply_cm() -> pd.DataFrame:
    """
    Load contract manufacturing and import goods receipts.
    Source: Supply Actuals file, 'CM Info' + 'Sheet5' sheets.
    Returns columns: du, site, date, month, cases, description, vendor
    """
    cm = _read("supply_actuals", "CM Info")
    cm = cm.rename(
        columns={
            "Material": "du",
            "Plant": "site",
            "Goods Receipt Quantity": "cases",
            "Goods Receipt Date": "date",
            "Description": "description",
            "Vendor Name": "vendor",
        }
    )
    cm["source_type"] = "CM"

    imp = _read("supply_actuals", "Sheet5")
    imp = imp.rename(
        columns={
            "Material": "du",
            "Plnt": "site",
            "Goods Receipt Quantity": "cases",
            "Goods Receipt Date": "date",
            "Description": "description",
            "Vendor Name": "vendor",
        }
    )
    imp["source_type"] = "Import"

    df = pd.concat([cm, imp], ignore_index=True)
    df["du"] = pd.to_numeric(df["du"], errors="coerce")
    df["cases"] = pd.to_numeric(df["cases"], errors="coerce").fillna(0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["site"] = df["site"].astype(str)
    df = df[
        ["du", "site", "date", "month", "cases", "description", "vendor", "source_type"]
    ].copy()
    df = df.dropna(subset=["du", "date"])
    df["du"] = df["du"].astype(int)
    print(
        f"[extract] CM/Import actuals loaded: {len(df)} rows, {df['du'].nunique()} DUs"
    )
    return df


# ---------------------------------------------------------------------------
# Forward-Looking Supply (Rapid Response)
# ---------------------------------------------------------------------------


def load_rr_supply() -> pd.DataFrame:
    """
    Load Rapid Response forward-looking supply plan (cleaned tidy format).
    Source: RR Conversion file, 'Cleaned Up' sheet.
    Returns columns: du, site, date, month, cases, description, line
    """
    df = _read("rr_supply", "Cleaned Up")
    df = df.rename(
        columns={
            "DU": "du",
            "Site": "site",
            "Qty": "cases",
            "Date": "date",
            "Description": "description",
            "Line": "line",
        }
    )
    df["du"] = pd.to_numeric(df["du"], errors="coerce")
    df["cases"] = pd.to_numeric(df["cases"], errors="coerce").fillna(0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["site"] = df["site"].astype(str)
    df["source_type"] = "RR"
    df = df[
        ["du", "site", "date", "month", "cases", "description", "line", "source_type"]
    ].copy()
    df = df.dropna(subset=["du", "date"])
    df["du"] = df["du"].astype(int)
    print(f"[extract] RR supply loaded: {len(df)} rows, {df['du'].nunique()} DUs")
    return df


# ---------------------------------------------------------------------------
# Actual Inventory (SAP MBEWH)
# ---------------------------------------------------------------------------


def load_actual_inventory() -> pd.DataFrame:
    """
    Load SAP MBEWH inventory actuals.
    Source: Inventory file, 'MBEWH-Actuals' sheet.
    Returns columns: du, site, year, period, month, cases, pallets, tech, description
    """
    df = _read("inventory_actuals", "MBEWH-Actuals")
    df = df.rename(
        columns={
            "Material": "du",
            "ValA": "site",
            "Year": "year",
            "Pe": "period",
            "TotalStock": "cases",
            "Pallets": "pallets",
            "Tech": "tech",
            "Description": "description",
            "Per pallet": "per_pallet_sap",
        }
    )
    df["du"] = pd.to_numeric(df["du"], errors="coerce")
    df["cases"] = pd.to_numeric(df["cases"], errors="coerce").fillna(0)
    df["pallets"] = pd.to_numeric(df["pallets"], errors="coerce").fillna(0)
    df["site"] = df["site"].astype(str)
    df["month"] = df["year"].astype(str) + "-" + df["period"].astype(str).str.zfill(2)
    df = df[
        [
            "du",
            "site",
            "year",
            "period",
            "month",
            "cases",
            "pallets",
            "tech",
            "description",
            "per_pallet_sap",
        ]
    ].copy()
    df = df.dropna(subset=["du"])
    df["du"] = df["du"].astype(int)
    print(
        f"[extract] Inventory actuals loaded: {len(df)} rows, {df['du'].nunique()} DUs"
    )
    return df


# ---------------------------------------------------------------------------
# Demand (MRF File)
# ---------------------------------------------------------------------------


def load_demand() -> pd.DataFrame:
    """
    Load demand forecasts from the PTG Master 'MRF3 Demand' sheet.
    This sheet is the already-processed demand after manual add-ons.
    Returns a tidy DataFrame: du, sub_tech, main_tech, month, cases

    Known data quirk: columns 6-8 are 2026-01..03 but columns 9-17 are
    mislabeled as 2024-04..12 — they are actually 2026-04..12.  We detect
    the 12 consecutive month columns by position and force the correct year.
    """
    df = _read("ptg_master", "MRF3 Demand", header=2)

    # Find the 12 consecutive month columns (datetime objects for Jan-Dec).
    # Columns 6-17 in the raw sheet are the monthly demand values.
    import datetime as _dt

    date_cols = [c for c in df.columns if isinstance(c, (_dt.datetime, pd.Timestamp))]

    # Sort by the column's position in the DataFrame to preserve Jan-Dec order
    col_positions = {c: list(df.columns).index(c) for c in date_cols}
    date_cols = sorted(date_cols, key=lambda c: col_positions[c])

    # Take exactly the first 12 date columns (Jan through Dec)
    date_cols = date_cols[:12]

    # Build a rename map: force all 12 columns to 2026-MM-01
    date_rename = {}
    for i, c in enumerate(date_cols):
        correct_date = pd.Timestamp(year=2026, month=i + 1, day=1)
        if pd.Timestamp(c) != correct_date:
            date_rename[c] = correct_date

    if date_rename:
        df = df.rename(columns=date_rename)
        date_cols = [date_rename.get(c, c) for c in date_cols]

    keep = ["DU", "Sub Tech", "Main Tech", "Description"] + date_cols
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.rename(
        columns={
            "DU": "du",
            "Sub Tech": "sub_tech",
            "Main Tech": "main_tech",
            "Description": "description",
        }
    )
    df = df.dropna(subset=["du"])
    df["du"] = pd.to_numeric(df["du"], errors="coerce")
    df = df.dropna(subset=["du"])
    df["du"] = df["du"].astype(int)

    # Melt to tidy format
    df_tidy = df.melt(
        id_vars=["du", "sub_tech", "main_tech", "description"],
        var_name="date_raw",
        value_name="cases",
    )
    df_tidy["date"] = pd.to_datetime(df_tidy["date_raw"], errors="coerce")
    df_tidy["month"] = df_tidy["date"].dt.to_period("M").astype(str)
    df_tidy["cases"] = pd.to_numeric(df_tidy["cases"], errors="coerce").fillna(0)
    df_tidy = df_tidy.dropna(subset=["date"])
    df_tidy = df_tidy[df_tidy["cases"] > 0]
    df_tidy = df_tidy[
        ["du", "sub_tech", "main_tech", "description", "month", "cases"]
    ].copy()

    print(
        f"[extract] Demand loaded: {len(df_tidy)} rows, {df_tidy['du'].nunique()} DUs, "
        f"months: {sorted(df_tidy['month'].unique())}"
    )
    return df_tidy


# ---------------------------------------------------------------------------
# Inv By Tech Post Attain — extract seed inventory values (col2 = prior-month actual)
# ---------------------------------------------------------------------------


def load_inv_seeds() -> dict:
    """
    Extract the starting inventory seeds from 'Inv By Tech Post Attain' sheet.

    In the client's sheet, col0/col1 identifies the tech, col2 is the SAP
    actual snapshot (the prior-month seed used to start the rolling projection).
    Structure per tech block:
      row N:   col1=<tech>  col2=Production  col3=Jan...
      row N+1: col1=<nan>   col2=Demand      col3=Jan...
      row N+2: col1=Inv     col2=<SEED>      col3=Jan projection...

    Returns dict: {tech_name: seed_cases}
    """
    raw = pd.read_excel(
        FILES["ptg_master"],
        sheet_name="Inv By Tech Post Attain",
        header=None,
        engine="openpyxl",
    )

    seeds = {}
    for i, row in raw.iterrows():
        # The Inv row has col1 == "Inv" and col2 is the numeric seed
        if str(row.iloc[1]).strip() == "Inv":
            seed_val = pd.to_numeric(row.iloc[2], errors="coerce")
            if pd.notna(seed_val):
                # Find the tech name: look back up to 3 rows for a non-null col1
                for lookback in range(1, 4):
                    tech_row = raw.iloc[i - lookback]
                    tech_name = str(tech_row.iloc[1]).strip()
                    if tech_name and tech_name != "nan" and tech_name != "NaN":
                        seeds[tech_name] = seed_val
                        break

    print(f"[extract] Inv seeds loaded: {len(seeds)} technologies")
    for t, v in seeds.items():
        print(f"  {t:<20}: {v:>15,.0f}")
    return seeds


def load_actual_inv_by_tech() -> dict:
    """
    Extract per-tech per-month actual inventory values from 'Inv By Tech Post Attain'.

    The actual months (Jan, Feb for MRF3) come from MBEWH snapshots and cannot
    be replicated via the rolling formula.  This function returns them so that
    project_inventory() can anchor on the real actuals.

    Returns dict: {tech_name: {"2026-01": cases, "2026-02": cases, ...}}
    """
    raw = pd.read_excel(
        FILES["ptg_master"],
        sheet_name="Inv By Tech Post Attain",
        header=None,
        engine="openpyxl",
    )

    months_labels = [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
    ]

    result = {}
    for i, row in raw.iterrows():
        if str(row.iloc[1]).strip() != "Inv":
            continue
        # Find the tech name by looking back
        tech_name = None
        for lookback in range(1, 4):
            prev = raw.iloc[i - lookback]
            name = str(prev.iloc[1]).strip()
            if name and name not in ("nan", "NaN", ""):
                tech_name = name
                break
        if not tech_name:
            continue

        # Col 3..14 = Jan..Dec values
        month_vals = {}
        for j, m in enumerate(months_labels):
            col_idx = 3 + j
            if col_idx < len(row):
                v = pd.to_numeric(row.iloc[col_idx], errors="coerce")
                if pd.notna(v) and v > 0:
                    month_vals[m] = v
        if month_vals:
            result[tech_name] = month_vals

    print(f"[extract] Actual inv by tech loaded: {len(result)} technologies")
    return result


def load_client_doh_and_targets() -> dict:
    """
    Extract per-tech DOH values, DOH target, inventory case targets, and
    bandwidth from the 'Inv By Tech Post Attain' sheet.

    The DOH in the client's sheet uses a trailing 12-month demand denominator
    that includes 2025 historical actuals (not available in MRF3 Demand).
    We extract the client's computed values directly for the baseline.

    Returns dict with structure:
      {
        tech_name: {
          "doh": {month: value, ...},         # cols 3-14 from DOH row
          "doh_target": float,                # col 17 from Production row
          "inv_targets": {month: cases, ...}, # from TGT row
          "bandwidth": float,                 # col 17 from DOH row
        }
      }
    """
    raw = pd.read_excel(
        FILES["ptg_master"],
        sheet_name="Inv By Tech Post Attain",
        header=None,
        engine="openpyxl",
    )
    months_labels = [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
    ]

    result = {}
    current_tech = None

    for i, row in raw.iterrows():
        c1 = str(row.iloc[1]).strip()
        c2 = str(row.iloc[2]).strip()

        # Detect tech block start: col0 non-null, col1 = tech name, col2 = "Production"
        if c2 == "Production" and c1 not in ("nan", "NaN", ""):
            current_tech = c1
            result[current_tech] = {
                "doh": {},
                "doh_target": (
                    pd.to_numeric(row.iloc[17], errors="coerce")
                    if len(row) > 17
                    else None
                ),
                "inv_targets": {},
                "bandwidth": None,
            }

        if current_tech is None:
            continue

        # DOH row
        if c2 == "DOH":
            for j, m in enumerate(months_labels):
                v = pd.to_numeric(row.iloc[3 + j], errors="coerce")
                if pd.notna(v):
                    result[current_tech]["doh"][m] = v
            bw = pd.to_numeric(row.iloc[17], errors="coerce") if len(row) > 17 else None
            if pd.notna(bw):
                result[current_tech]["bandwidth"] = bw

        # TGT row (inventory targets at checkpoints)
        if c2 == "TGT":
            for j, m in enumerate(months_labels):
                v = pd.to_numeric(row.iloc[3 + j], errors="coerce")
                if pd.notna(v) and v > 0:
                    result[current_tech]["inv_targets"][m] = v

    # Filter out techs with no DOH data
    result = {k: v for k, v in result.items() if v["doh"]}
    print(f"[extract] Client DOH + targets loaded: {len(result)} technologies")
    return result


# Mapping from client sheet tech names to our normalized pipeline names
_CLIENT_TECH_NORM = {
    "BJ Pts": "BJ PTS",
    "TALENTI": "Talenti",
    "MG Stick": "MG Sticks",
    "Total IC": None,  # skip the totals row
}


def load_client_inv_by_tech() -> pd.DataFrame:
    """
    Extract the full per-tech monthly data from "Inv By Tech Post Attain":
    Production, Demand, Inventory, and DOH for every tech and month.

    Used for validation: comparing our computed numbers against the client's
    manually assembled baseline.

    Returns DataFrame with columns:
      main_tech, month, client_production, client_demand, client_inventory, client_doh
    """
    raw = pd.read_excel(
        FILES["ptg_master"],
        sheet_name="Inv By Tech Post Attain",
        header=None,
        engine="openpyxl",
    )
    months_labels = [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
    ]

    blocks: dict[str, dict] = {}
    current_tech = None

    for _, row in raw.iterrows():
        b = str(row.iloc[1]).strip()
        c = str(row.iloc[2]).strip()

        if c == "Production" and b not in ("nan", "NaN", ""):
            norm = _CLIENT_TECH_NORM.get(b, b)
            if norm is None:
                current_tech = None
                continue
            current_tech = norm
            blocks[current_tech] = {
                "production": {},
                "demand": {},
                "inventory": {},
                "doh": {},
            }
            for j, m in enumerate(months_labels):
                v = pd.to_numeric(row.iloc[3 + j], errors="coerce")
                if pd.notna(v):
                    blocks[current_tech]["production"][m] = v

        if current_tech is None:
            continue

        if c == "Demand":
            for j, m in enumerate(months_labels):
                v = pd.to_numeric(row.iloc[3 + j], errors="coerce")
                if pd.notna(v):
                    blocks[current_tech]["demand"][m] = v

        if b == "Inv":
            for j, m in enumerate(months_labels):
                v = pd.to_numeric(row.iloc[3 + j], errors="coerce")
                if pd.notna(v):
                    blocks[current_tech]["inventory"][m] = v

        if c == "DOH":
            for j, m in enumerate(months_labels):
                v = pd.to_numeric(row.iloc[3 + j], errors="coerce")
                if pd.notna(v):
                    blocks[current_tech]["doh"][m] = v

    rows = []
    for tech, data in blocks.items():
        for m in months_labels:
            rows.append(
                {
                    "main_tech": tech,
                    "month": m,
                    "client_production": data["production"].get(m, 0),
                    "client_demand": data["demand"].get(m, 0),
                    "client_inventory": data["inventory"].get(m, 0),
                    "client_doh": data["doh"].get(m, 0),
                }
            )

    df = pd.DataFrame(rows)
    print(
        f"[extract] Client inv-by-tech loaded: {len(df)} rows, {df['main_tech'].nunique()} technologies"
    )
    return df


# ---------------------------------------------------------------------------
# Manual Supply Adjustments (from config)
# ---------------------------------------------------------------------------


def load_manual_supply_adjustments() -> pd.DataFrame:
    """
    Load manual supply adjustments from config YAML.
    Covers innovation items and offline supply plans not in SAP/RR.
    Returns DataFrame with same schema as other supply extracts:
      du, site, month, cases, description, source_type
    """
    import yaml

    config_path = Path(__file__).parent.parent / "config" / "manual_adjustments.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    rows = []
    for section in ("innovation_items", "manual_supply_adjustments"):
        items = config.get(section, []) or []
        for item in items:
            du = item.get("du")
            desc = item.get("description", "")
            site = str(item.get("site", "Manual"))
            monthly = item.get("monthly_cases", {}) or {}
            for month, cases in monthly.items():
                if cases and cases > 0:
                    rows.append(
                        {
                            "du": int(du),
                            "site": site,
                            "month": str(month),
                            "cases": float(cases),
                            "description": desc,
                            "source_type": "Manual",
                        }
                    )

    df = pd.DataFrame(rows)
    if len(df) == 0:
        df = pd.DataFrame(
            columns=["du", "site", "month", "cases", "description", "source_type"]
        )

    print(f"[extract] Manual supply adjustments loaded: {len(df)} rows")
    return df


# ---------------------------------------------------------------------------
# PTG Master '2026' Sheet (baseline for validation only)
# ---------------------------------------------------------------------------


def load_ptg_2026_baseline() -> pd.DataFrame:
    """
    Load the existing computed PTG '2026' sheet as a baseline for comparison.
    Source: PTG Master, '2026' sheet.
    Returns columns: du, site, month, week, cases_raw, cases_post_attain,
                     litons_post_attain, pallets_post_attain, sub_tech, main_tech, attain
    """
    df = _read("ptg_master", "2026")
    df = df.rename(
        columns={
            "Material Number": "du",
            "Plant": "site",
            "Delivered quantity": "cases_raw",
            "Basic start date": "date",
            "Material description": "description",
            "Sub Tech": "sub_tech",
            "Main Tech": "main_tech",
            "Attain": "attain",
            "Case post attain": "cases_post_attain",
            "Litons post attainment": "litons_post_attain",
            "Pallets Post Attainment": "pallets_post_attain",
            "Month": "month_label",
            "Week": "week",
            "Liton per": "litons",
            "Per Pallet": "per_pallet",
        }
    )
    df["du"] = pd.to_numeric(df["du"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["site"] = df["site"].astype(str)
    df = df.dropna(subset=["du", "date"])
    df["du"] = df["du"].astype(int)

    # The "Main Tech" column in the 2026 sheet is Plant+Tech concatenated
    # (e.g. "135248oz", "2904EDF"). The real tech name is in "Sub Tech".
    df["main_tech"] = df["sub_tech"]

    print(f"[extract] PTG 2026 baseline loaded: {len(df)} rows")
    return df
