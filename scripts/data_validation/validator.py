import io
import os
import re
import tempfile
import zipfile

import pandas as pd
import yaml

# ── Expected files ────────────────────────────────────────────────────────────
EXPECTED_FILES = ["catalogs.csv", "locations.csv", "inventories.csv", "transactions.csv"]

# ── Mandatory columns (canonical name, expected type) ────────────────────────
# Types: "str", "float", "date"

CATALOGS_MANDATORY_COLS = [
    ("id",         "str"),
    ("name",       "str"),
    ("product_id", "str"),
    ("price",      "float"),
    ("cost",       "float"),
]

LOCATIONS_MANDATORY_COLS = [
    ("id",   "str"),
    ("name", "str"),
    ("type", "str"),
]

LOCATION_VALID_TYPES = {"store", "warehouse", "ecomers", "vandor"}

TRANSACTIONS_MANDATORY_COLS = [
    ("id",                 "str"),
    ("sku_id",             "str"),
    ("source_location_id", "str"),
    ("target_location_id", "str"),
    ("quantity",           "float"),
    ("type",               "str"),
    ("transaction_date",   "date"),
]

TRANSACTION_VALID_TYPES = {"in", "out", "sale", "return"}

INVENTORIES_MANDATORY_COLS = [
    ("location_id",        "str"),
    ("sku_id",             "str"),
    ("source_location_id", "str"),
    ("transit_qty",        "float"),
    ("site_qty",           "float"),
    ("status_date",        "date"),
]

# ── Fuzzy filename patterns ───────────────────────────────────────────────────

_CATALOG_PATTERNS = [
    re.compile(r"^catalogs\.csv$",   re.IGNORECASE),
    re.compile(r"^catalog\.csv$",    re.IGNORECASE),
    re.compile(r"^.*catalog.*\.csv$", re.IGNORECASE),
]

_LOCATION_PATTERNS = [
    re.compile(r"^locations\.csv$",    re.IGNORECASE),
    re.compile(r"^location\.csv$",     re.IGNORECASE),
    re.compile(r"^.*location.*\.csv$", re.IGNORECASE),
]

_TRANSACTION_PATTERNS = [
    re.compile(r"^transactions\.csv$",     re.IGNORECASE),
    re.compile(r"^transaction\.csv$",      re.IGNORECASE),
    re.compile(r"^.*transaction.*\.csv$",  re.IGNORECASE),
]

_INVENTORY_PATTERNS = [
    re.compile(r"^inventories\.csv$",      re.IGNORECASE),
    re.compile(r"^inventory\.csv$",        re.IGNORECASE),
    re.compile(r"^input_inventor.*\.csv$", re.IGNORECASE),
    re.compile(r"^inventor.*\.csv$",       re.IGNORECASE),
]


# ── Generic helpers ───────────────────────────────────────────────────────────

def _find_in_zip(zip_names, target):
    """Return the first zip entry whose basename exactly matches *target* (case-insensitive)."""
    for name in zip_names:
        if name.split("/")[-1].lower() == target.lower():
            return name
    return None


def _find_file_fuzzy(zip_names, patterns):
    """
    Return (zip_entry, actual_basename) using the ordered list of compiled regex patterns.
    Returns (None, None) if nothing matched.
    """
    for pattern in patterns:
        for name in zip_names:
            basename = name.split("/")[-1]
            if pattern.match(basename):
                return name, basename
    return None, None


def _detect_bom(zf, entry):
    """Return True if the file starts with a UTF-8 BOM (0xEF 0xBB 0xBF)."""
    with zf.open(entry) as f:
        return f.read(3)[:3] == b"\xef\xbb\xbf"


def _load_mapper(zf, zip_names):
    """
    Find input_file_mapper.yml inside the ZIP and return the full parsed dict.
    Returns None if not found or unparseable.
    """
    for name in zip_names:
        basename = name.split("/")[-1].lower()
        if basename in ("input_file_mapper.yml", "input_file_mapper.yaml"):
            try:
                with zf.open(name) as f:
                    return yaml.safe_load(f)
            except Exception:
                return None
    return None


def _get_mapper_column(mapper, section, canonical_name):
    """
    Look up the actual CSV column name for *canonical_name* under
    mapper[section]['mapping'].
    """
    if mapper is None:
        return None
    section_data = mapper.get(section) or {}
    mapping = section_data.get("mapping") or {}
    return mapping.get(canonical_name)


def _basic_file_checks(df, filename):
    """Run per-file structure checks. Returns list of issue dicts."""
    issues = []
    if df.empty:
        issues.append({"level": "error", "msg": "File is empty (0 rows)"})
    if df.columns.duplicated().any():
        dupes = list(df.columns[df.columns.duplicated()])
        issues.append({"level": "error", "msg": f"Duplicate column names: {dupes}"})
    return issues


def _write_csv(df, session_dir, filename):
    """Write *df* to session_dir/filename. Returns basename on success, None on failure."""
    if not session_dir:
        return None
    try:
        path = os.path.join(session_dir, filename)
        df.to_csv(path, index=False)
        return filename
    except Exception:
        return None


# ── Type-casting helpers ──────────────────────────────────────────────────────

