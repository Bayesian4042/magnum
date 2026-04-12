"""
Phase 2: Transformation Mapping Script
Reads the key sheets from each source file, identifies join keys and overlapping
columns with the master PTG output, and prints a documented transformation map.
Output is written to transformation_map.txt for review.
"""

from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = Path(__file__).parent / "transformation_map.txt"

FILES = {
    "supply_actuals": DATA_DIR / "PTG 2026 Actuals TMICC and CM or IMports 3.25.26--Converting Actual Supply Info.xlsx",
    "inventory_actuals": DATA_DIR / "Feb 2026 Inventory -- Actual Inventory Conversion.xlsx",
    "demand_conversion": DATA_DIR / "Converting MRF File to PTG 2025-2026 MRF3- Demand Conversion.xlsx",
    "rr_supply": DATA_DIR / "Converting 3pm-Import and all RR to PTG MRF 3--Rapid Response Conversion.xlsx",
    "process_overview": DATA_DIR / "Inventory Process Overview.xlsx",
    "ptg_master": DATA_DIR / "PTG for 2026_MRF3_Send To Plants.xlsx",
}


def load(path, sheet, header=0):
    return pd.read_excel(path, sheet_name=sheet, header=header, engine="openpyxl")


def section(title):
    return ["\n" + "=" * 80, f"  {title}", "=" * 80]


lines = []
lines += [
    "MAGNUM S&OP TRANSFORMATION MAP",
    "=" * 80,
    "",
    "This document traces how each input source feeds the master PTG file.",
    "Primary join key across all files: DU / Material (8-digit integer SKU code).",
    "",
]

# ---------------------------------------------------------------------------
# 1. CONVERSION TABLE (Master Reference)
# ---------------------------------------------------------------------------
lines += section("1. MASTER CONVERSION TABLE (DU -> Tech, Litons, Per Pallet)")
lines.append(
    "Source: 'Converting MRF File to PTG' -> sheet 'Tech Pallet' (599 rows)\n"
    "Also:   'PTG for 2026_MRF3_Send To Plants' -> sheet 'Tech Litons' (532 rows)\n"
    "Key columns:\n"
    "  DU            -> 8-digit SKU identifier (join key)\n"
    "  Sub Tech      -> Fine-grained technology bucket (e.g. '48oz', 'BJ PTS')\n"
    "  Main Tech     -> Rollup tech bucket (e.g. '48oz', 'BJ PTS', 'MG Sticks')\n"
    "  Numerator     -> Volume numerator for litre calculation\n"
    "  Denominator   -> Volume denominator for litre calculation\n"
    "  Liters per case -> Numerator/Denominator (litres per case)\n"
    "  Litons        -> Liters per case / 1000 (metric tons per case)\n"
    "  Per Pallet    -> Cases per pallet (for pallet position calculation)\n"
    "\n"
    "FORMULA: Tonnage (le tons) = Cases * Litons\n"
    "FORMULA: Pallets = Cases / Per_Pallet\n"
)

conv = load(FILES["demand_conversion"], "Tech Pallet")
lines.append(f"Sample conversion table rows (first 5):\n{conv.head(5).to_string()}\n")

tech_vals = conv["Main Tech"].value_counts()
lines.append(f"Technology buckets found ({len(tech_vals)} unique):\n{tech_vals.to_string()}\n")

# ---------------------------------------------------------------------------
# 2. ACTUAL SUPPLY (SAP -> PTG)
# ---------------------------------------------------------------------------
lines += section("2. ACTUAL SUPPLY: SAP TMICC Table -> PTG '2026' sheet")
lines.append(
    "Source: 'PTG 2026 Actuals...' -> sheet 'TMICC' (1789 rows)\n"
    "  Material   -> DU/SKU code (join key to conversion table)\n"
    "  Plant      -> Manufacturing site code (1352=Covington, 2904=Tulare, etc.)\n"
    "  Quantity   -> Cases produced/shipped on that date\n"
    "  Pstng Date -> Posting date (daily granularity from SAP)\n"
    "\n"
    "Transformation: Aggregate daily cases by Material + Plant + Month,\n"
    "then join to conversion table on DU to get:\n"
    "  Tonnage = SUM(Quantity) * Litons\n"
    "  Pallets = SUM(Quantity) / Per_Pallet\n"
)
tmicc = load(FILES["supply_actuals"], "TMICC")
lines.append(f"Shape: {tmicc.shape}")
lines.append(f"Sites (Plants) found: {sorted(tmicc['Plant'].unique().tolist())}")
lines.append(f"Date range: {tmicc['Pstng Date'].min()} to {tmicc['Pstng Date'].max()}")
lines.append(f"Unique materials: {tmicc['Material'].nunique()}")
lines.append(f"Sample:\n{tmicc.head(3).to_string()}\n")

