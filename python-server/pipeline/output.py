"""
pipeline/output.py
------------------
Generates the final output files:
  1. Excel workbook replicating the PTG master structure
  2. CSV exports for each summary table (for dashboard consumption)
  3. Season Readiness summary
"""

from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def generate_summary_tables(
    master: pd.DataFrame,
    site_supply: pd.DataFrame,
    bandwidth: pd.DataFrame,
    matdi_vs_target: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """
    Build all pivot / summary tables matching the PTG master structure.
    Returns a dict of table_name -> DataFrame.
    """
    tables = {}

    # --- Cases post Attain (monthly by Tech) ---
    cases_pivot = master.pivot_table(
        index="main_tech",
        columns="month",
        values="supply_cases",
        aggfunc="sum",
        fill_value=0,
    )
    cases_pivot.columns = [str(c) for c in cases_pivot.columns]
    tables["cases_post_attain"] = cases_pivot

    # --- Litons post Attain ---
    litons_pivot = master.pivot_table(
        index="main_tech",
        columns="month",
        values="supply_litons",
        aggfunc="sum",
        fill_value=0,
    )
    litons_pivot.columns = [str(c) for c in litons_pivot.columns]
    tables["litons_post_attain"] = litons_pivot

    # --- Pallets post Attain ---
    pallets_pivot = master.pivot_table(
        index="main_tech",
        columns="month",
        values="supply_pallets",
        aggfunc="sum",
        fill_value=0,
    )
    pallets_pivot.columns = [str(c) for c in pallets_pivot.columns]
    tables["pallets_post_attain"] = pallets_pivot

    # --- Inventory by Tech (supply, demand, inventory, DOH) ---
    inv_col = "projected_inv_cases" if "projected_inv_cases" in master.columns else "inv_cases"
    inv_view = master[["main_tech", "month", "supply_cases", "demand_cases", inv_col]].copy()
    if "doh" in master.columns:
        inv_view["doh"] = master["doh"]
    tables["inv_by_tech"] = inv_view

    # --- MATDI Phasing ---
    if "matdi" in master.columns:
        matdi_pivot = master.pivot_table(
            index="main_tech",
            columns="month",
            values="matdi",
            aggfunc="mean",
        )
        matdi_pivot.columns = [str(c) for c in matdi_pivot.columns]
        tables["matdi_phasing"] = matdi_pivot

    # --- Tonnage Recap by Site ---
    tonnage_recap = site_supply.groupby(["site_name", "month"], as_index=False).agg(
        litons=("supply_litons", "sum")
    )
    tonnage_recap_pivot = tonnage_recap.pivot_table(
        index="site_name",
        columns="month",
        values="litons",
        aggfunc="sum",
        fill_value=0,
    )
    tonnage_recap_pivot.columns = [str(c) for c in tonnage_recap_pivot.columns]
    tables["tonnage_recap"] = tonnage_recap_pivot

    # --- Bandwidth / Season Readiness ---
    tables["season_readiness"] = bandwidth

    # --- MATDI vs Target ---
    tables["matdi_vs_target"] = matdi_vs_target

    print(f"[output] Generated {len(tables)} summary tables")
    return tables


def export_to_excel(tables: dict[str, pd.DataFrame], filename: str = "PTG_Automated_Output.xlsx") -> Path:
    """
    Write all summary tables into a single Excel workbook, one sheet per table.
    Mirrors the structure of the PTG master file.
    """
    output_path = OUTPUT_DIR / filename
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in tables.items():
            safe_name = sheet_name[:31]  # Excel sheet name limit
            if isinstance(df.index, pd.Index) and df.index.name:
                df.to_excel(writer, sheet_name=safe_name)
            else:
                df.to_excel(writer, sheet_name=safe_name, index=False)

    print(f"[output] Excel workbook written: {output_path}")
    return output_path


def export_to_csv(tables: dict[str, pd.DataFrame]) -> list[Path]:
    """
    Export each summary table as a CSV for dashboard / downstream consumption.
    """
    paths = []
    for name, df in tables.items():
        path = OUTPUT_DIR / f"{name}.csv"
        df.to_csv(path)
        paths.append(path)
    print(f"[output] {len(paths)} CSV files written to {OUTPUT_DIR}")
    return paths


def season_readiness(bandwidth: pd.DataFrame) -> str:
    """
    Generate a human-readable season readiness summary report string.
    """
    lines = [
        "SEASON READINESS SUMMARY",
        "=" * 50,
        f"{'Technology':<25} {'Bandwidth':>10} {'Status':>10}",
        "-" * 50,
    ]
    for _, row in bandwidth.sort_values("main_tech").iterrows():
        status = row["season_readiness"]
        symbol = {"Green": "✓", "Yellow": "~", "Red": "✗"}.get(status, "?")
        lines.append(
            f"{row['main_tech']:<25} {row['bandwidth']:>10.1%} {symbol} {status}"
        )
    lines.append("-" * 50)
    green = (bandwidth["season_readiness"] == "Green").sum()
    yellow = (bandwidth["season_readiness"] == "Yellow").sum()
    red = (bandwidth["season_readiness"] == "Red").sum()
    lines.append(f"Green: {green}  Yellow: {yellow}  Red: {red}")

    report = "\n".join(lines)
    print(report)

    report_path = OUTPUT_DIR / "season_readiness.txt"
    with open(report_path, "w") as f:
        f.write(report)
    return report