def _check_column_type(series, col_name, canonical, expected_type):
    """
    Validate every non-null value in *series* can be cast to *expected_type*.
    Returns a list of issue dicts.
    """
    issues = []
    non_null = series.dropna()
    if non_null.empty:
        return issues  # already caught by null check

    if expected_type == "str":
        bad = non_null.astype(str).str.match(r"^\d+\.0$")
        bad_count = bad.sum()
        if bad_count:
            examples = non_null.astype(str)[bad].head(3).tolist()
            issues.append({
                "level": "warning",
                "msg": (
                    f'Column "{col_name}" (expected string) has {bad_count:,} value(s) '
                    f'ending in ".0" (e.g. {examples}) — likely read as float. '
                    f'Ensure the source data has no trailing ".0".'
                ),
            })

    elif expected_type == "float":
        try:
            pd.to_numeric(non_null, errors="raise")
        except (ValueError, TypeError):
            mask = pd.to_numeric(non_null, errors="coerce").isna()
            bad_vals = non_null[mask].head(3).tolist()
            issues.append({
                "level": "error",
                "msg": (
                    f'Column "{col_name}" (expected numeric/float) contains non-numeric values: '
                    f'{bad_vals}.'
                ),
            })

    elif expected_type == "date":
        # Enforce strict %Y-%m-%d format
        _date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        str_vals = non_null.astype(str)
        wrong_format = ~str_vals.str.match(_date_re)
        wrong_count = wrong_format.sum()
        if wrong_count:
            bad_vals = str_vals[wrong_format].head(3).tolist()
            issues.append({
                "level": "error",
                "msg": (
                    f'Column "{col_name}" (expected date) has {wrong_count:,} value(s) '
                    f'not in YYYY-MM-DD format (e.g. {bad_vals}). '
                    f'All dates must use the format "%Y-%m-%d".'
                ),
            })
        else:
            # Format is correct — also validate that they are real calendar dates
            converted = pd.to_datetime(non_null, format="%Y-%m-%d", errors="coerce")
            bad_count = converted.isna().sum()
            if bad_count:
                bad_vals = non_null[converted.isna()].head(3).tolist()
                issues.append({
                    "level": "error",
                    "msg": (
                        f'Column "{col_name}" (expected date) contains {bad_count:,} '
                        f'invalid date value(s): {bad_vals}.'
                    ),
                })

    return issues


# ── Shared: mandatory column loop ─────────────────────────────────────────────

def _validate_mandatory_columns(df, mandatory_cols, mapper, mapper_section, zf, zip_names):
    """
    Resolve and validate each mandatory column.
    Returns (canonical_map, mapper_used, issues, mapper_loaded).
    """
    cols_lower = {c.lower(): c for c in df.columns}
    canonical_map = {}
    issues = []
    mapper_used = False

    for canonical, expected_type in mandatory_cols:
        actual_col = cols_lower.get(canonical.lower())

        if actual_col is None:
            if mapper is None:
                mapper = _load_mapper(zf, zip_names)
            mapped = _get_mapper_column(mapper, mapper_section, canonical)
            if mapped:
                actual_col = cols_lower.get(mapped.lower())
                if actual_col:
                    mapper_used = True
                    issues.append({
                        "level": "warning",
                        "msg": (
                            f'Column "{canonical}" not found directly; '
                            f'resolved via mapper as "{actual_col}".'
                        ),
                    })

        if actual_col is None:
            issues.append({
                "level": "error",
                "msg": (
                    f'Mandatory column "{canonical}" is missing'
                    + (" (checked input_file_mapper.yml — not resolved)." if mapper is not None else ".")
                ),
            })
            canonical_map[canonical] = None
            continue

        canonical_map[canonical] = actual_col
        series = df[actual_col]

        # Null check
        null_count = series.isna().sum()
        if null_count == len(df):
            issues.append({
                "level": "error",
                "msg": f'Column "{actual_col}" ("{canonical}") contains no data — all values are null.',
            })
        elif null_count > 0:
            pct = round(null_count / len(df) * 100, 1)
            issues.append({
                "level": "error",
                "msg": (
                    f'Column "{actual_col}" ("{canonical}") has {null_count:,} null value(s) '
                    f'({pct}%) — mandatory columns must have no nulls.'
                ),
            })

        # Type check
        issues.extend(_check_column_type(series, actual_col, canonical, expected_type))

    return canonical_map, mapper_used, issues, mapper


def _export_null_rows(df, canonical_map, session_dir, prefix="null_values"):
    """Export rows where any resolved mandatory column is null. Returns filename or None."""
    resolved_cols = [c for c in canonical_map.values() if c is not None and c in df.columns]
    if not resolved_cols:
        return None
    mask = df[resolved_cols].isna().any(axis=1)
    count = mask.sum()
    if not count:
        return None
    return _write_csv(df[mask], session_dir, f"{prefix}_{count}_rows.csv")


# ── Catalogs-specific validation ──────────────────────────────────────────────