lines += section("2b. CONTRACT MANUFACTURING (CM/Import) SUPPLY")
lines.append(
    "Source: 'PTG 2026 Actuals...' -> sheet 'CM Info' (319 rows)\n"
    "  Material               -> DU/SKU code\n"
    "  Plant                  -> Receiving site code\n"
    "  Goods Receipt Quantity -> Cases received\n"
    "  Goods Receipt Date     -> Date of receipt\n"
    "  Vendor / GS Name       -> Contract manufacturer name\n"
    "\n"
    "Source: 'PTG 2026 Actuals...' -> sheet 'Sheet5' (206 rows)\n"
    "  Same structure — additional imports (GDI, Rhino, Incom, etc.)\n"
)
cm = load(FILES["supply_actuals"], "CM Info")
lines.append(f"CM Vendors: {cm['Vendor Name'].unique().tolist()}")
lines.append(f"Sample:\n{cm.head(3).to_string()}\n")

# ---------------------------------------------------------------------------
# 3. FORWARD-LOOKING SUPPLY (Rapid Response -> PTG)
# ---------------------------------------------------------------------------
lines += section("3. FORWARD-LOOKING SUPPLY: Rapid Response -> PTG")
lines.append(
    "Source: 'Converting 3pm-Import...' -> sheet 'Combined' (734 rows)\n"
    "  Part Name      -> DU/SKU code (join key)\n"
    "  Site           -> Plant code\n"
    "  Site Name      -> Plant name\n"
    "  PPG            -> Product Group\n"
    "  Big/Small Cat  -> Category rollup\n"
    "  Site Type      -> Manufacturing / CM / Import\n"
    "  Line           -> Production line\n"
    "  Figure Name    -> Supply figure type\n"
    "  [date cols]    -> Weekly supply quantities (cases) by week-ending date\n"
    "\n"
    "Source: 'Converting 3pm-Import...' -> sheet 'Cleaned Up' (1876 rows)\n"
    "  DU / Site / Qty / Date / Description / Line\n"
    "  This is the cleaned, tidy-format version of the weekly supply plan.\n"
    "\n"
    "Transformation: Aggregate weekly cases to monthly by DU + Site + Month,\n"
    "then join conversion table for tonnage & pallet calculations.\n"
)
rr_combined = load(FILES["rr_supply"], "Combined")
lines.append(f"RR Combined shape: {rr_combined.shape}")
lines.append(f"Sites: {rr_combined['Site'].dropna().unique().tolist()[:15]}")
cleaned_up = load(FILES["rr_supply"], "Cleaned Up")
lines.append(f"Cleaned Up shape: {cleaned_up.shape}")
lines.append(f"Date range: {cleaned_up['Date'].min()} to {cleaned_up['Date'].max()}")
lines.append(f"Sample Cleaned Up:\n{cleaned_up.head(3).to_string()}\n")

