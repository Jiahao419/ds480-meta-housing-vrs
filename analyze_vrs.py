"""Paired VRS On/Off analysis of the public Meta VRS audit dataset.

Source data: Imana, Shen, Heidemann & Korolova, "External Evaluation of
Discrimination Mitigation Efforts in Meta's Ad Delivery", ACM FAccT 2025
(arXiv:2506.16560). Public ZIP: https://ant.isi.edu/datasets/addelivery-vrs/

Usage, from the project folder:
    python meta_vrs/analyze_vrs.py
    python meta_vrs/analyze_vrs.py path/to/vrs_ad_delivery_data-2025-05-23.zip

The ZIP is opened read-only; nothing is extracted, rewritten or deleted. Only
data_vrs_vs_novrs.csv is analysed. Outputs:
    meta_vrs/output/   tidy tables (CSV) and key_results.txt
    meta_vrs/figures/  figures (PNG at 300 dpi and vector PDF)

Data rules follow DATA_QA.md:
  * -1 values in cost fields are undefined costs (zero denominator) -> NaN.
  * Cost per 1,000 people reached is recomputed as spend / unique reach x 1,000
    (the README's "per 100" label is incorrect).
  * Gender pairs use the gender-report totals (*_g); race pairs use the
    race-report totals (*_r). Reach totals can differ by 1-2 between them.
  * The experimental unit is the matched pair, keyed by (exp_id, dimension).
    72 deployments -> 36 pairs; no deployment is used in more than one pair.
  * Unknown race/gender unit-cost fields (or_*, og_*) are not used.

Requirements: Python >= 3.10, pandas, numpy, matplotlib. SciPy is not needed;
the exact paired tests are implemented below.
"""

from __future__ import annotations

import hashlib
import io
import math
import sys
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_ZIP = HERE / "data_raw" / "vrs_ad_delivery_data-2025-05-23.zip"
EXPECTED_SHA256 = "ed37bcca5485f558f1e2bd55f0175dca4247a1901bd5319046a2bb2c64f4cf5d"
OUT_DIR = HERE / "output"
FIG_DIR = HERE / "figures"
PRIMARY = "data_vrs_vs_novrs.csv"
IDENTIFIERS = ("camp_id", "adset_id", "adcreative_id", "ad_id")
DATE_FORMAT = "%m/%d/%Y %H:%M:%S"

SEED = 480
N_BOOT = 10_000
N_PERM = 10_000

# Group 1 / group 2 convention used throughout the derived tables.
DIMENSIONS = {
    "gender": {
        "code": "g",
        "g1": ("f", "Female"),
        "g2": ("m", "Male"),
        "variance": "g-variance-eligible",
        "other_variance": "r-variance-eligible",
    },
    "race": {
        "code": "r",
        "g1": ("b", "Black"),
        "g2": ("w", "White"),
        "variance": "r-variance-eligible",
        "other_variance": "g-variance-eligible",
    },
}

# Reference distributions (group 1 share, group 2 share) for the variance formula
#   variance = 0.5 * (|share_1 - ref_1| + |share_2 - ref_2|), on impression shares.
# The first entry is the eligible-ratio estimate stated by the original researchers
# (paper Sec. 4.2.1); with it, the formula reproduces the published variance columns.
PAPER_BENCHMARK = "paper eligible-ratio estimate"
BENCHMARKS = {
    PAPER_BENCHMARK: {"race": (0.42, 0.58), "gender": (0.55, 0.45)},
    "post-matching audience (paper App. D)": {"race": (0.43, 0.57), "gender": (0.55, 0.45)},
    "uploaded audience (50:50)": {"race": (0.50, 0.50), "gender": (0.50, 0.50)},
}
BENCHMARK_SLUGS = {
    PAPER_BENCHMARK: "paper",
    "post-matching audience (paper App. D)": "postmatch",
    "uploaded audience (50:50)": "fifty",
}

CREATIVE_ORDER = ["HA", "GA", "EA", "EB", "IA", "FA"]
CREATIVES = {
    "HA": "Hair product",
    "GA": "Golf",
    "EA": "Education (ASU)",
    "EB": "Education (CSU)",
    "IA": "Insurance",
    "FA": "Financial",
}

# Values stated by the original researchers (arXiv:2506.16560v1). Kept separate
# from everything computed here so the two are never confused.
PAPER_REPORTED = {
    "reach_pct": -9.82,  # Sec. 4.2.3
    "cpp_pct": 12.02,  # Sec. 4.2.3
    "race_off_above_10": 18,  # Sec. 4.2.1
    "race_on_below_10": 18,  # Sec. 4.2.1
    "race_on_below_5": 15,  # Sec. 4.2.1
    "gender_off_below_5": 15,  # Sec. 4.2.1
    "eligible_ratio": {"Black": 0.42, "White": 0.58, "Male": 0.45, "Female": 0.55},  # Sec. 4.2.1
    "ha_leveling_down": ["HA1-g", "HA2-g", "HA2-r", "HA3-g"],  # Sec. 4.2.3
    "ha_cpp_not_up": ["HA1-g", "HA1-r"],  # Sec. 4.2.3
}

# Chart palette (validated: CVD and normal-vision separation pass for the On/Off pair).
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SHADE = "#f0efec"
COLOR_ON = "#2a78d6"
COLOR_OFF = "#eb6834"


