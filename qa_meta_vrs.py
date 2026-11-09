"""Read-only, reproducible quality audit of the public FAccT 2025 Meta VRS ZIP.

Usage:
    python meta_vrs/qa_meta_vrs.py
    python meta_vrs/qa_meta_vrs.py path/to/vrs_ad_delivery_data-2025-05-23.zip

This script does not decide whether Meta discriminated. It checks whether the
published experimental observations can support a later bias-delivery audit.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd


DEFAULT_ZIP = Path(__file__).parent / "data_raw" / "vrs_ad_delivery_data-2025-05-23.zip"
FILES = (
    "data_vrs_vs_novrs.csv",
    "data_heccomp.csv",
    "data_budget_split.csv",
)
IDENTIFIERS = ("camp_id", "adset_id", "adcreative_id", "ad_id")
DATE_FORMAT = "%m/%d/%Y %H:%M:%S"


def near_zero(series: pd.Series, tolerance: float = 1e-5) -> int:
    """Number of nonmissing values whose absolute error exceeds tolerance."""
    return int((series.dropna().abs() > tolerance).sum())


def audit_one(name: str, data: pd.DataFrame) -> None:
    print(f"\n{'=' * 72}\n{name}: {len(data)} rows × {len(data.columns)} columns")
    print("Experiment types:", data["exp_type"].value_counts().to_dict())
    print("HEC declarations:", data["hec_cat"].value_counts().to_dict())
    print("Distinct experiment IDs:", data["exp_id"].nunique())
    print("Exact duplicate rows:", int(data.duplicated().sum()))

    nulls = data.isna().sum()
    print("Missing cells:", int(nulls.sum()))
    print("Missing values by column:", nulls[nulls > 0].sort_values(ascending=False).to_dict())
    if "aggregate" in set(data["exp_type"]):
        aggregated = data["exp_type"].eq("aggregate")
        print("Aggregate rows (derived, NOT additional campaigns):", int(aggregated.sum()))
        print("Missing cells in aggregate rows:", int(data.loc[aggregated].isna().sum().sum()))
        print("Missing cells in other rows:", int(data.loc[~aggregated].isna().sum().sum()))

    starts = pd.to_datetime(data["start"], format=DATE_FORMAT, errors="coerce")
    ends = pd.to_datetime(data["end"], format=DATE_FORMAT, errors="coerce")
    print("Date coverage:", str(starts.min()), "to", str(ends.max()))
    print("Unparseable/missing dates:", int(starts.isna().sum()), int(ends.isna().sum()))
    print("Negative/zero experiment durations:", int(((ends <= starts) & starts.notna() & ends.notna()).sum()))
    print("Unique recorded ad IDs:", data["ad_id"].nunique(dropna=True))
    print("Ad IDs in scientific notation:", int(data["ad_id"].fillna("").str.contains(r"[eE]\+").sum()))

    numerical = data.select_dtypes(include="number").columns
    negatives = {col: int((data[col] < 0).sum()) for col in numerical if (data[col] < 0).any()}
    print("Negative numeric values (-1 sentinels):", negatives)
    sentinel_count = 0
    sentinel_without_zero_denominator = 0
    for group in ("b", "w", "or", "m", "f", "og"):
        for cost, denominator in (("cpc", "clicks"), ("cpm", "impressions"), ("cpp", "reach")):
            cost_series = data[f"{group}_{cost}"]
            sentinel = cost_series.eq(-1)
            sentinel_count += int(sentinel.sum())
            sentinel_without_zero_denominator += int((sentinel & data[f"{group}_{denominator}"].ne(0)).sum())
    print("Total -1 cost sentinels:", sentinel_count)
    print("-1 sentinels WITHOUT a zero denominator:", sentinel_without_zero_denominator)
    for kind, labels, suffix in (
        ("Race", ("b", "w", "or"), "r"),
        ("Gender", ("m", "f", "og"), "g"),
    ):
        for metric, total in (
            ("impressions", f"total_imp_{suffix}"),
            ("reach", f"total_reach_{suffix}"),
            ("clicks", f"total_click_{suffix}"),
            ("spend", f"total_spend_{suffix}"),
        ):
            if total not in data:
                continue
            expected = sum(data[f"{label}_{metric}"] for label in labels)
            mismatches = near_zero(expected - data[total], 0.02 if metric == "spend" else 1e-5)
            if mismatches:
                print(f"  WARNING: {kind} {metric} category-sum mismatch: {mismatches} rows")
        print(f"{kind} category impressions sum: checked")

    print("Race/Gender impression total disagreements:", near_zero(data["total_imp_r"] - data["total_imp_g"]))
    print("Race/Gender reach total disagreements (up to 2 possible):", near_zero(data["total_reach_r"] - data["total_reach_g"]))

    for suffix in ("r", "g"):
        cost_m = data[f"total_spend_{suffix}"] / data[f"total_imp_{suffix}"] * 1000
        cost_p = data[f"total_spend_{suffix}"] / data[f"total_reach_{suffix}"] * 1000
        print(
            f"Cost reconciliation ({suffix}): CPM / cpp per 1,000 errors:",
            near_zero(cost_m - data[f"total_cpm_{suffix}"]),
            near_zero(cost_p - data[f"total_cpp_{suffix}"]),
        )

    group_errors = 0
    valid_checks = 0
    for group in ("b", "w", "m", "f"):
        for cost, denominator, multiplier in (("cpc", "clicks", 1), ("cpm", "impressions", 1000), ("cpp", "reach", 1000)):
            eligible = data[f"{group}_{cost}"].ge(0) & data[f"{group}_{denominator}"].gt(0)
            valid_checks += int(eligible.sum())
            computed = data.loc[eligible, f"{group}_spend"] / data.loc[eligible, f"{group}_{denominator}"] * multiplier
            group_errors += near_zero(data.loc[eligible, f"{group}_{cost}"] - computed, 1e-4)
    print(f"Black/White/Male/Female cost formula mismatches: {group_errors} of {valid_checks} checks")
    # Some unknown/other groups have nonzero spending but reported cost 0.
    # They are NOT safe to use without recomputing costs from spend/denominator.
    unknown_placeholders = sum(
        int((data[f"{g}_spend"].gt(0) & data[f"{g}_{den}"].gt(0) & data[f"{g}_{cost}"].eq(0)).sum())
        for g in ("or", "og")
        for cost, den in (("cpc", "clicks"), ("cpm", "impressions"), ("cpp", "reach"))
    )
    print("Unknown-group positive-spend metrics recorded with zero cost:", unknown_placeholders)

    for group in ("r", "g"):
        series = data[f"{group}-variance-eligible"]
        outside = int((~series.between(0, 1) & series.notna()).sum())
        print(f"{group}-variance-eligible range:", f"{series.min():.4f}–{series.max():.4f}", "out of bounds:", outside)


def main(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Download the public ZIP first: {path}")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP checksum failed for: {bad}")
        members = archive.namelist()
        unsafe = [m for m in members if m.startswith("/") or ".." in Path(m).parts]
        if unsafe:
            raise ValueError(f"Unsafe archive paths: {unsafe}")
        print("ZIP:", path.resolve())
        print("ZIP files and directories:", len(members))
        print("Integrity: CRCs OK; path traversal check OK")
        print("Archive members:", ", ".join(members))
        datasets = {}
        for name in FILES:
            csv_bytes = archive.read(name)
            data = pd.read_csv(io.BytesIO(csv_bytes), dtype={identifier: "string" for identifier in IDENTIFIERS})
            datasets[name] = data

    columns = {name: set(data.columns) for name, data in datasets.items()}
    print("Same CSV columns across all three files:", all(x == columns[FILES[0]] for x in columns.values()))
    print("Column groups: race b/w/or, gender m/f/og, costs, impressions, reach, clicks, dates, IDs")
    for name, data in datasets.items():
        audit_one(name, data)

    paired = datasets["data_vrs_vs_novrs.csv"]
    expected = {"g-vrs", "g-novrs", "r-vrs", "r-novrs"}
    complete = paired.groupby("exp_id")["exp_type"].agg(lambda s: set(s) == expected and len(s) == 4)
    print("\nPAIRING CHECK")
    print("Complete four-row experiments:", int(complete.sum()), "/", len(complete))
    print("Paired VRS On/Off comparisons by demographic:", int(complete.sum() * 2))
    print("Creative prefixes and counts:", paired.exp_id.str.extract(r"^([A-Z]+)")[0].value_counts().to_dict())

    split = datasets["data_budget_split.csv"]
    split_types = {"aggregate", "split-black-male", "split-black-female", "split-white-male", "split-white-female"}
    complete_splits = split.groupby("exp_id")["exp_type"].agg(lambda s: set(s) == split_types and len(s) == 5)
    print("Complete five-row budget-splitting groups:", int(complete_splits.sum()), "/", len(complete_splits))

    hec = datasets["data_heccomp.csv"]
    print("HEC experiment types:", hec.exp_type.value_counts().to_dict())
    cross_file = hec.merge(
        paired,
        on=["start", "end", "total_imp_r", "total_reach_r"],
        how="inner",
        suffixes=("_hec", "_main"),
    )
    print("HEC records matching the primary comparison file by time/imp/reach:", len(cross_file))
    print("Matching HEC categories:", cross_file["exp_type_hec"].value_counts().to_dict())
    print("\nIMPORTANT UNITS: README says cpp = cost per 100 reach, but EVERY nonzero")
    print("row's published cpp is mathematically cost per 1,000 reach. Use / reach × 1,000.")
    print("IMPORTANT MISSING VALUES: -1 is a cost sentinel when impressions/reach/clicks")
    print("are zero. Replace it with NA for analysis, not with actual negative costs.")
    print("Unknown-race/gender cost fields sometimes contain zeros despite positive")
    print("spend; do NOT interpret those zeros as actual unit costs.")
    print("IMPORTANT GRAIN: budget_split 'aggregate' rows are derived; don't count")
    print("them as independent ad runs. Six HEC rows repeat main-file measurements.")
    print("Some ad IDs were exported in rounded scientific notation: do not rely")
    print("on them for exact cross-file matching or join through floating point.")
    print("IMPORTANT REPRODUCIBILITY: The ZIP does NOT include user-level histories")
    print("or the eligible-audience reference distributions, so the reported")
    print("variance can be compared but not independently reconstructed exactly.")
    print("IMPORTANT INTERPRETATION: these are controlled probe campaigns, not")
    print("actual listings of homes or user-level data. Disparity is not proof of intent.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ZIP)