# ---------------------------------------------------------------------------
# 4. DEMAND (MRF File -> PTG)
# ---------------------------------------------------------------------------
lines += section("4. DEMAND: MRF File -> PTG 'MRF3 Demand' Sheet")
lines.append(
    "Source: 'Converting MRF File...' -> sheet 'MRF2' (881 rows)\n"
    "  Row 0 is the actual header: Segment, Tech, DU, UCC, Description,\n"
    "  then monthly case columns (2024 actuals, 2025-2026 forecast)\n"
    "\n"
    "Target: 'PTG for 2026_MRF3' -> sheet 'MRF3 Demand' (392 rows)\n"
    "  DU, Sub Tech, Main Tech, Description, monthly case columns (2026 months)\n"
    "  Per Pallet, then historical pallet columns (JAN-2023 ... DEC-2023)\n"
    "\n"
    "Transformation:\n"
    "  Cases (monthly) -> join conversion table on DU ->\n"
    "  Demand Litons = Cases * Litons\n"
    "  Demand Pallets = Cases / Per_Pallet\n"
    "\n"
    "Manual add-ons captured in MRF3 Demand (rows with special DUs):\n"
    "  DU 84141102 = B&J Export Pts (export demand)\n"
    "  DU 62735647 = B&J Export Bulk (export demand)\n"
    "  DU 84141103 = BJ Pints Depend Demand (dependent demand)\n"
    "  DU 69798156 = 828ml SMOG (excess inventory for sale)\n"
)
mrf3_demand = load(FILES["ptg_master"], "MRF3 Demand", header=2)
lines.append(f"MRF3 Demand shape: {mrf3_demand.shape}")
lines.append(f"Sample:\n{mrf3_demand.head(5).to_string()}\n")

# ---------------------------------------------------------------------------
# 5. ACTUAL INVENTORY (SAP MBEWH -> PTG)
# ---------------------------------------------------------------------------
lines += section("5. ACTUAL INVENTORY: SAP MBEWH -> PTG 'Inv By Tech Post Attain'")
lines.append(
    "Source: 'Feb 2026 Inventory...' -> sheet 'MBEWH-Actuals' (2275 rows)\n"
    "  Material    -> DU/SKU code (join key)\n"
    "  ValA        -> Plant/site code\n"
    "  Year/Pe     -> Year and Period (month)\n"
    "  TotalStock  -> Inventory cases on hand\n"
    "  Total Val.  -> Inventory value\n"
    "  Tech        -> Technology bucket (pre-labeled in SAP extract)\n"
    "  Per pallet  -> Cases per pallet\n"
    "  Pallets     -> TotalStock / Per pallet (pre-calculated)\n"
    "\n"
    "Transformation:\n"
    "  Group by Tech + Period -> sum TotalStock -> starting inventory for projections\n"
    "  Inventory Litons = TotalStock * Litons_per_case\n"
    "\n"
    "MATDI Formula:\n"
    "  MAT (Moving Annual Total) = sum of last 12 months demand\n"
    "  DI (Days of Inventory)    = (Inventory_Cases / MAT_Cases) * 365\n"
    "  MATDI                     = DI (rolling, updated monthly)\n"
)
inv = load(FILES["inventory_actuals"], "MBEWH-Actuals")
lines.append(f"Inventory shape: {inv.shape}")
lines.append(f"Tech buckets: {inv['Tech'].unique().tolist()}")
lines.append(f"Sites (ValA): {sorted(inv['ValA'].unique().tolist())}")
lines.append(f"Total inventory cases: {inv['TotalStock'].sum():,.0f}")
lines.append(f"Sample:\n{inv.head(3).to_string()}\n")