# --------------------------------------------------------------------------- #
# Loading, cleaning, validation
# --------------------------------------------------------------------------- #
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_primary(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP CRC check failed for member: {bad}")
        payload = archive.read(PRIMARY)
    return pd.read_csv(io.BytesIO(payload), dtype={col: "string" for col in IDENTIFIERS})


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    data = raw.copy()
    cost_cols = [c for c in data.columns if c.endswith(("_cpc", "_cpm", "_cpp"))]
    sentinel = data[cost_cols].eq(-1)
    n_sentinel = int(sentinel.to_numpy().sum())
    data[cost_cols] = data[cost_cols].mask(sentinel)
    data["start"] = pd.to_datetime(data["start"], format=DATE_FORMAT)
    data["end"] = pd.to_datetime(data["end"], format=DATE_FORMAT)
    exp_type = data["exp_type"].astype(str)
    data["dimension"] = np.where(exp_type.str.startswith("g-"), "gender", "race")
    data["condition"] = np.where(exp_type.str.endswith("-novrs"), "off", "on")
    exp_id = data["exp_id"].astype(str)
    data["creative"] = exp_id.str.extract(r"^([A-Z]+)")[0]
    data["replicate"] = exp_id.str.extract(r"(\d+)$")[0].astype(int)
    return data, n_sentinel


def tvd(share_1: pd.Series, share_2: pd.Series, ref: tuple[float, float]) -> pd.Series:
    """Half the summed absolute gap between delivered and reference shares."""
    return 0.5 * ((share_1 - ref[0]).abs() + (share_2 - ref[1]).abs())


def validate(data: pd.DataFrame) -> dict[str, object]:
    checks: dict[str, object] = {}
    expected_types = {"g-vrs", "g-novrs", "r-vrs", "r-novrs"}
    assert len(data) == 72, "expected 72 deployments"
    assert not data.duplicated(["exp_id", "exp_type"]).any(), "duplicate (exp_id, exp_type)"
    per_id = data.groupby("exp_id")["exp_type"].agg(lambda s: set(s.astype(str)))
    assert per_id.map(lambda s: s == expected_types).all(), "incomplete four-row experiment"
    assert len(per_id) == 18
    reps = data.drop_duplicates("exp_id").groupby("creative")["replicate"].nunique()
    assert set(reps.index) == set(CREATIVE_ORDER) and (reps == 3).all()
    assert (data.groupby("exp_id")["start"].nunique() == 1).all(), "pair members not concurrent"
    assert (data.groupby("exp_id")["end"].nunique() == 1).all()
    durations = (data["end"] - data["start"]).dt.total_seconds().div(3600)
    assert durations.eq(24).all(), "non-24-hour deployment"
    assert data["total_imp_r"].eq(data["total_imp_g"]).all()
    checks["reach_total_disagreements_r_vs_g"] = int(data["total_reach_r"].ne(data["total_reach_g"]).sum())
    checks["max_abs_reach_total_disagreement"] = float((data["total_reach_r"] - data["total_reach_g"]).abs().max())

    # The published variance columns are reproduced exactly from impression shares
    # and the researchers' stated eligible-ratio estimate.
    bench = BENCHMARKS[PAPER_BENCHMARK]
    race = tvd(data["b_impressions"] / data["total_imp_r"], data["w_impressions"] / data["total_imp_r"], bench["race"])
    gender = tvd(data["f_impressions"] / data["total_imp_g"], data["m_impressions"] / data["total_imp_g"], bench["gender"])
    err_r = float((race - data["r-variance-eligible"]).abs().max())
    err_g = float((gender - data["g-variance-eligible"]).abs().max())
    assert err_r < 1e-9 and err_g < 1e-9, "variance columns not reproduced"
    checks["max_abs_error_race_variance_reconstruction"] = err_r
    checks["max_abs_error_gender_variance_reconstruction"] = err_g
    return checks


# --------------------------------------------------------------------------- #
# Derived tables
# --------------------------------------------------------------------------- #
def deployment_table(data: pd.DataFrame) -> pd.DataFrame:
    """One row per deployment (72), using the dimension-matched report."""
    frames = []
    for dim, spec in DIMENSIONS.items():
        sub = data[data["dimension"] == dim]
        c = spec["code"]
        g1, g1_name = spec["g1"]
        g2, g2_name = spec["g2"]
        out = pd.DataFrame(
            {
                "exp_id": sub["exp_id"].astype(str),
                "creative": sub["creative"],
                "replicate": sub["replicate"],
                "dimension": dim,
                "condition": sub["condition"],
                "exp_type": sub["exp_type"].astype(str),
                "start": sub["start"],
                "variance": sub[spec["variance"]],
                "variance_other_dimension": sub[spec["other_variance"]],
                "impressions": sub[f"total_imp_{c}"],
                "reach": sub[f"total_reach_{c}"],
                "spend": sub[f"total_spend_{c}"],
                "g1_name": g1_name,
                "g2_name": g2_name,
                "g1_impressions": sub[f"{g1}_impressions"],
                "g2_impressions": sub[f"{g2}_impressions"],
                "g1_reach": sub[f"{g1}_reach"],
                "g2_reach": sub[f"{g2}_reach"],
            }
        )
        out["cpp"] = out["spend"] / out["reach"] * 1000
        out["cpm"] = out["spend"] / out["impressions"] * 1000
        out["frequency"] = out["impressions"] / out["reach"]
        out["g1_imp_share"] = out["g1_impressions"] / out["impressions"]
        out["g2_imp_share"] = out["g2_impressions"] / out["impressions"]
        out["g1_reach_share"] = out["g1_reach"] / out["reach"]
        out["g2_reach_share"] = out["g2_reach"] / out["reach"]
        out["g1_frequency"] = out["g1_impressions"] / out["g1_reach"]
        out["g2_frequency"] = out["g2_impressions"] / out["g2_reach"]
        # Group-level cost per 1,000 reached, recomputed from spend and reach.
        out["g1_cpp"] = sub[f"{g1}_spend"] / out["g1_reach"] * 1000
        out["g2_cpp"] = sub[f"{g2}_spend"] / out["g2_reach"] * 1000
        out["frequency_ratio"] = out["g1_frequency"] / out["g2_frequency"]
        paper_ref = BENCHMARKS[PAPER_BENCHMARK][dim]
        out["variance_recomputed"] = tvd(out["g1_imp_share"], out["g2_imp_share"], paper_ref)
        out["reach_share_variance_analog"] = tvd(out["g1_reach_share"], out["g2_reach_share"], paper_ref)
        for name, slug in BENCHMARK_SLUGS.items():
            out[f"variance_{slug}"] = tvd(out["g1_imp_share"], out["g2_imp_share"], BENCHMARKS[name][dim])
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


PAIR_LEVEL_METRICS = [
    "variance",
    "variance_other_dimension",
    "impressions",
    "reach",
    "spend",
    "cpp",
    "cpm",
    "frequency",
    "g1_impressions",
    "g2_impressions",
    "g1_reach",
    "g2_reach",
    "g1_imp_share",
    "g1_reach_share",
    "g1_frequency",
    "g2_frequency",
    "frequency_ratio",
    "g1_cpp",
    "g2_cpp",
    "reach_share_variance_analog",
] + [f"variance_{slug}" for slug in BENCHMARK_SLUGS.values()]


REACH_PATTERNS = [
    "both groups lose reach",
    "over-delivered group loses, other does not",
    "over-delivered group does not lose, other loses",
    "neither group loses reach",
]


def build_pairs(dep: pd.DataFrame) -> pd.DataFrame:
    """36 matched VRS On/Off comparisons keyed by (exp_id, dimension)."""
    key = ["exp_id", "dimension"]
    on = dep[dep["condition"] == "on"].set_index(key).sort_index()
    off = dep[dep["condition"] == "off"].set_index(key).sort_index()
    assert on.index.equals(off.index) and len(on) == 36 and on.index.is_unique
    assert (on["start"] == off["start"]).all()

    pairs = on[["creative", "replicate", "g1_name", "g2_name"]].copy()
    for metric in PAIR_LEVEL_METRICS:
        pairs[f"{metric}_off"] = off[metric]
        pairs[f"{metric}_on"] = on[metric]
    pairs["d_variance_pp"] = (on["variance"] - off["variance"]) * 100
    pairs["d_variance_other_pp"] = (on["variance_other_dimension"] - off["variance_other_dimension"]) * 100
    for metric in ("reach", "impressions", "spend", "cpp", "cpm", "frequency", "g1_reach", "g2_reach", "g1_cpp", "g2_cpp"):
        pairs[f"pct_{metric}"] = (on[metric] / off[metric] - 1) * 100
    pairs["d_g1_imp_share_pp"] = (on["g1_imp_share"] - off["g1_imp_share"]) * 100
    pairs["d_g1_reach_share_pp"] = (on["g1_reach_share"] - off["g1_reach_share"]) * 100
    pairs["d_frequency_ratio"] = on["frequency_ratio"] - off["frequency_ratio"]
    pairs["d_reach_variance_analog_pp"] = (
        on["reach_share_variance_analog"] - off["reach_share_variance_analog"]
    ) * 100
    for slug in BENCHMARK_SLUGS.values():
        pairs[f"d_variance_{slug}_pp"] = (on[f"variance_{slug}"] - off[f"variance_{slug}"]) * 100

    # Which group was over-delivered (impression share above the paper's reference)
    # without VRS, and what happened to each group's unique reach with VRS.
    ref_1 = np.array([BENCHMARKS[PAPER_BENCHMARK][d][0] for d in pairs.index.get_level_values("dimension")])
    over_is_g1 = off["g1_imp_share"].to_numpy() > ref_1
    pairs["overdelivered_group_off"] = np.where(over_is_g1, pairs["g1_name"], pairs["g2_name"])
    over = np.where(over_is_g1, pairs["pct_g1_reach"], pairs["pct_g2_reach"])
    under = np.where(over_is_g1, pairs["pct_g2_reach"], pairs["pct_g1_reach"])
    pairs["pct_reach_overdelivered_group"] = over
    pairs["pct_reach_other_group"] = under
    pairs["reach_pattern"] = np.select(
        [(over < 0) & (under < 0), (over < 0) & (under >= 0), (over >= 0) & (under < 0)],
        REACH_PATTERNS[:3],
        default=REACH_PATTERNS[3],
    )
    pairs["leveling_down"] = (pairs["reach_pattern"] == "both groups lose reach") & (pairs["d_variance_pp"] < 0)

    pairs = pairs.reset_index()
    pairs["pair_id"] = pairs["exp_id"] + "-" + pairs["dimension"].str[0]
    pairs["creative_label"] = pairs["creative"].map(CREATIVES)
    lead = ["pair_id", "exp_id", "dimension", "creative", "creative_label", "replicate", "g1_name", "g2_name"]
    return pairs[lead + [c for c in pairs.columns if c not in lead]]


# --------------------------------------------------------------------------- #
# Statistics (exact paired tests, bootstrap, permutation)
# --------------------------------------------------------------------------- #
def sign_test(values) -> float:
    """Exact two-sided sign test against a median change of zero."""
    x = np.asarray(values, float)
    x = x[~np.isnan(x) & (x != 0)]
    n, k = len(x), int((x > 0).sum())
    if n == 0:
        return float("nan")
    lower = sum(math.comb(n, i) for i in range(0, k + 1)) / 2**n
    upper = sum(math.comb(n, i) for i in range(k, n + 1)) / 2**n
    return min(1.0, 2 * min(lower, upper))


def wilcoxon_exact(values) -> float:
    """Exact two-sided Wilcoxon signed-rank test (zeros dropped, mid-ranks for ties)."""
    x = np.asarray(values, float)
    x = x[~np.isnan(x) & (x != 0)]
    n = len(x)
    if n == 0:
        return float("nan")
    doubled = np.rint(2 * pd.Series(np.abs(x)).rank(method="average").to_numpy()).astype(int)
    w_plus = int(doubled[x > 0].sum())
    total = int(doubled.sum())
    dist = np.zeros(total + 1)
    dist[0] = 1.0
    for r in doubled:
        shifted = np.zeros_like(dist)
        shifted[r:] = dist[: total + 1 - r]
        dist = dist + shifted
    dist /= dist.sum()
    return float(min(1.0, 2 * min(dist[: w_plus + 1].sum(), dist[w_plus:].sum())))


def bootstrap_ci(values, n_boot: int = N_BOOT) -> tuple[float, float]:
    """Percentile 95% CI of the mean, resampling the supplied independent units."""
    v = np.asarray(values, float)
    rng = np.random.default_rng(SEED)
    means = v[rng.integers(0, len(v), size=(n_boot, len(v)))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def spearman(x, y) -> float:
    rx = pd.Series(np.asarray(x, float)).rank().to_numpy()
    ry = pd.Series(np.asarray(y, float)).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def spearman_perm_p(x, y, n_perm: int = N_PERM) -> float:
    rx = pd.Series(np.asarray(x, float)).rank().to_numpy()
    ry = pd.Series(np.asarray(y, float)).rank().to_numpy()
    observed = abs(np.corrcoef(rx, ry)[0, 1])
    rng = np.random.default_rng(SEED)
    hits = sum(abs(np.corrcoef(rx, rng.permutation(ry))[0, 1]) >= observed - 1e-12 for _ in range(n_perm))
    return (hits + 1) / (n_perm + 1)


def scopes(pairs: pd.DataFrame):
    yield "gender", pairs[pairs["dimension"] == "gender"]
    yield "race", pairs[pairs["dimension"] == "race"]
    yield "all", pairs


def test_units(sub: pd.DataFrame, effect: pd.Series, scope: str) -> tuple[pd.Series, str]:
    """Independent units for inference: pairs within a dimension; experiment IDs when pooled.

    The gender and race pairs of one experiment ID ran at the same time with the same
    creative, so they are averaged before pooled tests and the pooled bootstrap.
    """
    if scope == "all":
        return effect.groupby(sub["exp_id"]).mean(), "experiment ID (n=18; gender and race pairs averaged)"
    return effect, "matched pair (n=18)"


SUMMARY_SPECS = [
    ("variance", "Reported variance, dimension-matched (%)", "diff", "d_variance_pp", 100),
    ("reach", "Unique reach (accounts reached)", "pct", "pct_reach", 1),
    ("impressions", "Impressions", "pct", "pct_impressions", 1),
    ("frequency", "Impressions per account reached", "pct", "pct_frequency", 1),
    ("cpp", "Cost per 1,000 accounts reached (USD)", "pct", "pct_cpp", 1),
    ("cpm", "Cost per 1,000 impressions (USD)", "pct", "pct_cpm", 1),
    ("spend", "Spend (USD)", "pct", "pct_spend", 1),
]


def paired_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, label, kind, effect_col, scale in SUMMARY_SPECS:
        for scope, sub in scopes(pairs):
            effect = sub[effect_col]
            units, unit_label = test_units(sub, effect, scope)
            low, high = bootstrap_ci(units)
            off, on = sub[f"{key}_off"] * scale, sub[f"{key}_on"] * scale
            by_creative = effect.groupby(sub["creative"]).mean()
            rows.append(
                {
                    "metric": label,
                    "scope": scope,
                    "n_pairs": len(sub),
                    "mean_off": off.mean(),
                    "mean_on": on.mean(),
                    "median_off": off.median(),
                    "median_on": on.median(),
                    "effect_definition": "on minus off (percentage points)" if kind == "diff" else "% change, on vs off",
                    "mean_effect": effect.mean(),
                    "median_effect": effect.median(),
                    "ci95_low_mean_effect": low,
                    "ci95_high_mean_effect": high,
                    "pct_change_of_means": (on.mean() / off.mean() - 1) * 100 if kind == "pct" else np.nan,
                    "n_lower_with_vrs": int((effect < 0).sum()),
                    "n_higher_with_vrs": int((effect > 0).sum()),
                    "creatives_with_lower_mean": int((by_creative < 0).sum()),
                    "n_creatives": len(by_creative),
                    "wilcoxon_p": wilcoxon_exact(units),
                    "sign_test_p": sign_test(units),
                    "inference_unit": unit_label,
                }
            )
    return pd.DataFrame(rows)


def creative_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    grouped = pairs.groupby(["dimension", "creative"], sort=False)
    out = grouped.agg(
        n_pairs=("pair_id", "size"),
        mean_d_variance_pp=("d_variance_pp", "mean"),
        mean_pct_reach=("pct_reach", "mean"),
        n_reach_lower=("pct_reach", lambda s: int((s < 0).sum())),
        mean_pct_cpp=("pct_cpp", "mean"),
        n_cpp_higher=("pct_cpp", lambda s: int((s > 0).sum())),
        mean_pct_g1_reach=("pct_g1_reach", "mean"),
        mean_pct_g2_reach=("pct_g2_reach", "mean"),
    ).reset_index()
    out["creative_label"] = out["creative"].map(CREATIVES)
    out["creative"] = pd.Categorical(out["creative"], CREATIVE_ORDER, ordered=True)
    return out.sort_values(["dimension", "creative"]).reset_index(drop=True)


def tradeoff_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scope, sub in scopes(pairs):
        if scope == "all":
            continue  # gender and race variance changes differ in scale; analysed separately
        dv, dr, dc = sub["d_variance_pp"], sub["pct_reach"], sub["pct_cpp"]
        rows.append(
            {
                "scope": scope,
                "n_pairs": len(sub),
                "variance_lower_reach_lower": int(((dv < 0) & (dr < 0)).sum()),
                "variance_lower_reach_not_lower": int(((dv < 0) & (dr >= 0)).sum()),
                "variance_not_lower_reach_lower": int(((dv >= 0) & (dr < 0)).sum()),
                "variance_not_lower_reach_not_lower": int(((dv >= 0) & (dr >= 0)).sum()),
                "spearman_dvariance_vs_pct_reach": spearman(dv, dr),
                "perm_p_dvariance_vs_pct_reach": spearman_perm_p(dv, dr),
                "spearman_dvariance_vs_pct_cpp": spearman(dv, dc),
                "perm_p_dvariance_vs_pct_cpp": spearman_perm_p(dv, dc),
            }
        )
    return pd.DataFrame(rows)


def group_reach_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    """Per-group change in unique reach and cost per 1,000 reached (one row per group)."""
    rows = []
    for scope, sub in scopes(pairs):
        if scope == "all":
            continue
        for tag in ("g1", "g2"):
            name = sub[f"{tag}_name"].iat[0]
            eff = sub[f"pct_{tag}_reach"]
            cost = sub[f"pct_{tag}_cpp"]
            rows.append(
                {
                    "scope": scope,
                    "group": f"{name} (DMA-inferred)" if scope == "race" else name,
                    "n_pairs": len(sub),
                    "mean_reach_off": sub[f"{tag}_reach_off"].mean(),
                    "mean_reach_on": sub[f"{tag}_reach_on"].mean(),
                    "mean_pct_change_reach": eff.mean(),
                    "median_pct_change_reach": eff.median(),
                    "n_pairs_reach_lower": int((eff < 0).sum()),
                    "wilcoxon_p_reach": wilcoxon_exact(eff),
                    "mean_pct_change_cpp": cost.mean(),
                    "n_pairs_cpp_higher": int((cost > 0).sum()),
                    "n_pairs_overdelivered_without_vrs": int((sub["overdelivered_group_off"] == name).sum()),
                }
            )
    return pd.DataFrame(rows)


def reach_pattern_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    """How each pair's two groups moved in unique reach (counts by pattern)."""
    rows = []
    for scope, sub in scopes(pairs):
        row = {"scope": scope, "n_pairs": len(sub)}
        for pattern in REACH_PATTERNS:
            row[pattern] = int((sub["reach_pattern"] == pattern).sum())
        row["leveling_down (both lose reach AND variance lower)"] = int(sub["leveling_down"].sum())
        row["leveling_down_pair_ids"] = ", ".join(sorted(sub.loc[sub["leveling_down"], "pair_id"]))
        rows.append(row)
    return pd.DataFrame(rows)


def impressions_vs_reach(pairs: pd.DataFrame, dep: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    levels = (
        dep.groupby(["dimension", "condition"])
        .agg(
            n_deployments=("exp_id", "size"),
            g1_name=("g1_name", "first"),
            g2_name=("g2_name", "first"),
            mean_g1_share_of_impressions=("g1_imp_share", "mean"),
            mean_g1_share_of_reach=("g1_reach_share", "mean"),
            mean_g1_frequency=("g1_frequency", "mean"),
            mean_g2_frequency=("g2_frequency", "mean"),
            mean_frequency_ratio_g1_over_g2=("frequency_ratio", "mean"),
            mean_variance_impressions_pct=("variance", lambda s: s.mean() * 100),
            mean_reach_share_variance_analog_pct=("reach_share_variance_analog", lambda s: s.mean() * 100),
        )
        .reset_index()
    )
    levels["mean_imp_minus_reach_share_pp"] = (
        levels["mean_g1_share_of_impressions"] - levels["mean_g1_share_of_reach"]
    ) * 100
    rows = []
    effects = [
        ("d_g1_imp_share_pp", "Group 1 share of impressions (pp change)"),
        ("d_g1_reach_share_pp", "Group 1 share of unique reach (pp change)"),
        ("d_frequency_ratio", "Frequency ratio, group 1 / group 2 (change)"),
        ("d_variance_pp", "Variance on impression shares (pp change)"),
        ("d_reach_variance_analog_pp", "Same formula on reach shares (pp change)"),
    ]
    for scope, sub in scopes(pairs):
        if scope == "all":
            continue
        for col, label in effects:
            eff = sub[col]
            rows.append(
                {
                    "scope": scope,
                    "group_1": sub["g1_name"].iat[0],
                    "quantity": label,
                    "mean_change": eff.mean(),
                    "median_change": eff.median(),
                    "n_negative": int((eff < 0).sum()),
                    "n_positive": int((eff > 0).sum()),
                    "wilcoxon_p": wilcoxon_exact(eff),
                }
            )
    return levels, pd.DataFrame(rows)


def benchmark_sensitivity(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, slug in BENCHMARK_SLUGS.items():
        for scope, sub in scopes(pairs):
            if scope == "all":
                continue
            off, on = sub[f"variance_{slug}_off"] * 100, sub[f"variance_{slug}_on"] * 100
            d = sub[f"d_variance_{slug}_pp"]
            ref = BENCHMARKS[name][scope]
            rows.append(
                {
                    "reference_distribution": name,
                    "scope": scope,
                    "reference_g1_g2": f"{ref[0]:.2f} / {ref[1]:.2f}",
                    "mean_variance_off_pct": off.mean(),
                    "mean_variance_on_pct": on.mean(),
                    "mean_change_pp": d.mean(),
                    "n_lower_with_vrs": int((d < 0).sum()),
                    "n_off_below_10pct": int((off < 10).sum()),
                    "n_on_below_10pct": int((on < 10).sum()),
                    "n_off_below_5pct": int((off < 5).sum()),
                    "n_on_below_5pct": int((on < 5).sum()),
                    "wilcoxon_p": wilcoxon_exact(d),
                }
            )
    return pd.DataFrame(rows)


def cross_dimension(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scope, sub in scopes(pairs):
        if scope == "all":
            continue
        other = "race" if scope == "gender" else "gender"
        d = sub["d_variance_other_pp"]
        rows.append(
            {
                "pairs": f"{scope} pairs",
                "variance_measured": f"{other} variance",
                "n_pairs": len(sub),
                "mean_off_pct": sub["variance_other_dimension_off"].mean() * 100,
                "mean_on_pct": sub["variance_other_dimension_on"].mean() * 100,
                "mean_change_pp": d.mean(),
                "n_lower_with_vrs": int((d < 0).sum()),
                "wilcoxon_p": wilcoxon_exact(d),
            }
        )
    return pd.DataFrame(rows)


def paper_comparison(pairs: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    g = pairs[pairs["dimension"] == "gender"]
    r = pairs[pairs["dimension"] == "race"]
    ha = pairs[pairs["creative"] == "HA"]
    # The paper's eligible-ratio estimate is the mean delivery ratio over all
    # VRS-enabled ads; every deployment carries both race and gender breakdowns.
    on = data[data["condition"] == "on"]
    eligible = {
        "Black": (on["b_impressions"] / on["total_imp_r"]).mean(),
        "White": (on["w_impressions"] / on["total_imp_r"]).mean(),
        "Male": (on["m_impressions"] / on["total_imp_g"]).mean(),
        "Female": (on["f_impressions"] / on["total_imp_g"]).mean(),
    }
    lev = sorted(ha.loc[ha["leveling_down"], "pair_id"])
    cpp_not_up = sorted(ha.loc[ha["pct_cpp"] <= 0, "pair_id"])
    group_cpp_down = sorted(ha.loc[(ha["pct_g1_cpp"] <= 0) | (ha["pct_g2_cpp"] <= 0), "pair_id"])
    reach_mean = pairs["pct_reach"].mean()
    reach_of_means = (pairs["reach_on"].mean() / pairs["reach_off"].mean() - 1) * 100
    cpp_mean = pairs["pct_cpp"].mean()
    cpp_of_means = (pairs["cpp_on"].mean() / pairs["cpp_off"].mean() - 1) * 100

    def status(match: bool, close: bool = False) -> str:
        return "reproduced" if match else ("close, not exact" if close else "differs")

    rows = [
        (
            "Mean change in unique reach, 36 pairs",
            f"{PAPER_REPORTED['reach_pct']:+.2f}%",
            f"{reach_mean:+.2f}% (mean of per-pair % changes); {reach_of_means:+.2f}% (change in mean reach)",
            status(abs(reach_mean - PAPER_REPORTED["reach_pct"]) < 0.005, abs(reach_mean - PAPER_REPORTED["reach_pct"]) < 0.5),
        ),
        (
            "Mean change in cost per 1,000 reached, 36 pairs",
            f"{PAPER_REPORTED['cpp_pct']:+.2f}%",
            f"{cpp_mean:+.2f}% (mean of per-pair % changes); {cpp_of_means:+.2f}% (change in mean CPP)",
            status(abs(cpp_mean - PAPER_REPORTED["cpp_pct"]) < 0.005, abs(cpp_mean - PAPER_REPORTED["cpp_pct"]) < 0.5),
        ),
        (
            "Race pairs: variance > 10% without VRS",
            f"{PAPER_REPORTED['race_off_above_10']} of 18",
            f"{int((r['variance_off'] > 0.10).sum())} of 18",
            status(int((r["variance_off"] > 0.10).sum()) == PAPER_REPORTED["race_off_above_10"]),
        ),
        (
            "Race pairs: variance < 10% with VRS",
            f"{PAPER_REPORTED['race_on_below_10']} of 18",
            f"{int((r['variance_on'] < 0.10).sum())} of 18",
            status(int((r["variance_on"] < 0.10).sum()) == PAPER_REPORTED["race_on_below_10"]),
        ),
        (
            "Race pairs: variance < 5% with VRS",
            f"{PAPER_REPORTED['race_on_below_5']} of 18",
            f"{int((r['variance_on'] < 0.05).sum())} of 18",
            status(int((r["variance_on"] < 0.05).sum()) == PAPER_REPORTED["race_on_below_5"]),
        ),
        (
            "Gender pairs: variance < 5% without VRS",
            f"{PAPER_REPORTED['gender_off_below_5']} of 18",
            f"{int((g['variance_off'] < 0.05).sum())} of 18",
            status(int((g["variance_off"] < 0.05).sum()) == PAPER_REPORTED["gender_off_below_5"]),
        ),
        (
            "Eligible-ratio estimate = mean impression share over the 36 VRS-on ads (Black / White / Male / Female)",
            " / ".join(f"{PAPER_REPORTED['eligible_ratio'][k]:.2f}" for k in ("Black", "White", "Male", "Female")),
            " / ".join(f"{eligible[k]:.3f}" for k in ("Black", "White", "Male", "Female")),
            "reproduced"
            if all(round(eligible[k], 2) == PAPER_REPORTED["eligible_ratio"][k] for k in eligible)
            else "rounds to reported value for "
            + ", ".join(k for k in eligible if round(eligible[k], 2) == PAPER_REPORTED["eligible_ratio"][k])
            + "; not for "
            + ", ".join(k for k in eligible if round(eligible[k], 2) != PAPER_REPORTED["eligible_ratio"][k]),
        ),
        (
            "Hair-product (HA) pairs where both groups lose reach",
            ", ".join(PAPER_REPORTED["ha_leveling_down"]),
            ", ".join(lev) if lev else "none",
            status(lev == PAPER_REPORTED["ha_leveling_down"]),
        ),
        (
            "HA pairs where cost per 1,000 reached does not rise",
            ", ".join(PAPER_REPORTED["ha_cpp_not_up"]),
            f"total CPP: {', '.join(cpp_not_up) if cpp_not_up else 'none'}; "
            f"at least one group's CPP: {', '.join(group_cpp_down) if group_cpp_down else 'none'}",
            "reproduced"
            if cpp_not_up == PAPER_REPORTED["ha_cpp_not_up"]
            else (
                "matches only if group-level CPP is counted (definition not stated in paper)"
                if group_cpp_down == PAPER_REPORTED["ha_cpp_not_up"]
                else "differs"
            ),
        ),
    ]
    return pd.DataFrame(rows, columns=["quantity", "reported_by_original_researchers", "independently_computed", "status"])


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def set_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 8.5,
            "axes.titlesize": 9,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.labelsize": 8.5,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "grid.linestyle": "-",
            "xtick.color": AXIS,
            "ytick.color": AXIS,
            "xtick.labelcolor": INK_2,
            "ytick.labelcolor": INK_2,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def signed(x: float, digits: int = 1, suffix: str = "") -> str:
    return f"{x:+.{digits}f}{suffix}".replace("-", "−")


def save(fig, stem: str) -> list[Path]:
    paths = [FIG_DIR / f"{stem}.png", FIG_DIR / f"{stem}.pdf"]
    for path in paths:
        fig.savefig(path)
    plt.close(fig)
    return paths


def note(ax, text: str, x: float = 0.02, y: float = 0.98, ha: str = "left", va: str = "top") -> None:
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va, fontsize=7.5, color=INK_2, linespacing=1.35)


def panel_title(ax, title: str, subtitle: str | None = None) -> None:
    """Bold panel title with an optional statistics line placed above the plot area."""
    n_lines = subtitle.count("\n") + 1 if subtitle else 0
    ax.set_title(title, fontsize=8.5, pad=4 + 10 * n_lines)
    if subtitle:
        ax.annotate(
            subtitle,
            xy=(0, 1),
            xycoords="axes fraction",
            xytext=(0, 3),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=7.5,
            color=INK_2,
            linespacing=1.3,
        )


def p_text(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def fig_variance(pairs: pd.DataFrame) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.5), sharey=True)
    for ax, (letter, dim) in zip(axes, (("A", "gender"), ("B", "race"))):
        sub = pairs[pairs["dimension"] == dim]
        off, on = sub["variance_off"] * 100, sub["variance_on"] * 100
        for o, n in zip(off, on):
            rising = n > o
            ax.plot([0, 1], [o, n], color=INK_2 if rising else AXIS, lw=1.1 if rising else 0.9, zorder=1)
        ax.scatter(np.zeros(len(off)), off, s=30, marker="s", color=COLOR_OFF, edgecolor="white", lw=0.8, zorder=3, label="VRS off")
        ax.scatter(np.ones(len(on)), on, s=34, marker="o", color=COLOR_ON, edgecolor="white", lw=0.8, zorder=3, label="VRS on")
        for level in (5, 10):
            ax.axhline(level, color=MUTED, lw=0.7, zorder=0)
            ax.text(1.42, level, f"{level}%", ha="right", va="bottom", fontsize=7, color=MUTED)
        ax.text(-0.1, off.median(), f"median\n{off.median():.1f}%", ha="right", va="center", fontsize=7.5, color=INK)
        ax.text(1.1, on.median(), f"median\n{on.median():.1f}%", ha="left", va="center", fontsize=7.5, color=INK)
        n_lower = int((on < off).sum())
        n_higher = len(sub) - n_lower
        label = "Gender pairs (female/male)" if dim == "gender" else "Race pairs (Black/White, DMA-inferred)"
        panel_title(ax, f"{letter}. {label}", f"Lower with VRS in {n_lower} of {len(sub)}; higher in {n_higher} (dark lines)")
        ax.set_xticks([0, 1], ["VRS off", "VRS on"])
        ax.set_xlim(-0.55, 1.45)
        ax.grid(axis="x", visible=False)
        ax.tick_params(axis="x", colors=INK_2, length=0)
    axes[0].set_ylabel("Reported variance (%)")
    axes[0].set_ylim(bottom=0)
    fig.tight_layout(w_pad=2.0)
    return save(fig, "fig1_variance_paired")


def fig_reach_cost(pairs: pd.DataFrame) -> list[Path]:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), sharey=True, sharex="col")
    ypos = {c: len(CREATIVE_ORDER) - 1 - i for i, c in enumerate(CREATIVE_ORDER)}
    offsets = {1: 0.17, 2: 0.0, 3: -0.17}
    panels = [
        ("A", "gender", "pct_reach", "Gender pairs: unique reach"),
        ("B", "gender", "pct_cpp", "Gender pairs: cost per 1,000 reached"),
        ("C", "race", "pct_reach", "Race pairs: unique reach"),
        ("D", "race", "pct_cpp", "Race pairs: cost per 1,000 reached"),
    ]
    for ax, (letter, dim, col, title) in zip(axes.flat, panels):
        sub = pairs[pairs["dimension"] == dim]
        y = sub["creative"].map(ypos) + sub["replicate"].map(offsets)
        ax.axvline(0, color=MUTED, lw=0.8, zorder=1)
        ax.scatter(sub[col], y, s=26, color=COLOR_ON, edgecolor="white", lw=0.8, zorder=3)
        means = sub.groupby("creative")[col].mean()
        ax.scatter(means.values, [ypos[c] for c in means.index], marker="|", s=110, color=INK, lw=1.4, zorder=4)
        n_dir = int((sub[col] < 0).sum()) if col == "pct_reach" else int((sub[col] > 0).sum())
        word = "lower" if col == "pct_reach" else "higher"
        panel_title(ax, f"{letter}. {title}", f"Mean {signed(sub[col].mean(), 1, '%')}; {word} with VRS in {n_dir} of {len(sub)} pairs")
        ax.grid(axis="y", visible=False)
    for ax in axes[:, 0]:
        ax.set_yticks(list(ypos.values()), [f"{c}  {CREATIVES[c]}" for c in CREATIVE_ORDER])
        ax.tick_params(axis="y", length=0)
    for ax in axes[1, :]:
        ax.set_xlabel("% change with VRS on (vs. off)")
    axes[0, 0].set_ylim(-0.6, len(CREATIVE_ORDER) - 0.4)
    fig.text(0.99, 0.005, "Dots: replicates 1–3 (top to bottom). Black tick: creative mean.", ha="right", va="bottom", fontsize=7, color=MUTED)
    fig.tight_layout(h_pad=1.4, w_pad=1.6, rect=(0, 0.02, 1, 1))
    return save(fig, "fig2_reach_cost_by_creative")


def fig_tradeoff(pairs: pd.DataFrame, trade: pd.DataFrame) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.3), sharey=True)
    for ax, (letter, dim) in zip(axes, (("A", "gender"), ("B", "race"))):
        sub = pairs[pairs["dimension"] == dim]
        row = trade.set_index("scope").loc[dim]
        ax.axhline(0, color=MUTED, lw=0.8, zorder=1)
        ax.axvline(0, color=MUTED, lw=0.8, zorder=1)
        ax.scatter(sub["d_variance_pp"], sub["pct_reach"], s=30, color=COLOR_ON, edgecolor="white", lw=0.8, zorder=3)
        both = int(row["variance_lower_reach_lower"])
        panel_title(
            ax,
            f"{letter}. {dim.capitalize()} pairs (n = {len(sub)})",
            f"Variance lower and reach lower: {both} of {len(sub)}\n"
            f"Spearman ρ = {signed(row['spearman_dvariance_vs_pct_reach'], 2)} "
            f"(permutation {p_text(row['perm_p_dvariance_vs_pct_reach'])})",
        )
        ax.set_xlabel("Change in reported variance (percentage points)")
        if dim == "gender":
            lim = max(abs(sub["d_variance_pp"]).max(), 1) * 1.15
            ax.set_xlim(-lim, lim)
        else:
            ax.set_xlim(sub["d_variance_pp"].min() * 1.1, max(1.0, sub["d_variance_pp"].max() + 1))
    axes[0].set_ylabel("% change in unique reach")
    fig.tight_layout(w_pad=2.0)
    return save(fig, "fig3_variance_vs_reach")