def _validate_catalogs(zf, zip_names, session_dir=None):
    """
    Full validation for the catalogs CSV.

    Extra keys vs generic: actual_filename, bom, canonical_map, mapper_used,
                           nulls_file, zero_values_file, duplicates_file
    """
    result = {
        "found": False,
        "actual_filename": None,
        "bom": None,
        "rows": 0,
        "columns": [],
        "issues": [],
        "canonical_map": {},
        "mapper_used": False,
        "nulls_file": None,
        "zero_values_file": None,
        "duplicates_file": None,
        "color_conflict_file": None,
        "size_dup_file": None,
        "_df": None,
    }

    entry, basename = _find_file_fuzzy(zip_names, _CATALOG_PATTERNS)

    if entry is None:
        result["issues"].append({
            "level": "error",
            "msg": "catalogs.csv not found in ZIP (also tried fuzzy patterns: catalog.csv, *catalog*.csv)",
        })
        return result

    result["found"] = True
    result["actual_filename"] = basename

    if basename.lower() != "catalogs.csv":
        result["issues"].append({
            "level": "warning",
            "msg": f'File found as "{basename}" — rename to "catalogs.csv" for best compatibility.',
        })

    # BOM
    has_bom = _detect_bom(zf, entry)
    result["bom"] = has_bom
    if has_bom:
        result["issues"].append({
            "level": "warning",
            "msg": "File contains a UTF-8 BOM (Byte Order Mark). Remove BOM for cleaner processing.",
        })

    # Load CSV
    try:
        with zf.open(entry) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"))
    except Exception as e:
        result["issues"].append({"level": "error", "msg": f"Failed to read CSV: {e}"})
        return result

    result["_df"] = df
    result["rows"] = len(df)
    result["columns"] = list(df.columns)
    result["issues"].extend(_basic_file_checks(df, basename))

    # Mandatory columns
    canonical_map, mapper_used, col_issues, _ = _validate_mandatory_columns(
        df, CATALOGS_MANDATORY_COLS, None, "catalogs", zf, zip_names
    )
    result["canonical_map"] = canonical_map
    result["mapper_used"] = mapper_used
    result["issues"].extend(col_issues)

    # Null rows export
    result["nulls_file"] = _export_null_rows(df, canonical_map, session_dir)

    # ── price / cost zero-or-null check ──────────────────────────────────────
    price_col = canonical_map.get("price")
    cost_col  = canonical_map.get("cost")

    zero_null_mask = pd.Series(False, index=df.index)
    bad_cols = []

    for col, label in [(price_col, "price"), (cost_col, "cost")]:
        if col and col in df.columns:
            numeric = pd.to_numeric(df[col], errors="coerce")
            col_mask = numeric.isna() | (numeric == 0)
            bad_count = col_mask.sum()
            if bad_count:
                bad_cols.append(f'"{col}" ({label}): {bad_count:,} row(s)')
                zero_null_mask |= col_mask

    if bad_cols:
        total_bad = zero_null_mask.sum()
        result["issues"].append({
            "level": "warning",
            "msg": (
                f'price/cost should not be 0 or empty — '
                f'{"; ".join(bad_cols)}.'
            ),
        })
        result["zero_values_file"] = _write_csv(
            df[zero_null_mask], session_dir,
            f"zero_or_null_price_cost_{total_bad}_rows.csv"
        )

    # ── Duplicate id check ────────────────────────────────────────────────────
    id_col = canonical_map.get("id")
    if id_col and id_col in df.columns:
        dup_mask = df.duplicated(subset=[id_col], keep=False)
        dup_count = dup_mask.sum()
        if dup_count:
            result["issues"].append({
                "level": "error",
                "msg": (
                    f'Found {dup_count:,} rows with duplicate "{id_col}" values. '
                    f'Each catalog ID must be unique.'
                ),
            })
            result["duplicates_file"] = _write_csv(
                df[dup_mask], session_dir,
                f"duplicate_catalog_id_{dup_count}_rows.csv"
            )

    # ── Optional column checks (sku_name, color) ─────────────────────────────
    cols_lower_cat = {c.lower(): c for c in df.columns}
    product_id_col = canonical_map.get("product_id")

    # product_id == sku_name (if sku_name column present)
    sku_name_col = cols_lower_cat.get("sku_name")
    if product_id_col and sku_name_col and product_id_col in df.columns:
        both = df[product_id_col].notna() & df[sku_name_col].notna()
        mismatch = both & (df[product_id_col].astype(str) != df[sku_name_col].astype(str))
        mismatch_count = mismatch.sum()
        total = int(both.sum())
        if mismatch_count:
            pct = round(mismatch_count / total * 100, 1) if total else 0
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'{mismatch_count:,} of {total:,} rows ({pct}%) have '
                    f'product_id ≠ sku_name. product_id is expected to match sku_name.'
                ),
            })

    # product_id should contain the product's color (if color column present)
    color_col = cols_lower_cat.get("color")
    if product_id_col and color_col and product_id_col in df.columns:
        both = df[product_id_col].notna() & df[color_col].notna()
        mismatch = both & ~df.apply(
            lambda row: str(row[color_col]).strip().lower()
                        in str(row[product_id_col]).strip().lower(),
            axis=1,
        )
        mismatch_count = mismatch.sum()
        total = int(both.sum())
        if mismatch_count:
            pct = round(mismatch_count / total * 100, 1) if total else 0
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'{mismatch_count:,} of {total:,} rows ({pct}%) have a product_id '
                    f'that does not contain the product\'s color value. '
                    f'product_id is expected to reference the color.'
                ),
            })

    # ── Check 1: product_id color consistency ─────────────────────────────────
    # All SKUs sharing the same product_id must have the same color.
    if product_id_col and color_col and product_id_col in df.columns and color_col in df.columns:
        sub = df[[product_id_col, color_col]].dropna(subset=[product_id_col])
        color_groups = (
            sub.groupby(product_id_col, sort=False)[color_col]
            .apply(lambda s: sorted({str(v).strip() for v in s.dropna()}))
        )
        conflicts = color_groups[color_groups.apply(len) > 1]
        if not conflicts.empty:
            n = len(conflicts)
            sample = list(conflicts.items())[:10]
            details = "; ".join(
                f'"{pid}" → [{", ".join(colors)}]'
                for pid, colors in sample
            )
            if n > 10:
                details += f" … and {n - 10} more"
            result["issues"].append({
                "level": "error",
                "msg": (
                    f'{n:,} product_id(s) have inconsistent colors — '
                    f'all SKUs with the same product_id must share the same color. '
                    f'Conflicts: {details}.'
                ),
            })
            bad_pids = set(conflicts.index.astype(str))
            bad_mask = df[product_id_col].astype(str).isin(bad_pids)
            result["color_conflict_file"] = _write_csv(
                df[bad_mask], session_dir,
                f"product_color_conflict_{n}_product_ids.csv"
            )

    # ── Check 2: product_id + size uniqueness ─────────────────────────────────
    # Each size value must appear at most once per product_id.
    size_col = cols_lower_cat.get("size")
    if product_id_col and size_col and product_id_col in df.columns and size_col in df.columns:
        sub = df[[product_id_col, size_col]].dropna(subset=[product_id_col, size_col])
        counts = sub.groupby([product_id_col, size_col]).size().reset_index(name="count")
        dups = counts[counts["count"] > 1]
        if not dups.empty:
            n = len(dups)
            sample = dups.head(10)
            details = "; ".join(
                f'"{row[product_id_col]}" has size "{row[size_col]}" × {row["count"]}'
                for _, row in sample.iterrows()
            )
            if n > 10:
                details += f" … and {n - 10} more"
            result["issues"].append({
                "level": "error",
                "msg": (
                    f'{n:,} product_id/size combination(s) duplicated — '
                    f'each size must appear only once per product_id. '
                    f'Duplicates: {details}.'
                ),
            })
            bad_key_set = {
                f"{p}\x00{s}"
                for p, s in zip(dups[product_id_col].astype(str), dups[size_col].astype(str))
            }
            key_series = df[product_id_col].astype(str).str.cat(
                df[size_col].astype(str), sep="\x00"
            )
            bad_mask = df[product_id_col].notna() & df[size_col].notna() & key_series.isin(bad_key_set)
            result["size_dup_file"] = _write_csv(
                df[bad_mask], session_dir,
                f"duplicate_product_size_{n}_combinations.csv"
            )

    # ── Check 3: sku_id == product_id warning ─────────────────────────────────
    if id_col and product_id_col and id_col in df.columns and product_id_col in df.columns:
        both = df[id_col].notna() & df[product_id_col].notna()
        eq_mask = both & (
            df[id_col].astype(str).str.strip() == df[product_id_col].astype(str).str.strip()
        )
        eq_count = int(eq_mask.sum())
        if eq_count:
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'{eq_count:,} row(s) where sku_id (id) equals product_id. '
                    f'SKU IDs are typically distinct from product IDs.'
                ),
            })

    return result


