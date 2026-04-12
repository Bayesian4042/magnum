"""
Magnum S&OP Automation Pipeline
--------------------------------
Entry point. Runs the full pipeline:
  1. Extract   - load all source xlsx files
  2. Transform - unit conversions, attainment, litons, pallets
  3. Consolidate - merge supply + demand + inventory
  4. Calculate - project inventory, MATDI, bandwidth
  5. Output    - Excel workbook + CSVs + season readiness report

Usage:
  uv run python main.py
  uv run python main.py --no-excel   (skip Excel export, CSVs only)
"""

import argparse
import time

from pipeline import extract, transform, consolidate, calculate, output


def run_pipeline(export_excel: bool = True) -> None:
    t0 = time.time()
    print("\n=== MAGNUM S&OP AUTOMATION PIPELINE ===\n")

    # ------------------------------------------------------------------
    # 1. EXTRACT
    # ------------------------------------------------------------------
    print("--- Phase 1: Extract ---")
    conv_table = extract.load_conversion_table()
    attain_table = extract.load_attainment_table()

    tmicc = extract.load_actual_supply_tmicc()
    cm = extract.load_actual_supply_cm()
    rr = extract.load_rr_supply()
    manual_supply = extract.load_manual_supply_adjustments()
    ptg_baseline = extract.load_ptg_2026_baseline()
    inventory = extract.load_actual_inventory()
    demand = extract.load_demand()
    inv_seeds = extract.load_inv_seeds()

    # ------------------------------------------------------------------
    # 2. TRANSFORM
    # ------------------------------------------------------------------
    print("\n--- Phase 2: Transform ---")
    supply_monthly = transform.prepare_supply(
        tmicc, cm, rr, conv_table, attain_table,
        manual_df=manual_supply,
    )
    demand_monthly = transform.prepare_demand(demand, conv_table)
    inventory_monthly = transform.prepare_inventory(inventory, conv_table)

    # ------------------------------------------------------------------
    # 3. CONSOLIDATE
    # ------------------------------------------------------------------
    print("\n--- Phase 3: Consolidate ---")
    master = consolidate.build_master_view(
        supply_monthly, demand_monthly, inventory_monthly,
        ptg_2026_baseline=ptg_baseline,
    )
    site_supply = consolidate.build_site_supply_view(supply_monthly)

    # ------------------------------------------------------------------
    # 4. CALCULATE
    # ------------------------------------------------------------------
    print("\n--- Phase 4: Calculate ---")
    actual_inv = extract.load_actual_inv_by_tech()
    client_doh = extract.load_client_doh_and_targets()
    master = calculate.project_inventory(
        master, starting_inv=inv_seeds, actual_inv=actual_inv,
    )
    master = calculate.compute_matdi(master, client_doh_data=client_doh)
    bandwidth = calculate.compute_bandwidth(master, client_doh_data=client_doh)
    matdi_vs_target = calculate.compare_to_matdi_targets(master)

    # ------------------------------------------------------------------
    # 5. OUTPUT
    # ------------------------------------------------------------------
    print("\n--- Phase 5: Output ---")
    tables = output.generate_summary_tables(master, site_supply, bandwidth, matdi_vs_target)

    if export_excel:
        output.export_to_excel(tables)

    output.export_to_csv(tables)
    output.season_readiness(bandwidth)

    elapsed = time.time() - t0
    print(f"\n=== Pipeline complete in {elapsed:.1f}s ===")
    print(f"Output files written to: output/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Magnum S&OP Automation Pipeline")
    parser.add_argument("--no-excel", action="store_true", help="Skip Excel export")
    args = parser.parse_args()
    run_pipeline(export_excel=not args.no_excel)