def fig_impressions_vs_reach(dep: pd.DataFrame) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.6))
    for ax, (letter, dim) in zip(axes, (("A", "race"), ("B", "gender"))):
        sub = dep[dep["dimension"] == dim]
        g1 = sub["g1_name"].iat[0]
        ref = BENCHMARKS[PAPER_BENCHMARK][dim][0]
        x, y = sub["g1_reach_share"] * 100, sub["g1_imp_share"] * 100
        lo = math.floor(min(x.min(), y.min(), ref * 100) - 2)
        hi = math.ceil(max(x.max(), y.max(), ref * 100) + 2)
        ax.plot([lo, hi], [lo, hi], color=MUTED, lw=0.8, zorder=1)
        ax.axhline(ref * 100, color=AXIS, lw=0.9, zorder=1)
        if dim == "race":
            label_x, label_y, label_ha, label_va = hi - 0.3, ref * 100 + 0.3, "right", "bottom"
        else:
            label_x, label_y, label_ha, label_va = lo + 0.3, ref * 100 - 0.2, "left", "top"
        ax.text(label_x, label_y, f"eligible-ratio estimate {ref * 100:.0f}%", ha=label_ha, va=label_va, fontsize=7, color=MUTED)
        ax.text(hi - 0.3, hi - 0.6, "equal shares", ha="right", va="top", fontsize=7, color=MUTED, rotation=45, rotation_mode="anchor")
        for cond, color, marker, label in (("off", COLOR_OFF, "s", "VRS off"), ("on", COLOR_ON, "o", "VRS on")):
            part = sub[sub["condition"] == cond]
            ax.scatter(part["g1_reach_share"] * 100, part["g1_imp_share"] * 100, s=30, marker=marker, color=color, edgecolor="white", lw=0.8, zorder=3, label=label)
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal")
        step = 5 if hi - lo > 25 else 2
        ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(step))
        ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(step))
        group = "Black (DMA-inferred)" if dim == "race" else "Female"
        ax.set_title(f"{letter}. {group} share, {dim} deployments", fontsize=8.5)
        ax.set_xlabel(f"{group} share of unique reach (%)")
        ax.set_ylabel(f"{group} share of impressions (%)")
        if dim == "race":
            ax.legend(loc="upper left", handletextpad=0.3)
            note(ax, "Above the diagonal: more impressions\nper account reached than the other group", x=0.98, y=0.03, ha="right", va="bottom")
    fig.tight_layout(w_pad=2.5)
    return save(fig, "fig4_impressions_vs_reach_shares")