# ── Locations-specific validation ────────────────────────────────────────────

def _validate_locations(zf, zip_names, session_dir=None):
    """
    Full validation for the locations CSV.

    Extra keys vs generic: actual_filename, bom, canonical_map, mapper_used,
                           nulls_file, duplicates_file
    """
    result = {
        "found": False,
        "actual_filename": None,
        "bom": None,
        "rows": 0,
        "columns": [],
        "issues": [],
        "canonical_map": {},
        "mapper_used": False,
        "nulls_file": None,
        "duplicates_file": None,
        "_df": None,
    }

    entry, basename = _find_file_fuzzy(zip_names, _LOCATION_PATTERNS)

    if entry is None:
        result["issues"].append({
            "level": "error",
            "msg": "locations.csv not found in ZIP (also tried fuzzy patterns: location.csv, *location*.csv)",
        })
        return result

    result["found"] = True
    result["actual_filename"] = basename

    if basename.lower() != "locations.csv":
        result["issues"].append({
            "level": "warning",
            "msg": f'File found as "{basename}" — rename to "locations.csv" for best compatibility.',
        })

    # BOM
    has_bom = _detect_bom(zf, entry)
    result["bom"] = has_bom
    if has_bom:
        result["issues"].append({
            "level": "warning",
            "msg": "File contains a UTF-8 BOM (Byte Order Mark). Remove BOM for cleaner processing.",
        })

    # Load CSV
    try:
        with zf.open(entry) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"))
    except Exception as e:
        result["issues"].append({"level": "error", "msg": f"Failed to read CSV: {e}"})
        return result

    result["_df"] = df
    result["rows"] = len(df)
    result["columns"] = list(df.columns)
    result["issues"].extend(_basic_file_checks(df, basename))

    # Mandatory columns
    canonical_map, mapper_used, col_issues, _ = _validate_mandatory_columns(
        df, LOCATIONS_MANDATORY_COLS, None, "locations", zf, zip_names
    )
    result["canonical_map"] = canonical_map
    result["mapper_used"] = mapper_used
    result["issues"].extend(col_issues)

    # Null rows export
    result["nulls_file"] = _export_null_rows(df, canonical_map, session_dir)

    # ── type column checks ────────────────────────────────────────────────────
    type_col = canonical_map.get("type")
    if type_col and type_col in df.columns:
        non_null_types = df[type_col].dropna().astype(str)

        # Warning: any uppercase letters
        has_caps = non_null_types.str.contains(r"[A-Z]", regex=True)
        caps_count = has_caps.sum()
        if caps_count:
            examples = non_null_types[has_caps].head(3).tolist()
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'Column "{type_col}" has {caps_count:,} value(s) with uppercase letters '
                    f'(e.g. {examples}). Values should be lowercase.'
                ),
            })

        # Warning: values not in allowed set (checked after lowercasing)
        valid = LOCATION_VALID_TYPES
        invalid_mask = ~non_null_types.str.lower().isin(valid)
        invalid_vals = non_null_types[invalid_mask].unique().tolist()
        if invalid_vals:
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'Column "{type_col}" contains unexpected value(s): {invalid_vals}. '
                    f'Expected one of: {sorted(valid)}.'
                ),
            })

    # ── Duplicate id check ────────────────────────────────────────────────────
    id_col = canonical_map.get("id")
    if id_col and id_col in df.columns:
        dup_mask = df.duplicated(subset=[id_col], keep=False)
        dup_count = dup_mask.sum()
        if dup_count:
            result["issues"].append({
                "level": "error",
                "msg": (
                    f'Found {dup_count:,} rows with duplicate "{id_col}" values. '
                    f'Each location ID must be unique.'
                ),
            })
            result["duplicates_file"] = _write_csv(
                df[dup_mask], session_dir,
                f"duplicate_location_id_{dup_count}_rows.csv"
            )

    return result


# ── Inventories-specific validation ──────────────────────────────────────────