# ---------------------------------------------------------------------------
# 6. MASTER PTG OUTPUT STRUCTURE
# ---------------------------------------------------------------------------
lines += section("6. MASTER PTG OUTPUT: 'PTG for 2026_MRF3_Send To Plants.xlsx'")
lines.append(
    "Sheet '2026' (7261 rows) - GRAIN: Material + Plant + Week\n"
    "  Material Number          -> DU/SKU code\n"
    "  Plant                    -> Site code\n"
    "  Delivered quantity       -> Raw production cases (from RR/SAP)\n"
    "  Basic start date         -> Week start date\n"
    "  Material description     -> SKU name\n"
    "  Production Version       -> Line/version code\n"
    "  Liton per                -> Litons conversion factor (from Tech Litons tab)\n"
    "  Per Pallet               -> Cases per pallet\n"
    "  Sub Tech / Main Tech     -> Technology classification\n"
    "  Attain                   -> Attainment factor from 'Attain %' tab\n"
    "  Case post attain         -> Delivered quantity * Attain\n"
    "  Litons post attainment   -> Case post attain * Liton per\n"
    "  Pallets Post Attainment  -> Case post attain / Per Pallet\n"
    "  Month / Week             -> Time dimension\n"
    "\n"
    "Sheet 'Cases post Attain' - Monthly rollup by Tech + Plant (pivot)\n"
    "Sheet 'Litons Post Attain' - Monthly liton totals by Tech + Plant\n"
    "Sheet 'Pallets post Attain' - Monthly pallet totals by Tech + Plant\n"
    "Sheet 'Inv By Tech Post Attain' - Supply, Demand, Inventory, DOH by Tech\n"
    "Sheet 'Phasing MAT DI' - Monthly MATDI projection (target vs projection)\n"
    "Sheet 'BW' - Bandwidth / Season Readiness (target vs LV, green/yellow/red)\n"
    "Sheet 'Vs Target' - Inventory vs MATDI target at key months (Apr, Aug, EOY)\n"
    "Sheet 'Recap2' - Tonnage recap by site (MRF1, MRF2, MRF3 comparison)\n"
)
ptg_2026 = load(FILES["ptg_master"], "2026")
lines.append(f"'2026' sheet shape: {ptg_2026.shape}")
lines.append(f"Sites: {ptg_2026['Plant'].unique().tolist()}")
lines.append(f"Months: {ptg_2026['Month'].unique().tolist()}")
lines.append(f"Attain % range: {ptg_2026['Attain'].min()} - {ptg_2026['Attain'].max()}")
lines.append(f"Sample:\n{ptg_2026.head(5).to_string()}\n")

# ---------------------------------------------------------------------------
# 7. ATTAINMENT FACTOR TABLE
# ---------------------------------------------------------------------------
lines += section("7. ATTAINMENT % TABLE")
lines.append(
    "Source: 'PTG for 2026_MRF3_Send To Plants' -> sheet 'Attain %' (73 rows)\n"
    "  Tech      -> Technology bucket\n"
    "  Attain %  -> Fraction applied to raw supply to get 'real' output\n"
    "              (accounts for yield loss, downtime, etc.)\n"
    "\n"
    "FORMULA: Case post attain = Delivered_quantity * Attain_%\n"
)
attain = load(FILES["ptg_master"], "Attain %")
lines.append(f"Sample attainment table:\n{attain[['Tech', 'Attain %']].head(15).to_string()}\n")

# ---------------------------------------------------------------------------
# 8. FULL DATA FLOW SUMMARY
# ---------------------------------------------------------------------------
lines += section("8. COMPLETE DATA FLOW SUMMARY")
lines.append("""
INPUT SOURCES                          TRANSFORMATION                OUTPUT
─────────────────────────────────────────────────────────────────────────────
SAP TMICC Table                        + Attain % by Tech           →  Cases post Attain
  (Material, Plant, Qty, Date)         × Litons per case            →  Litons post Attain
                                       ÷ Per Pallet                 →  Pallets post Attain

SAP CM/Import Goods Receipts           Same conversions above       →  (same outputs)
  (Material, Plant, GR Qty, Date)

Rapid Response Weekly Plan             Aggregate weekly→monthly     →  Forward supply
  (DU, Site, Qty, Week Date)           + Attain factor              →  Cases/Litons/Pallets

MRF Demand File                        Aggregate by Tech+Month      →  Demand Cases
  (DU, UCC, monthly cases)             × Litons per case            →  Demand Litons
                                       ÷ Per Pallet                 →  Demand Pallets

SAP MBEWH Inventory                    Group by Tech+Month          →  Starting Inventory
  (Material, Plant, TotalStock)        × Litons per case            →  Inventory Litons
                                                                     →  Inventory Pallets

Manual Adjustments (in MRF3 Demand):
  - B&J Export Pts/Bulk               Included in demand            →  Reduces net supply
  - Dependent demand (BJ pints)        Added to demand              →  Reduces net supply
  - SMOG (excess inventory)            Treated as demand            →  Inventory draw-down
  - Innovation items                   Manual case entries          →  Demand uplift

CALCULATIONS:
  MATDI = (Inventory_Cases / Rolling_12M_Demand) × 365
  DOH   = (Inventory_Cases / Monthly_Demand) × 30   [monthly view]
  Bandwidth = (Peak_Inventory - Min_Service_Inventory) / Average_Demand

FINAL OUTPUTS (sheets in PTG Master):
  → Tonnage by Site (Recap2)                   → Send to manufacturing sites
  → Pallets by Tech + Site (Pallets post Attain) → Warehousing team
  → MATDI Projection (Phasing MAT DI)           → Senior leadership / finance
  → Season Readiness / Bandwidth (BW sheet)     → S&OP stakeholders
  → RCCP Overview (Cases/Litons/Pallets by Tech) → Capacity planning

JOIN KEY MAPPING ACROSS FILES:
  File                         Column Name    Notes
  ─────────────────────────────────────────────────
  TMICC (SAP actuals)          Material       8-digit int
  CM Info (contract mfg)       Material       8-digit int
  RR Combined/Cleaned Up       Part Name/DU   8-digit int
  MBEWH Actuals (inventory)    Material       8-digit int
  MRF Demand (demand file)     DU             8-digit int
  Tech Pallet (conv table)     DU             8-digit int
  PTG '2026' sheet             Material Number 8-digit int
  PTG 'MRF3 Demand' sheet      DU             8-digit int

SITE CODE MAPPING (ValA / Plant):
  1352 = Covington
  2904 = Tulare
  5914 = St. Albans (B&J)
  1419 = Sikeston / GDI
  1717 = Caspers (CM/Yasso)
  Rhino/Hollipac, Corlu = External CM/Import sites
""")