def fig_group_reach(pairs: pd.DataFrame) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.5))
    for ax, (letter, dim) in zip(axes, (("A", "race"), ("B", "gender"))):
        sub = pairs[pairs["dimension"] == dim]
        g1, g2 = sub["g1_name"].iat[0], sub["g2_name"].iat[0]
        x, y = sub["pct_g1_reach"], sub["pct_g2_reach"]
        pad = 5
        xlo, xhi = min(x.min(), 0) - pad, max(x.max(), 0) + pad
        ylo, yhi = min(y.min(), 0) - pad, max(y.max(), 0) + pad
        ax.fill_between([xlo, 0], ylo, 0, color=SHADE, zorder=0, lw=0)
        ax.axhline(0, color=MUTED, lw=0.8, zorder=1)
        ax.axvline(0, color=MUTED, lw=0.8, zorder=1)
        ax.scatter(x, y, s=30, color=COLOR_ON, edgecolor="white", lw=0.8, zorder=3)
        label_offsets = {"HA1-g": (-6, -10, "right"), "HA3-g": (-6, 5, "right")}
        for _, row in sub[sub["creative"] == "HA"].iterrows():
            dx, dy, ha = label_offsets.get(row["pair_id"], (4, 3, "left"))
            ax.annotate(
                row["pair_id"],
                (row["pct_g1_reach"], row["pct_g2_reach"]),
                xytext=(dx, dy),
                textcoords="offset points",
                ha=ha,
                fontsize=6.5,
                color=INK_2,
            )
        ax.set_xlim(xlo, xhi)
        ax.set_ylim(ylo, yhi)
        n_both = int(((x < 0) & (y < 0)).sum())
        ax.text(xlo + 1, ylo + 1, f"Both groups lose reach: {n_both} of {len(sub)}", ha="left", va="bottom", fontsize=7.5, color=INK_2)
        g1_label = "Black (DMA-inferred)" if dim == "race" else g1
        g2_label = "White (DMA-inferred)" if dim == "race" else g2
        ax.set_title(f"{letter}. {dim.capitalize()} pairs (n = {len(sub)})", fontsize=8.5)
        ax.set_xlabel(f"% change in {g1_label} unique reach")
        ax.set_ylabel(f"% change in {g2_label} unique reach")
    fig.tight_layout(w_pad=2.5)
    return save(fig, "fig5_group_reach_changes")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def key_results(checks, n_sentinel, summary, trade, groups, patterns, ivr_levels, ivr_paired, bench, cross, paper) -> list[str]:
    lines = ["KEY RESULTS (independently computed unless labelled 'paper')", ""]
    lines.append("Data checks:")
    for k, v in checks.items():
        lines.append(f"  {k}: {v}")
    lines.append(f"  -1 cost sentinels set to NaN: {n_sentinel}")
    lines.append("")
    for _, r in summary.iterrows():
        lines.append(
            f"[{r['scope']:6s}] {r['metric']}: off mean {r['mean_off']:.4g}, on mean {r['mean_on']:.4g}; "
            f"mean effect {r['mean_effect']:+.3f} (median {r['median_effect']:+.3f}; 95% CI {r['ci95_low_mean_effect']:+.3f} to "
            f"{r['ci95_high_mean_effect']:+.3f}); lower {r['n_lower_with_vrs']}/{r['n_pairs']}; "
            f"creatives lower {r['creatives_with_lower_mean']}/{r['n_creatives']}; Wilcoxon p {fmt_p(r['wilcoxon_p'])}; "
            f"sign p {fmt_p(r['sign_test_p'])} [{r['inference_unit']}]"
        )
    lines.append("")
    lines.append("Trade-off (variance change vs reach change):")
    lines.extend("  " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()) for row in trade.to_dict("records"))
    lines.append("")
    lines.append("Group-level reach and cost:")
    lines.extend("  " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()) for row in groups.to_dict("records"))
    lines.append("")
    lines.append("Reach patterns (leveling down):")
    lines.extend("  " + ", ".join(f"{k}={v}" for k, v in row.items()) for row in patterns.to_dict("records"))
    lines.append("")
    lines.append("Impressions vs reach (levels by dimension and condition):")
    lines.extend("  " + ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()) for row in ivr_levels.to_dict("records"))
    lines.append("")
    lines.append("Impressions vs reach (paired changes):")
    lines.extend("  " + ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()) for row in ivr_paired.to_dict("records"))
    lines.append("")
    lines.append("Benchmark sensitivity:")
    lines.extend("  " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()) for row in bench.to_dict("records"))
    lines.append("")
    lines.append("Cross-dimension variance:")
    lines.extend("  " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()) for row in cross.to_dict("records"))
    lines.append("")
    lines.append("Paper-reported vs independently computed:")
    lines.extend(f"  {r['quantity']}: paper {r['reported_by_original_researchers']} | computed {r['independently_computed']} | {r['status']}" for _, r in paper.iterrows())
    return lines