def _validate_inventories(zf, zip_names, session_dir=None):
    """
    Full validation for the inventories CSV.

    Extra keys vs generic: actual_filename, bom, canonical_map, mapper_used,
                           nulls_file, duplicates_file
    """
    result = {
        "found": False,
        "actual_filename": None,
        "bom": None,
        "rows": 0,
        "columns": [],
        "issues": [],
        "canonical_map": {},
        "mapper_used": False,
        "duplicates_file": None,
        "nulls_file": None,
        "reserved_qty_file": None,
        "site_qty_neg_file": None,
        "avoid_replenishment_file": None,
        "min_max_stock_file": None,
        "_df": None,
    }

    entry, basename = _find_file_fuzzy(zip_names, _INVENTORY_PATTERNS)

    if entry is None:
        result["issues"].append({
            "level": "error",
            "msg": (
                "inventories.csv not found in ZIP "
                "(also tried fuzzy patterns: inventory.csv, input_inventor*.csv)"
            ),
        })
        return result

    result["found"] = True
    result["actual_filename"] = basename

    if basename.lower() != "inventories.csv":
        result["issues"].append({
            "level": "warning",
            "msg": f'File found as "{basename}" — rename to "inventories.csv" for best compatibility.',
        })

    # BOM
    has_bom = _detect_bom(zf, entry)
    result["bom"] = has_bom
    if has_bom:
        result["issues"].append({
            "level": "warning",
            "msg": "File contains a UTF-8 BOM (Byte Order Mark). Remove BOM for cleaner processing.",
        })

    # Load CSV
    try:
        with zf.open(entry) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"))
    except Exception as e:
        result["issues"].append({"level": "error", "msg": f"Failed to read CSV: {e}"})
        return result

    result["_df"] = df
    result["rows"] = len(df)
    result["columns"] = list(df.columns)
    result["issues"].extend(_basic_file_checks(df, basename))

    # Mandatory columns
    canonical_map, mapper_used, col_issues, _ = _validate_mandatory_columns(
        df, INVENTORIES_MANDATORY_COLS, None, "inventories", zf, zip_names
    )
    result["canonical_map"] = canonical_map
    result["mapper_used"] = mapper_used
    result["issues"].extend(col_issues)

    # Null rows export
    result["nulls_file"] = _export_null_rows(df, canonical_map, session_dir)

    # ── transit_qty < 0 warning ──────────────────────────────────────────────
    transit_col = canonical_map.get("transit_qty")
    if transit_col and transit_col in df.columns:
        numeric_transit = pd.to_numeric(df[transit_col], errors="coerce")
        neg_count = (numeric_transit < 0).sum()
        if neg_count:
            result["issues"].append({
                "level": "warning",
                "msg": f'Column "{transit_col}" has {neg_count:,} negative value(s). transit_qty is expected to be ≥ 0.',
            })

    # ── reserved_qty < 0 warning (optional column) ───────────────────────────
    cols_lower = {c.lower(): c for c in df.columns}
    reserved_col = cols_lower.get("reserved_qty")
    if reserved_col:
        numeric_reserved = pd.to_numeric(df[reserved_col], errors="coerce")
        neg_reserved = (numeric_reserved < 0).sum()
        if neg_reserved:
            result["issues"].append({
                "level": "warning",
                "msg": f'Column "{reserved_col}" has {neg_reserved:,} negative value(s). reserved_qty is expected to be ≥ 0.',
            })
            result["reserved_qty_file"] = _write_csv(
                df[numeric_reserved < 0], session_dir,
                f"negative_reserved_qty_{neg_reserved}_rows.csv"
            )

    # ── site_qty < 0 warning ─────────────────────────────────────────────────
    site_col = canonical_map.get("site_qty")
    if site_col and site_col in df.columns:
        numeric_site = pd.to_numeric(df[site_col], errors="coerce")
        neg_site = (numeric_site < 0).sum()
        if neg_site:
            result["issues"].append({
                "level": "warning",
                "msg": f'Column "{site_col}" has {neg_site:,} negative value(s). site_qty is expected to be ≥ 0.',
            })
            result["site_qty_neg_file"] = _write_csv(
                df[numeric_site < 0], session_dir,
                f"negative_site_qty_{neg_site}_rows.csv"
            )

    # ── avoid_replenishment: flag if >50% are 1/True (optional column) ───────
    cols_lower_inv = {c.lower(): c for c in df.columns}
    avoid_col = cols_lower_inv.get("avoid_replenishment")
    if avoid_col:
        total = len(df)
        if total:
            series_av = df[avoid_col]
            # treat 1, True, "1", "true", "True", "TRUE" as positive
            positive_mask = (
                series_av.astype(str).str.strip().str.lower().isin({"1", "true"})
            )
            pos_count = positive_mask.sum()
            pct = round(pos_count / total * 100, 1)
            if pct > 50:
                result["issues"].append({
                    "level": "warning",
                    "msg": (
                        f'Column "{avoid_col}": {pos_count:,} of {total:,} rows ({pct}%) '
                        f'have avoid_replenishment=1/True — exceeds the 50% threshold.'
                    ),
                })
                result["avoid_replenishment_file"] = _write_csv(
                    df[positive_mask], session_dir,
                    f"avoid_replenishment_flagged_{pos_count}_rows.csv"
                )

    # ── min/max stock: enforce 1 ≤ min_stock ≤ max_stock (optional cols) ──────
    min_col = cols_lower_inv.get("min_stock")
    max_col = cols_lower_inv.get("max_stock")
    if min_col or max_col:
        num_min = pd.to_numeric(df[min_col], errors="coerce") if min_col else None
        num_max = pd.to_numeric(df[max_col], errors="coerce") if max_col else None

        violation_mask = pd.Series(False, index=df.index)
        reasons = []

        # min_stock must be ≥ 1
        if num_min is not None:
            below_one = num_min.notna() & (num_min < 1)
            if below_one.any():
                violation_mask |= below_one
                reasons.append(f'min_stock < 1 in {below_one.sum():,} row(s)')

        # min_stock must be ≤ max_stock (only when both present)
        if num_min is not None and num_max is not None:
            both_present = num_min.notna() & num_max.notna()
            exceeds = both_present & (num_min > num_max)
            if exceeds.any():
                violation_mask |= exceeds
                reasons.append(f'min_stock > max_stock in {exceeds.sum():,} row(s)')

        viol_count = violation_mask.sum()
        if viol_count:
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'Stock range violation (rule: 1 ≤ min_stock ≤ max_stock) — '
                    f'{"; ".join(reasons)}.'
                ),
            })
            result["min_max_stock_file"] = _write_csv(
                df[violation_mask], session_dir,
                f"stock_range_violation_{viol_count}_rows.csv"
            )

    # ── Duplicate (location_id, sku_id) check ────────────────────────────────
    loc_col = canonical_map.get("location_id")
    sku_col = canonical_map.get("sku_id")

    if loc_col and sku_col and loc_col in df.columns and sku_col in df.columns:
        dup_mask = df.duplicated(subset=[loc_col, sku_col], keep=False)
        dup_count = dup_mask.sum()
        if dup_count:
            result["issues"].append({
                "level": "error",
                "msg": (
                    f'Found {dup_count:,} rows with duplicate ({loc_col}, {sku_col}) combinations. '
                    f'Each location–SKU pair must be unique.'
                ),
            })
            result["duplicates_file"] = _write_csv(
                df[dup_mask], session_dir,
                f"duplicate_location_sku_{dup_count}_rows.csv"
            )

    return result


# ── Transactions-specific validation ─────────────────────────────────────────

