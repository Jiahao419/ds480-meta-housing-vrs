# ds480-meta-housing-vrs
DS480 analysis of fairness and reach in Meta housing ad delivery (VRS)

## What this project analyzes

`meta_vrs/analyze_vrs.py` is a reproducible paired analysis of Meta's **Variance Reduction System (VRS)**, using the public audit data from Imana, Shen, Heidemann and Korolova, *External Evaluation of Discrimination Mitigation Efforts in Meta's Ad Delivery* (ACM FAccT 2025, [arXiv:2506.16560](https://arxiv.org/abs/2506.16560)).

It builds the **36 matched VRS On/Off comparisons** in `data_vrs_vs_novrs.csv`: 6 ad creatives × 3 replicates × 2 dimensions (gender, race). Each of the 72 ad deployments is used in exactly one pair. For each pair it compares:

- the researchers' reported **race and gender delivery variance**, and how sensitive it is to the reference distribution;
- **unique reach**, **impressions**, impressions per account reached, **cost per 1,000 people reached** and cost per 1,000 impressions;
- whether lower variance is accompanied by **reduced reach**, both overall and for each demographic group ("leveling down");
- each group's share of **impressions versus its share of unique reach**;
- the values reported in the paper against the values computed here.

The ads are controlled probe ads that the researchers declared as housing ads to switch VRS on; they are not real housing listings. Race is inferred from geography (DMA audience partitions), not observed directly. A measured disparity is not, by itself, evidence of discrimination.

## Data

The dataset is public but **not included in this repository**.

- Source: <https://ant.isi.edu/datasets/addelivery-vrs/>
- File: `vrs_ad_delivery_data-2025-05-23.zip`
- SHA-256: `ed37bcca5485f558f1e2bd55f0175dca4247a1901bd5319046a2bb2c64f4cf5d`

Download the ZIP and save it, unchanged, as:

```
meta_vrs/data_raw/vrs_ad_delivery_data-2025-05-23.zip
```

For example, on macOS or Linux:

```bash
mkdir -p meta_vrs/data_raw && curl -L -o meta_vrs/data_raw/vrs_ad_delivery_data-2025-05-23.zip https://ant.isi.edu/datasets/addelivery-vrs/vrs_ad_delivery_data-2025-05-23.zip
```

The script opens the ZIP read-only, without extracting it. It checks the SHA-256 before and after the run, and stops if the archive differs from the audited version.

## Install

You need Python 3.10 or newer. From the repository root:

```bash
python -m pip install -r meta_vrs/requirements.txt
```

The dependencies are pandas, numpy and matplotlib; SciPy is not needed. The code was tested with Python 3.14 / pandas 3.0 and with Python 3.13 / pandas 2.3, which produce identical tables.

## Run

From the repository root:

```bash
python meta_vrs/analyze_vrs.py
```

If the ZIP is stored somewhere else, pass its path as the first argument:

```bash
python meta_vrs/analyze_vrs.py path/to/vrs_ad_delivery_data-2025-05-23.zip
```

The script prints the key results and finishes in about 10 seconds. The results are deterministic: the bootstrap and permutation tests use 10,000 draws with seed 480.

## Outputs

The script writes tables to `meta_vrs/output/` and figures to `meta_vrs/figures/`, creating both folders if needed.

| File | Content |
|---|---|
| `output/pairs_36.csv` | One row per matched pair: Off/On values, paired changes, group reach, reach pattern |
| `output/deployments_72.csv` | One row per deployment: derived shares, frequencies, costs, variance under alternative references |
| `output/summary_paired.csv` | Paired summaries: means, medians, bootstrap 95% CIs, exact Wilcoxon and sign tests |
| `output/summary_by_creative.csv` | Creative-level means |
| `output/tradeoff_variance_vs_reach.csv` | Variance-change vs. reach-change quadrant counts and Spearman correlations |
| `output/group_reach_changes.csv` | Reach and cost changes for each demographic group |
| `output/reach_patterns_leveling_down.csv` | How each pair's two groups moved in reach; leveling-down counts |
| `output/impressions_vs_reach_levels.csv` | Group shares of impressions vs. unique reach, and frequencies, by condition |
| `output/impressions_vs_reach_paired.csv` | Paired changes in those shares and frequencies |
| `output/variance_benchmark_sensitivity.csv` | Variance recomputed under three reference distributions |
| `output/variance_cross_dimension.csv` | Race variance in gender pairs, and gender variance in race pairs |
| `output/paper_vs_independent.csv` | Values reported in the paper vs. values computed here |
| `output/key_results.txt` | Plain-text log of the data checks and all key numbers |
| `figures/fig1_variance_paired.{png,pdf}` | Reported variance, VRS off vs. on, per pair |
| `figures/fig2_reach_cost_by_creative.{png,pdf}` | % change in unique reach and cost per 1,000 reached, by creative |
| `figures/fig3_variance_vs_reach.{png,pdf}` | Change in variance vs. % change in unique reach |
| `figures/fig4_impressions_vs_reach_shares.{png,pdf}` | Group share of impressions vs. share of unique reach |
| `figures/fig5_group_reach_changes.{png,pdf}` | % change in each group's unique reach |

PNG figures are 300 dpi; PDF figures are vector.

## Methods in brief

- **Pairing.** A pair is the VRS-on and VRS-off deployment with the same `exp_id` and dimension (`g-vrs`/`g-novrs`, `r-vrs`/`r-novrs`). The script asserts complete, concurrent, 24-hour, non-duplicated sets.
- **Data handling.**
  - `-1` cost values are treated as undefined (NaN).
  - Cost per 1,000 reached is recomputed as spend ÷ unique reach × 1,000; the dataset README's "per 100" label is incorrect.
  - Gender pairs use the gender-report totals and race pairs the race-report totals.
  - Unknown-group unit-cost fields are not used.
  - The script's comments refer to these rules as coming from `DATA_QA.md`, a separate data-quality audit that is not included in this repository.
- **Reported variance.** ½ · (|s₁ − e₁| + |s₂ − e₂|), computed on impression shares. The references are the paper's eligible-ratio estimate: 0.42 / 0.58 for Black / White and 0.55 / 0.45 for female / male. The script checks that this formula reproduces the dataset's variance columns exactly.
- **Statistics.**
  - Paired changes (On − Off, or % change).
  - Exact two-sided Wilcoxon signed-rank and sign tests, with n = 18 pairs per dimension. When pooled, the gender and race pairs from the same experiment are averaged into 18 experiment-level units.
  - Percentile bootstrap 95% CIs.
  - Spearman correlations with permutation p-values.

## Repository layout

```
.
├── README.md
├── .gitignore
└── meta_vrs/
    ├── analyze_vrs.py
    ├── requirements.txt
    ├── data_raw/      # place the downloaded ZIP here (git-ignored)
    ├── output/        # created by the script
    └── figures/       # created by the script
```