def main(argv: list[str]) -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    zip_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_ZIP
    if not zip_path.exists():
        raise FileNotFoundError(f"Public ZIP not found: {zip_path}")
    digest = sha256(zip_path)
    if digest != EXPECTED_SHA256:
        raise ValueError(f"ZIP SHA-256 {digest} does not match the audited archive {EXPECTED_SHA256}")
    print(f"ZIP: {zip_path}  (SHA-256 verified)")

    data, n_sentinel = clean(load_primary(zip_path))
    checks = validate(data)
    dep = deployment_table(data)
    pairs = build_pairs(dep)

    summary = paired_summary(pairs)
    creatives = creative_summary(pairs)
    trade = tradeoff_summary(pairs)
    groups = group_reach_summary(pairs)
    patterns = reach_pattern_summary(pairs)
    ivr_levels, ivr_paired = impressions_vs_reach(pairs, dep)
    bench = benchmark_sensitivity(pairs)
    cross = cross_dimension(pairs)
    paper = paper_comparison(pairs, data)

    OUT_DIR.mkdir(exist_ok=True)
    FIG_DIR.mkdir(exist_ok=True)
    tables = {
        "deployments_72.csv": dep,
        "pairs_36.csv": pairs,
        "summary_paired.csv": summary,
        "summary_by_creative.csv": creatives,
        "tradeoff_variance_vs_reach.csv": trade,
        "group_reach_changes.csv": groups,
        "reach_patterns_leveling_down.csv": patterns,
        "impressions_vs_reach_levels.csv": ivr_levels,
        "impressions_vs_reach_paired.csv": ivr_paired,
        "variance_benchmark_sensitivity.csv": bench,
        "variance_cross_dimension.csv": cross,
        "paper_vs_independent.csv": paper,
    }
    for name, table in tables.items():
        table.to_csv(OUT_DIR / name, index=False, float_format="%.6f", encoding="utf-8")

    set_style()
    figures = []
    figures += fig_variance(pairs)
    figures += fig_reach_cost(pairs)
    figures += fig_tradeoff(pairs, trade)
    figures += fig_impressions_vs_reach(dep)
    figures += fig_group_reach(pairs)

    lines = key_results(checks, n_sentinel, summary, trade, groups, patterns, ivr_levels, ivr_paired, bench, cross, paper)
    (OUT_DIR / "key_results.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {len(tables)} tables to {OUT_DIR}")
    print(f"Wrote {len(figures)} figure files to {FIG_DIR}")
    if sha256(zip_path) != EXPECTED_SHA256:
        raise RuntimeError("Source ZIP changed during the run")
    print("Source ZIP unchanged (SHA-256 re-verified).")


if __name__ == "__main__":
    main(sys.argv)