def _validate_transactions(zf, zip_names, session_dir=None):
    """
    Full validation for the transactions CSV.

    Extra keys vs generic: actual_filename, bom, canonical_map, mapper_used,
                           nulls_file, duplicates_file
    """
    result = {
        "found": False,
        "actual_filename": None,
        "bom": None,
        "rows": 0,
        "columns": [],
        "issues": [],
        "canonical_map": {},
        "mapper_used": False,
        "nulls_file": None,
        "duplicates_file": None,
        "sale_price_file": None,
        "_df": None,
    }

    entry, basename = _find_file_fuzzy(zip_names, _TRANSACTION_PATTERNS)

    if entry is None:
        result["issues"].append({
            "level": "error",
            "msg": "transactions.csv not found in ZIP (also tried fuzzy patterns: transaction.csv, *transaction*.csv)",
        })
        return result

    result["found"] = True
    result["actual_filename"] = basename

    if basename.lower() != "transactions.csv":
        result["issues"].append({
            "level": "warning",
            "msg": f'File found as "{basename}" — rename to "transactions.csv" for best compatibility.',
        })

    # BOM
    has_bom = _detect_bom(zf, entry)
    result["bom"] = has_bom
    if has_bom:
        result["issues"].append({
            "level": "warning",
            "msg": "File contains a UTF-8 BOM (Byte Order Mark). Remove BOM for cleaner processing.",
        })

    # Load CSV
    try:
        with zf.open(entry) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"))
    except Exception as e:
        result["issues"].append({"level": "error", "msg": f"Failed to read CSV: {e}"})
        return result

    result["_df"] = df
    result["rows"] = len(df)
    result["columns"] = list(df.columns)
    result["issues"].extend(_basic_file_checks(df, basename))

    # Mandatory columns
    canonical_map, mapper_used, col_issues, _ = _validate_mandatory_columns(
        df, TRANSACTIONS_MANDATORY_COLS, None, "transactions", zf, zip_names
    )
    result["canonical_map"] = canonical_map
    result["mapper_used"] = mapper_used
    result["issues"].extend(col_issues)

    # Null rows export
    result["nulls_file"] = _export_null_rows(df, canonical_map, session_dir)

    # ── type column checks ────────────────────────────────────────────────────
    type_col = canonical_map.get("type")
    if type_col and type_col in df.columns:
        non_null_types = df[type_col].dropna().astype(str)

        # Warning: any uppercase letters
        has_caps = non_null_types.str.contains(r"[A-Z]", regex=True)
        caps_count = has_caps.sum()
        if caps_count:
            examples = non_null_types[has_caps].head(3).tolist()
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'Column "{type_col}" has {caps_count:,} value(s) with uppercase letters '
                    f'(e.g. {examples}). Values should be lowercase.'
                ),
            })

        # Warning: values not in allowed set (checked after lowercasing)
        invalid_mask = ~non_null_types.str.lower().isin(TRANSACTION_VALID_TYPES)
        invalid_vals = non_null_types[invalid_mask].unique().tolist()
        if invalid_vals:
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'Column "{type_col}" contains unexpected value(s): {invalid_vals}. '
                    f'Expected one of: {sorted(TRANSACTION_VALID_TYPES)}.'
                ),
            })

    # ── Duplicate id check ────────────────────────────────────────────────────
    id_col = canonical_map.get("id")
    if id_col and id_col in df.columns:
        dup_mask = df.duplicated(subset=[id_col], keep=False)
        dup_count = dup_mask.sum()
        if dup_count:
            result["issues"].append({
                "level": "error",
                "msg": (
                    f'Found {dup_count:,} rows with duplicate "{id_col}" values. '
                    f'Each transaction ID must be unique.'
                ),
            })
            result["duplicates_file"] = _write_csv(
                df[dup_mask], session_dir,
                f"duplicate_transaction_id_{dup_count}_rows.csv"
            )

    # ── source_location_id ≠ target_location_id ──────────────────────────────
    src_col = canonical_map.get("source_location_id")
    tgt_col = canonical_map.get("target_location_id")
    if src_col and tgt_col and src_col in df.columns and tgt_col in df.columns:
        both = df[src_col].notna() & df[tgt_col].notna()
        same_mask = both & (df[src_col].astype(str) == df[tgt_col].astype(str))
        same_count = same_mask.sum()
        total = int(both.sum())
        if same_count:
            pct = round(same_count / total * 100, 1) if total else 0
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'{same_count:,} of {total:,} rows ({pct}%) have '
                    f'source_location_id == target_location_id. '
                    f'Source and target locations should differ.'
                ),
            })

    # ── sale_price: warn if empty (optional column) ───────────────────────────
    cols_lower_txn = {c.lower(): c for c in df.columns}
    sale_price_col = cols_lower_txn.get("sale_price")
    if sale_price_col:
        numeric_sp = pd.to_numeric(df[sale_price_col], errors="coerce")
        empty_mask = numeric_sp.isna()
        empty_count = empty_mask.sum()
        if empty_count:
            result["issues"].append({
                "level": "warning",
                "msg": (
                    f'Column "{sale_price_col}" has {empty_count:,} empty/null value(s). '
                    f'sale_price should be populated for all rows.'
                ),
            })
            result["sale_price_file"] = _write_csv(
                df[empty_mask], session_dir,
                f"missing_sale_price_{empty_count}_rows.csv"
            )

    return result


# ── Cross-file validation ─────────────────────────────────────────────────────

