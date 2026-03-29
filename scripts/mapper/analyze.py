import io
import re
import zipfile

import pandas as pd

CANONICAL_COLUMNS = {
    "locations": [
        "id", "name", "type", "avoid_replenishment", "brands", "city",
        "classifications", "description", "location_address", "region",
        "status", "default_replenishment_lead_time",
    ],
    "catalogs": [
        "id", "name", "price", "cost", "product_id", "product_name", "size",
        "discount_price", "avoid_replenishment", "brands", "categories", "colors",
        "cost_currency", "department_id", "department_name", "description",
        "end_of_life_date", "markets", "introduction_date", "pack_constraint",
        "pictures", "price_currency", "product_description", "product_type",
        "seasons", "styles", "wh_pack_constraint", "fabric", "length",
        "sleeve_length", "actual_price", "status",
    ],
    "inventories": [
        "location_id", "sku_id", "site_qty", "source_location_id", "status_date",
        "transit_qty", "avoid_replenishment", "maximum_target", "minimum_target",
        "replenishment_lead_time", "reserved_qty", "status",
        "dtm_policy", "shipment_policy_id",
    ],
    "transactions": [
        "id", "quantity", "sale_price", "sku_id", "source_location_id",
        "target_location_id", "transaction_date", "type", "currency",
    ],
}

KNOWN_ALIASES = {
    "max_stock": "maximum_target",
    "maxstock": "maximum_target",
    "min_stock": "minimum_target",
    "minstock": "minimum_target",
    "def_repl_lead_time": "default_replenishment_lead_time",
    "def_repl_lead_type": "default_replenishment_lead_time",
    "default_replenishment_lead_type": "default_replenishment_lead_time",
    "avoid_replenishemt": "avoid_replenishment",  # common typo
    "target_market": "markets",
    "color": "colors",
}

# File detection patterns per section
_SECTION_PATTERNS = {
    "locations": [
        re.compile(r'^locations?\.csv$', re.IGNORECASE),
        re.compile(r'^.*location.*\.csv$', re.IGNORECASE),
    ],
    "catalogs": [
        re.compile(r'^catalogs?\.csv$', re.IGNORECASE),
        re.compile(r'^.*catalog.*\.csv$', re.IGNORECASE),
    ],
    "inventories": [
        re.compile(r'^inventories\.csv$', re.IGNORECASE),
        re.compile(r'^inventory\.csv$', re.IGNORECASE),
        re.compile(r'^input_inventor.*\.csv$', re.IGNORECASE),
        re.compile(r'^inventor.*\.csv$', re.IGNORECASE),
        re.compile(r'^.*inventor.*\.csv$', re.IGNORECASE),
    ],
    "transactions": [
        re.compile(r'^transactions?\.csv$', re.IGNORECASE),
        re.compile(r'^.*transaction.*\.csv$', re.IGNORECASE),
    ],
}


def _normalize(col: str) -> str:
    return col.strip().lower().replace(" ", "_")


def _find_entry(zip_names: list, section: str) -> str | None:
    patterns = _SECTION_PATTERNS[section]
    for pattern in patterns:
        for name in zip_names:
            basename = name.split("/")[-1]
            if pattern.match(basename):
                return name
    return None


def analyze_zip(zip_path: str) -> dict:
    result = {}
    with zipfile.ZipFile(zip_path) as zf:
        zip_names = zf.namelist()
        for section, canonical_list in CANONICAL_COLUMNS.items():
            entry = _find_entry(zip_names, section)
            if entry is None:
                result[section] = {
                    "found": False,
                    "filename": None,
                    "matched": {},
                    "unmatched_csv": [],
                    "remaining_canonical": list(canonical_list),
                    "all_csv_cols": [],
                }
                continue

            filename = entry.split("/")[-1]
            try:
                with zf.open(entry) as f:
                    df = pd.read_csv(
                        io.TextIOWrapper(f, encoding="utf-8-sig"),
                        dtype=str,
                        nrows=0,
                    )
                all_csv_cols = list(df.columns)
            except Exception as e:
                result[section] = {
                    "found": False,
                    "filename": filename,
                    "matched": {},
                    "unmatched_csv": [],
                    "remaining_canonical": list(canonical_list),
                    "all_csv_cols": [],
                }
                continue

            matched = {}           # canonical -> csv_col
            used_canonical = set()
            used_csv = set()

            for csv_col in all_csv_cols:
                normalized = _normalize(csv_col)
                # Try known alias first
                if normalized in KNOWN_ALIASES:
                    canonical = KNOWN_ALIASES[normalized]
                    if canonical in canonical_list and canonical not in used_canonical:
                        matched[canonical] = csv_col
                        used_canonical.add(canonical)
                        used_csv.add(csv_col)
                        continue
                # Try exact normalized match
                if normalized in canonical_list and normalized not in used_canonical:
                    matched[normalized] = csv_col
                    used_canonical.add(normalized)
                    used_csv.add(csv_col)

            unmatched_csv = [c for c in all_csv_cols if c not in used_csv]
            remaining_canonical = [c for c in canonical_list if c not in used_canonical]

            result[section] = {
                "found": True,
                "filename": filename,
                "matched": matched,
                "unmatched_csv": unmatched_csv,
                "remaining_canonical": remaining_canonical,
                "all_csv_cols": all_csv_cols,
            }

    return result
