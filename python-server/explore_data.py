"""
Phase 1: Data Exploration Script
Profiles all xlsx files in the data/ folder:
  - Sheet names
  - Column headers, dtypes, shape
  - First 5 rows per sheet
  - Null counts
  - Potential join key candidates
Output is written to explore_output.txt for review.
"""

import sys
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = Path(__file__).parent / "explore_output.txt"

# Known domain keywords that likely represent join keys
JOIN_KEY_HINTS = [
    "uccc", "uc cc", "item", "material", "sku", "technology", "tech",
    "site", "plant", "location", "month", "period", "date", "year",
    "du", "design unit", "demand unit", "mrf", "code", "key", "id",
]


def is_likely_join_key(col_name: str) -> bool:
    name_lower = str(col_name).lower()
    return any(hint in name_lower for hint in JOIN_KEY_HINTS)


def profile_sheet(df: pd.DataFrame, file_name: str, sheet_name: str) -> list[str]:
    lines = []
    lines.append(f"\n  Sheet: '{sheet_name}'")
    lines.append(f"  Shape: {df.shape[0]} rows x {df.shape[1]} columns")

    if df.empty:
        lines.append("  (empty sheet)")
        return lines

    lines.append(f"\n  Columns ({len(df.columns)}):")
    for col in df.columns:
        dtype = str(df[col].dtype)
        null_count = int(df[col].isna().sum())
        null_pct = round(null_count / len(df) * 100, 1) if len(df) > 0 else 0
        key_flag = " <-- POTENTIAL JOIN KEY" if is_likely_join_key(col) else ""
        lines.append(f"    [{dtype:>12}]  {str(col):<55}  nulls: {null_count} ({null_pct}%){key_flag}")

    lines.append(f"\n  Sample data (first 5 rows):")
    try:
        sample = df.head(5).to_string(max_cols=20, max_colwidth=30)
        for row in sample.split("\n"):
            lines.append(f"    {row}")
    except Exception as e:
        lines.append(f"    (could not render sample: {e})")

    # Identify numeric columns and their ranges
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if num_cols:
        lines.append(f"\n  Numeric column ranges (non-null):")
        for col in num_cols[:20]:  # cap at 20 numeric cols
            non_null = df[col].dropna()
            if len(non_null) > 0:
                lines.append(
                    f"    {str(col):<55}  min={non_null.min():.2f}  max={non_null.max():.2f}  mean={non_null.mean():.2f}"
                )

    return lines


def profile_file(path: Path) -> list[str]:
    lines = []
    lines.append("\n" + "=" * 80)
    lines.append(f"FILE: {path.name}")
    lines.append(f"Size: {path.stat().st_size / 1024:.1f} KB")
    lines.append("=" * 80)

    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
        sheet_names = xl.sheet_names
        lines.append(f"Sheets ({len(sheet_names)}): {sheet_names}")

        for sheet in sheet_names:
            try:
                df = xl.parse(sheet, header=0)
                # Try to find the real header row if first row is empty/metadata
                if df.columns.str.contains("^Unnamed").all() or df.shape[1] <= 1:
                    for header_row in range(1, 5):
                        df_retry = xl.parse(sheet, header=header_row)
                        if not df_retry.columns.str.contains("^Unnamed").all() and df_retry.shape[1] > 1:
                            lines.append(f"  (re-parsed sheet '{sheet}' with header_row={header_row})")
                            df = df_retry
                            break

                profile_lines = profile_sheet(df, path.name, sheet)
                lines.extend(profile_lines)
            except Exception as e:
                lines.append(f"\n  Sheet '{sheet}': ERROR reading -- {e}")

    except Exception as e:
        lines.append(f"ERROR opening file: {e}")

    return lines


def main():
    xlsx_files = sorted(DATA_DIR.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No xlsx files found in {DATA_DIR}")
        sys.exit(1)

    print(f"Found {len(xlsx_files)} xlsx files in {DATA_DIR}")
    all_lines = [
        "MAGNUM S&OP DATA EXPLORATION REPORT",
        f"Data directory: {DATA_DIR}",
        f"Files found: {len(xlsx_files)}",
    ]

    for path in xlsx_files:
        print(f"  Profiling: {path.name} ...")
        file_lines = profile_file(path)
        all_lines.extend(file_lines)

    report = "\n".join(all_lines)

    with open(OUTPUT_FILE, "w") as f:
        f.write(report)

    print(f"\nReport written to: {OUTPUT_FILE}")
    print(report)


if __name__ == "__main__":
    main()
