# Magnum S&OP Automation — Client Pitch

## The Problem: 2-3 Days of Manual Work Every Month

Today, every S&OP cycle starts the same way: someone opens 6 spreadsheets,
copies data from SAP and Rapid Response, runs VLOOKUPs, adjusts formulas by
hand, fixes pivot tables, and manually fills in green/yellow/red cells. By the
time the PTG file lands in stakeholders' inboxes, the data is already weeks old.

---

## Before vs After

| Step | Today (Manual) | Automated |
|---|---|---|
| Pull SAP TMICC actuals | ~4 hrs (login, export, paste) | **Seconds** (API pull or file watcher) |
| Pull SAP MBEWH inventory | ~2 hrs | **Seconds** |
| Export Rapid Response plan | ~3 hrs (manual export + cleanup) | **Seconds** |
| Receive & import MRF demand file | ~1 hr | **Seconds** (file watcher on shared drive) |
| Apply UCCC→DU conversion (VLOOKUP) | ~2 hrs | **< 1 second** (join on DU key) |
| Apply attainment % by tech | ~1 hr (manual lookup per row) | **< 1 second** (config YAML) |
| Calculate cases/litons/pallets | ~2 hrs (formula audit + fixes) | **< 1 second** (vectorized Python) |
| Compute MATDI rolling window | ~1 hr (Excel row formulas) | **< 1 second** (pandas rolling) |
| Build pivot summaries | ~2 hrs (manual pivot refresh) | **< 1 second** (groupby + pivot_table) |
| Season readiness traffic lights | ~1 hr (manual fill) | **< 1 second** (threshold logic) |
| **Total** | **~19 hrs / cycle** | **< 5 minutes** |

**Time saved per cycle: ~18+ hours**
**Current cadence: Monthly → Achievable: Weekly**

---

## What We Built

### 1. Data Pipeline (`pipeline/`)

Five modules that replace the manual Excel process end-to-end:

```
extract.py      → reads all source xlsx files (or future API connectors)
transform.py    → unit conversions, attainment, litons, pallets
consolidate.py  → merges supply + demand + inventory
calculate.py    → MATDI, inventory projection, bandwidth
output.py       → Excel workbook + CSVs + season readiness report
```

**Run the full pipeline:**
```bash
uv run python main.py
```
Generates `output/PTG_Automated_Output.xlsx` and CSV files in under 5 minutes.

### 2. Config-Driven Adjustments (`config/`)

Manual assumptions that previously lived in hidden Excel cells are now
transparent, version-controlled YAML files:

- `conversion_tables.yaml` — DU→Tech mappings, site codes
- `manual_adjustments.yaml` — attainment %, MATDI targets, bandwidth thresholds,
  manual demand add-ons (exports, dependent demand, SMOG)

Changing an attainment % from 94% to 92% for 48oz now takes **3 seconds**
(edit one YAML value) instead of hunting through a formula-heavy spreadsheet.

### 3. Interactive Dashboard (`dashboard.py`)

A live planning tool replacing static Excel outputs:

```bash
uv run streamlit run dashboard.py
```

**5 tabs, all driven from actual client data:**

| Tab | What it shows |
|---|---|
| 🚦 Season Readiness | Traffic-light bandwidth by technology — at a glance |
| 📦 Tonnage by Site | Monthly liton projections per manufacturing site |
| 🏗 Pallet Positions | Supply & demand pallets by tech, monthly |
| 📊 MATDI Trend | Rolling MATDI vs targets at Apr / Aug / Dec |
| ⚖ RCCP Overview | Supply vs Demand vs Inventory for any technology |

**Interactive override panel:** Adjust attainment % by tech in the sidebar
and all charts update instantly — no more "let me rebuild the Excel and send
a new file."

---

## Key Findings From the Data

From profiling the client's actual files:

- **Primary join key**: `DU` / `Material` — 8-digit integer — consistent across all 6 files
- **599 active DUs** in the conversion table across 24 technology buckets
- **22.5 million cases** of inventory on hand at Feb 2026 snapshot
- **Attainment range**: 85% (2.4 Gal bulk) to 96% (most technologies)
- **7 contract manufacturers** feeding into the supply plan (Caspers, Rhino, GDI, Incom, etc.)
- **Weekly granularity** already exists in Rapid Response — the bottleneck is the
  monthly manual aggregation, not the source data

---

## The Path to Weekly Planning

The biggest barrier to weekly cycles is not the calculations — it's the
**4 manual extraction steps** that take 1-2 days each month. With:

1. An SAP RFC/OData connector for TMICC and MBEWH tables
2. A Rapid Response scheduled export (or API)
3. A shared-drive file watcher for the MRF demand file

…the entire pipeline runs automatically on a schedule. The team shifts from
**building the spreadsheet** to **reviewing the dashboard and adjusting assumptions**.

---

## Recommended Next Steps

1. **Pilot**: Run this pipeline in parallel with the next MRF cycle to validate numbers
2. **SAP connector**: Work with IT to expose TMICC/MBEWH via RFC or OData
3. **RR API or SFTP**: Automate the Rapid Response extract
4. **Demand file integration**: Set up file watcher on the MRF shared drive
5. **Dashboard hosting**: Deploy Streamlit on internal server or Streamlit Cloud
6. **Weekly cadence**: Once steps 3-4 are live, schedule a weekly pipeline run

---

## File Structure

```
magnum/
├── main.py                  ← run the full pipeline
├── dashboard.py             ← run the Streamlit dashboard
├── explore_data.py          ← data profiling (Phase 1)
├── map_transformations.py   ← transformation documentation (Phase 2)
├── pipeline/
│   ├── extract.py           ← load source files
│   ├── transform.py         ← unit conversions
│   ├── consolidate.py       ← merge supply/demand/inventory
│   ├── calculate.py         ← MATDI, projections, bandwidth
│   └── output.py            ← Excel + CSV + reports
├── config/
│   ├── conversion_tables.yaml
│   └── manual_adjustments.yaml
├── data/                    ← client xlsx files (unchanged)
└── output/                  ← generated outputs
```
