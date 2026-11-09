# Meta VRS public data: Python inspection (2026-11-08)

This is a data-quality record, not an essay and not a finding of unlawful discrimination.

## Source and integrity

- Study: Imana, Shen, Heidemann, and Korolova, *External Evaluation of Discrimination Mitigation Efforts in Meta's Ad Delivery*, ACM FAccT 2025.
- Public source: <https://ant.isi.edu/datasets/addelivery-vrs/>
- ZIP: <https://ant.isi.edu/datasets/addelivery-vrs/vrs_ad_delivery_data-2025-05-23.zip>
- ZIP SHA-256: `ed37bcca5485f558f1e2bd55f0175dca4247a1901bd5319046a2bb2c64f4cf5d`
- ZIP passes CRC integrity tests. Twenty archive members: 3 CSVs, a README, 6 image screenshots, 6 saved landing webpages, 2 directory entries, and 2 auxiliary/index files.

## Tables and row grain

| File | Shape | Row grain | Intended use |
| --- | ---: | --- | --- |
| `data_vrs_vs_novrs.csv` | 72 × 74 | One ad deployment in a four-row experiment | **Primary analysis**: VRS versus no VRS, separately for gender and race |
| `data_heccomp.csv` | 12 × 74 | One ad deployment in housing/job/credit comparison | Secondary analysis: HEC declaration comparison |
| `data_budget_split.csv` | 90 × 74 | 72 split-budget ad deployments **plus 18 derived aggregate rows** | Secondary analysis: alternative budget-splitting approach |

All CSVs share the same 74 column names (not necessarily the same missingness or meaning for every row type). Categories of columns:

- Experiment descriptors: `exp_id`, `exp_type`, `hec_cat` (3).
- Reported gender/race variance: `g-variance-eligible`, `r-variance-eligible` (2).
- Race groups (`b`, `w`, `or`) × clicks/reach/impressions/spend/CPM/CPC/CPP (21), plus four shares (`b_reach_frac`, `w_reach_frac`, `b_imp_frac`, `w_imp_frac`).
- Gender groups (`m`, `f`, `og`) × seven matching measurements (21), plus four shares (`m_reach_frac`, `f_reach_frac`, `m_imp_frac`, `f_imp_frac`).
- Race/gender total impressions/spend/reach/clicks/CPM/CPP: six metrics × two groups (12).
- Start/end timestamps (2); race proxy method (1); campaign/ad identifiers (4).

## Audit outcomes

- **Main comparison:** 18 creative/replicate experiment IDs, 4 rows per ID (`g-vrs`, `g-novrs`, `r-vrs`, `r-novrs`) and **36 complete matched On/Off comparisons**. Six creatives (HA, GA, EA, EB, IA, FA), each with three repeats. No blank cells or duplicate *complete rows*. All 72 deployments are exactly 24 hours.
- **HEC comparison:** 12 rows (3 housing, 3 no-VRS, 3 job, 3 credit), no blank cells. **Six housing/no-VRS rows repeat measurements in the main CSV**. Do not concatenate all records and treat them as independent observations.
- **Budget splitting:** 18 IDs × 5 rows: four demographic-targeted campaigns plus one derived aggregate. All **240 blank cells occur only on aggregate rows**. These are not 18 extra real campaigns. Four individually targeted rows per ID have complete fields, and all 72 are 24-hour deployments.
- Impressions and group breakdown totals reconcile in all files; all total CPM and CPP calculations independently reconcile. Black/White/Male/Female unit-cost fields reconcile in 1,928 valid checks (863 + 141 + 924). Variance fields are within [0, 1].

## Data issues and rules for subsequent analysis

1. **Incorrect README unit**. README says `cpp` = USD cost per **100** reached people. Numerical checks show the stored `*_cpp` = `spend / reach × 1,000` in all applicable rows. Use **cost per 1,000 unique people reached**.
2. **Implicit missing-value sentinels**. There are **160 `-1` values** in cost fields (1 primary, 3 HEC, 156 budget-split). All correspond to zero clicks, impressions or reach. Treat these as undefined costs (`NaN`), *not* negative money.
3. **Unreliable unknown-group unit costs**. `or_*` and `og_*` CPC/CPM/CPP can equal zero even when spending and the denominators are positive. If needed, recalculate from their spend and denominator instead of relying on those recorded unit-cost fields.
4. **Ad identifier precision**. All 72 primary and 72 individual budget-split deployment IDs are written in scientific notation in the CSVs. They are not safe for exact integer recovery or cross-file key matching. Preserve the raw string and use `(exp_id, exp_type)` for main-file experimental pairing.
5. **Race/gender reach totals sometimes differ by 1–2**, even though total impressions agree, consistent with different grouping/rounding or reporting. Use the matching race (`_r`) or gender (`_g`) reach columns; do not assume they are always identical.
6. **No underlying eligible-audience distribution**. The ZIP contains the study's **reported** `*-variance-eligible`, but not the detailed eligible-audience reference values or individual-level exposure data. We can compare reported variances but cannot reconstruct the exact benchmark independently.
7. **This is an audit of controlled probes**, not observed housing listings. The researchers deliberately declared *non-housing* creative ads to be housing ads to trigger VRS. The racial breakdown is inferred using geographically separated DMA audience partitions, not directly observed race. The paper acknowledges omitting a geographic "flip" validation in this study (Appendix B). Results cannot be generalized to all housing ads or interpreted as proof of intentional discrimination.

## Reproduce

With Python and pandas installed, run from the project folder:

```bash
python meta_vrs/qa_meta_vrs.py
```

The script reads the ZIP directly; it does not modify the source archive.

## Next stage, not yet executed

1. Build a tidy **36-pair** table comparing VRS On versus Off.
2. Examine `Δvariance`, `Δunique_reach` and `Δcost_per_1000_reach` overall, by race/gender experiment and by six ad creatives. Preserve the paired unit; do not treat 72 deployments as independent pairs.
3. Analyze Black/White and Female/Male proportions for *impressions versus unique reach*. Compare them with the disclosed baseline limitations.
4. Visualize paired changes and analyze counterexamples; keep uncertainty and small experimental sample in view.
5. Optionally compare the 18 budget-splitting aggregates to VRS experiments with a clearly stated comparison design.

The choice of what counts as **ethically relevant bias** remains the student's, not a statistical threshold chosen automatically by code.