def _cross_validate(dfs, canonical_maps, session_dir):
    """
    Run cross-file validation checks across all 4 DataFrames.

    Args:
        dfs:           dict keyed by file label → DataFrame (or None)
        canonical_maps: dict keyed by file label → canonical_map dict
        session_dir:   path for writing downloadable CSV files

    Returns a list of issue dicts, each with keys:
        level ("warning"), msg (str), file (filename or None)
    """
    issues = []

    cat_df  = dfs.get("catalogs")
    loc_df  = dfs.get("locations")
    inv_df  = dfs.get("inventories")
    txn_df  = dfs.get("transactions")

    cat_map = canonical_maps.get("catalogs",     {})
    loc_map = canonical_maps.get("locations",    {})
    inv_map = canonical_maps.get("inventories",  {})
    txn_map = canonical_maps.get("transactions", {})

    # ── Build reference lookup sets ───────────────────────────────────────────
    loc_ids = None
    if loc_df is not None:
        loc_id_col = loc_map.get("id")
        if loc_id_col and loc_id_col in loc_df.columns:
            loc_ids = set(loc_df[loc_id_col].dropna().astype(str).str.strip())

    cat_ids = None
    if cat_df is not None:
        cat_id_col = cat_map.get("id")
        if cat_id_col and cat_id_col in cat_df.columns:
            cat_ids = set(cat_df[cat_id_col].dropna().astype(str).str.strip())

    # ── Helper: check a column against a reference set ────────────────────────
    def _ref_check(df, col, ref_set, label, file_prefix, allowed_extra=None):
        """
        Warn when values in df[col] are not in ref_set.
        allowed_extra: set of additional allowed values (case-insensitive).
        Returns (issue_dict or None).
        """
        if df is None or col is None or col not in df.columns or ref_set is None:
            return None
        col_vals = df[col].dropna().astype(str).str.strip()
        if allowed_extra:
            allowed_lower = {v.lower() for v in (ref_set | allowed_extra)}
            missing_mask = df[col].notna() & ~col_vals.str.lower().isin(allowed_lower)
        else:
            missing_mask = df[col].notna() & ~col_vals.isin(ref_set)
        missing_count = int(missing_mask.sum())
        if not missing_count:
            return None
        missing_vals = col_vals[missing_mask].unique().tolist()[:5]
        fname = _write_csv(df[missing_mask], session_dir,
                           f"{file_prefix}_{missing_count}_rows.csv")
        extra_note = f' ("{next(iter(allowed_extra))}" is allowed)' if allowed_extra else ""
        return {
            "level": "warning",
            "msg": (
                f'[{label}] {missing_count:,} row(s) have {col!r} values not found '
                f'in the reference list (e.g. {missing_vals}){extra_note}.'
            ),
            "file": fname,
        }

    # ── 1. Inventories: source_location_id ≠ location_id ─────────────────────
    if inv_df is not None:
        src_col  = inv_map.get("source_location_id")
        loc_col  = inv_map.get("location_id")
        if src_col and loc_col and src_col in inv_df.columns and loc_col in inv_df.columns:
            both = inv_df[src_col].notna() & inv_df[loc_col].notna()
            same_mask = both & (
                inv_df[src_col].astype(str).str.strip()
                == inv_df[loc_col].astype(str).str.strip()
            )
            same_count = int(same_mask.sum())
            total = int(both.sum())
            if same_count:
                same_rows    = inv_df[same_mask]
                loc_type_col = loc_map.get("type")
                loc_id_col_l = loc_map.get("id")
                type_lookup_available = (
                    loc_df is not None
                    and loc_type_col and loc_id_col_l
                    and loc_type_col in loc_df.columns
                    and loc_id_col_l in loc_df.columns
                )

                if type_lookup_available:
                    # For each matching inventory row: take its location_id,
                    # find the row in locations where locations.id == location_id,
                    # and read the type.
                    loc_type_series = (
                        loc_df.drop_duplicates(subset=[loc_id_col_l])
                        .set_index(loc_id_col_l)[loc_type_col]
                        .astype(str).str.strip().str.lower()
                    )
                    matched_types = (
                        same_rows[loc_col].astype(str).str.strip().map(loc_type_series)
                    )
                    is_wh        = matched_types == "warehouse"
                    wh_count     = int(is_wh.sum())
                    non_wh_count = same_count - wh_count

                    # ⚠️ Non-warehouse locations are a real problem
                    if non_wh_count:
                        non_wh_rows = same_rows[~is_wh]
                        pct = round(non_wh_count / total * 100, 1) if total else 0
                        fname = _write_csv(
                            non_wh_rows, session_dir,
                            f"cross_inv_src_eq_loc_{non_wh_count}_rows.csv"
                        )
                        issues.append({
                            "level": "warning",
                            "msg": (
                                f'[Inventories] {non_wh_count:,} of {total:,} rows ({pct}%) have '
                                f'source_location_id == location_id for non-warehouse locations. '
                                f'These should be different locations.'
                            ),
                            "file": fname,
                        })
                        # ℹ️ Mention warehouse rows only as extra context alongside real failures
                        if wh_count:
                            issues.append({
                                "level": "info",
                                "msg": (
                                    f'[Inventories] Additionally, {wh_count:,} row(s) have '
                                    f'source_location_id == location_id for warehouse-type locations '
                                    f'— this is expected and acceptable for warehouses.'
                                ),
                                "file": None,
                            })
                    # If all matching rows are warehouse-type → nothing to report
                else:
                    # Location type data unavailable — original behaviour
                    pct = round(same_count / total * 100, 1) if total else 0
                    fname = _write_csv(
                        same_rows, session_dir,
                        f"cross_inv_src_eq_loc_{same_count}_rows.csv"
                    )
                    issues.append({
                        "level": "warning",
                        "msg": (
                            f'[Inventories] {same_count:,} of {total:,} rows ({pct}%) have '
                            f'source_location_id == location_id. '
                            f'These should be different locations.'
                        ),
                        "file": fname,
                    })

    # ── 2. Transactions date == Inventories status_date ───────────────────────
    if inv_df is not None and txn_df is not None:
        status_col = inv_map.get("status_date")
        # Detect a date column in transactions (check common names)
        txn_cols_lower = {c.lower(): c for c in txn_df.columns}
        txn_date_col = None
        for candidate in ["date", "transaction_date", "created_date", "created_at", "txn_date"]:
            if candidate in txn_cols_lower:
                txn_date_col = txn_cols_lower[candidate]
                break

        if status_col and status_col in inv_df.columns and txn_date_col:
            inv_dates = set(
                pd.to_datetime(inv_df[status_col], errors="coerce")
                .dropna().dt.date.unique()
            )
            txn_dates = set(
                pd.to_datetime(txn_df[txn_date_col], errors="coerce")
                .dropna().dt.date.unique()
            )
            only_in_txn = txn_dates - inv_dates
            only_in_inv = inv_dates - txn_dates
            if only_in_txn or only_in_inv:
                parts = []
                if only_in_txn:
                    parts.append(
                        f'in Transactions only: {sorted(str(d) for d in only_in_txn)}'
                    )
                if only_in_inv:
                    parts.append(
                        f'in Inventories only: {sorted(str(d) for d in only_in_inv)}'
                    )
                issues.append({
                    "level": "warning",
                    "msg": (
                        f'[Cross] Transaction dates and Inventory status_date do not '
                        f'fully align — {"; ".join(parts)}.'
                    ),
                    "file": None,
                })

    # ── 3. Inventories.location_id → Locations.id ─────────────────────────────
    issue = _ref_check(
        inv_df, inv_map.get("location_id"), loc_ids,
        "Inventories × Locations", "cross_inv_location_id_not_in_locations",
    )
    if issue:
        issue["msg"] = issue["msg"].replace(
            repr(inv_map.get("location_id")), "location_id"
        )
        issues.append(issue)

    # ── 4. Inventories.sku_id → Catalogs.id ──────────────────────────────────
    issue = _ref_check(
        inv_df, inv_map.get("sku_id"), cat_ids,
        "Inventories × Catalogs", "cross_inv_sku_id_not_in_catalogs",
    )
    if issue:
        issue["msg"] = issue["msg"].replace(repr(inv_map.get("sku_id")), "sku_id")
        issues.append(issue)

    # ── 5. Inventories.source_location_id → Locations.id ─────────────────────
    issue = _ref_check(
        inv_df, inv_map.get("source_location_id"), loc_ids,
        "Inventories × Locations", "cross_inv_source_location_not_in_locations",
    )
    if issue:
        issue["msg"] = issue["msg"].replace(
            repr(inv_map.get("source_location_id")), "source_location_id"
        )
        issues.append(issue)

    # ── 6. Transactions.sku_id → Catalogs.id ─────────────────────────────────
    issue = _ref_check(
        txn_df, txn_map.get("sku_id"), cat_ids,
        "Transactions × Catalogs", "cross_txn_sku_id_not_in_catalogs",
    )
    if issue:
        issue["msg"] = issue["msg"].replace(repr(txn_map.get("sku_id")), "sku_id")
        issues.append(issue)

    # ── 7. Transactions.source_location_id → Locations.id (or "client") ──────
    issue = _ref_check(
        txn_df, txn_map.get("source_location_id"), loc_ids,
        "Transactions × Locations", "cross_txn_source_location_not_in_locations",
        allowed_extra={"client"},
    )
    if issue:
        issue["msg"] = issue["msg"].replace(
            repr(txn_map.get("source_location_id")), "source_location_id"
        )
        issues.append(issue)

    # ── 8. Transactions.target_location_id → Locations.id (or "client") ──────
    issue = _ref_check(
        txn_df, txn_map.get("target_location_id"), loc_ids,
        "Transactions × Locations", "cross_txn_target_location_not_in_locations",
        allowed_extra={"client"},
    )
    if issue:
        issue["msg"] = issue["msg"].replace(
            repr(txn_map.get("target_location_id")), "target_location_id"
        )
        issues.append(issue)

    return issues