# ---------------------------------------------------------------------------
# 9. AUTOMATION OPPORTUNITIES
# ---------------------------------------------------------------------------
lines += section("9. AUTOMATION OPPORTUNITIES")
lines.append("""
CURRENT MANUAL STEP                    AUTOMATION APPROACH
─────────────────────────────────────────────────────────────────────────────
1. Pull SAP TMICC table monthly        → SAP RFC/BAPI or OData API connector
   (copy-paste into Excel)               pipeline.extract.sap_tmicc()

2. Pull SAP MBEWH inventory            → Same SAP connector
   (copy-paste into Excel)               pipeline.extract.sap_mbewh()

3. Export Rapid Response weekly plan   → RR API or scheduled file drop
   (manual export, paste into sheets)    pipeline.extract.rapid_response()

4. Receive MRF demand file             → File watcher on shared drive / email
   (monthly Excel from demand team)      pipeline.extract.mrf_demand()

5. Apply UCCC→DU conversion            → One-time load of Tech Pallet table
   (manual VLOOKUP / manual mapping)     pipeline.transform.apply_conversion_table()

6. Apply Attainment % factors          → Config-driven YAML table
   (manual lookup per tech)              config/attainment_factors.yaml

7. Calculate Cases/Litons/Pallets      → Python: cases * litons, cases / per_pallet
   (Excel formulas, error-prone)         pipeline.calculate.convert_units()

8. Compute MATDI                       → Rolling 12-month window calculation
   (Excel formulas across rows)          pipeline.calculate.compute_matdi()

9. Build pivot summaries               → pandas groupby + pivot_table
   (manual pivot tables in Excel)        pipeline.output.generate_summary_tables()

10. Update Bandwidth/Season Readiness  → Threshold-based traffic light logic
    (manual green/yellow/red fill)       pipeline.output.season_readiness()

BIGGEST TIME SAVINGS:
  Steps 1-4 (data extraction) currently take ~1-2 days per cycle.
  Automation reduces this to minutes with scheduled pulls.
  Steps 5-10 (calculations + pivots) take ~1 day.
  Automation reduces to seconds once data is loaded.
  Net effect: Monthly 2-3 day process → <1 hour automated run.
  Enables: Weekly cadence instead of monthly.
""")

report = "\n".join(str(l) for l in lines)
with open(OUTPUT_FILE, "w") as f:
    f.write(report)

print(f"Transformation map written to: {OUTPUT_FILE}")
print(report)