# ── Main entry point ──────────────────────────────────────────────────────────

def validate_zip(zip_path, session_dir=None):
    """
    Open a ZIP, locate the 4 expected CSV files, run checks on each,
    and return a structured result dict ready for the template.
    """
    result = {
        "ok": True,
        "files": {},
        "cross": [],
        "summary": {"errors": 0, "warnings": 0, "total_rows": 0, "total_cols": 0},
    }

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zip_names = zf.namelist()

            for expected in EXPECTED_FILES:
                if expected == "catalogs.csv":
                    info = _validate_catalogs(zf, zip_names, session_dir=session_dir)
                elif expected == "locations.csv":
                    info = _validate_locations(zf, zip_names, session_dir=session_dir)
                elif expected == "inventories.csv":
                    info = _validate_inventories(zf, zip_names, session_dir=session_dir)
                elif expected == "transactions.csv":
                    info = _validate_transactions(zf, zip_names, session_dir=session_dir)
                else:
                    entry = _find_in_zip(zip_names, expected)
                    if entry is None:
                        info = {
                            "found": False,
                            "rows": 0,
                            "columns": [],
                            "issues": [{"level": "error", "msg": f"{expected} not found in ZIP"}],
                        }
                    else:
                        try:
                            with zf.open(entry) as f:
                                df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"))
                            info = {
                                "found": True,
                                "rows": len(df),
                                "columns": list(df.columns),
                                "issues": _basic_file_checks(df, expected),
                            }
                        except Exception as e:
                            info = {
                                "found": True,
                                "rows": 0,
                                "columns": [],
                                "issues": [{"level": "error", "msg": f"Failed to read: {e}"}],
                            }

                # Tally errors / warnings / totals
                for issue in info["issues"]:
                    if issue["level"] == "error":
                        result["summary"]["errors"] += 1
                        result["ok"] = False
                    elif issue["level"] == "warning":
                        result["summary"]["warnings"] += 1

                if info.get("found"):
                    result["summary"]["total_rows"] += info.get("rows", 0)
                    result["summary"]["total_cols"] += len(info.get("columns", []))

                result["files"][expected] = info

            # ── Cross-validations ─────────────────────────────────────────
            # Collect DataFrames and canonical maps from each file result,
            # then strip the internal "_df" key so it never reaches the template.
            _label_map = {
                "catalogs.csv":     "catalogs",
                "locations.csv":    "locations",
                "inventories.csv":  "inventories",
                "transactions.csv": "transactions",
            }
            dfs           = {}
            canonical_maps = {}
            for expected, info in result["files"].items():
                label = _label_map.get(expected, expected)
                dfs[label]            = info.pop("_df", None)
                canonical_maps[label] = info.get("canonical_map", {})

            cross_issues = _cross_validate(dfs, canonical_maps, session_dir)
            result["cross"] = cross_issues
            for issue in cross_issues:
                result["summary"]["warnings"] += 1

    except zipfile.BadZipFile:
        result["ok"] = False
        result["summary"]["errors"] += 1
        for f in EXPECTED_FILES:
            result["files"][f] = {
                "found": False, "rows": 0, "columns": [],
                "issues": [{"level": "error", "msg": "Invalid or corrupted ZIP file"}],
            }

    return result
