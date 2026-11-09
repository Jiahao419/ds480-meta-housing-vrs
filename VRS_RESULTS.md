# Meta's Variance Reduction System (VRS): paired On/Off analysis

Empirical results from the public audit dataset of Imana, Shen, Heidemann and Korolova, *External Evaluation of Discrimination Mitigation Efforts in Meta's Ad Delivery* (ACM FAccT 2025; [arXiv:2506.16560](https://arxiv.org/abs/2506.16560)). Data: `vrs_ad_delivery_data-2025-05-23.zip` (SHA-256 `ed37bcca…cf5d`), audited in `DATA_QA.md`. Code: `analyze_vrs.py`. Analysis date: 2026-11-08.

Throughout, **computed here** means calculated independently from the CSV. **Reported by the original researchers** means values stated in the paper or derived by them and stored in the dataset. Section 3.1 lists the two side by side.

---

## 1. What the data are

- **Probe ads, not housing listings.** There are six non-housing creatives: HA hair product, GA golf, EA and EB education (ASU, CSU), IA insurance and FA financial products. Each creative was run three times (replicates 1–3), with launch dates from 26 Nov to 17 Dec 2024. Each deployment ran for 24 hours on a budget of about $20. To trigger VRS, the researchers declared one copy of each ad as a housing ad (*VRS on*). The other copy was not declared (*VRS off*).
- **Audiences.** The audiences are North Carolina voter-list Custom Audiences, balanced by race and gender. Meta does not report race, so the researchers inferred it from geography. They took Black voters from one set of DMAs (Designated Market Areas: media markets) and White voters from a disjoint set. **"Black" and "White" therefore mean delivery in those DMA partitions**, not observed race; this report writes *Black (DMA-inferred)*. Gender is Meta's reported female/male breakdown.
- **Design.** The On and Off copies of an experiment ran at the same time, on separate audience partitions. The data contain Meta-reported impressions, unique reach (estimated accounts reached), spend and clicks, broken down by group.
- **Only `data_vrs_vs_novrs.csv` is analysed (72 deployments).** The HEC file repeats six of its rows. The budget-splitting file is a separate design whose aggregate rows are derived. Neither is used here.

## 2. Methods

### 2.1 The 36 matched comparisons

Each `exp_id` (18 in total: 6 creatives × 3 replicates) has four deployments: `g-vrs`, `g-novrs`, `r-vrs` and `r-novrs`. A **pair** is the On and Off deployment with the same `exp_id` and the same dimension label (g = gender, r = race). That gives 18 gender pairs plus 18 race pairs, or **36 pairs**. Each of the 72 deployments appears in exactly one pair; no observation is counted twice.

The script asserts several checks and stops if any fails:
- every ID has a complete four-row set, with no duplicates;
- the members of each ID share identical start and end times, and every deployment lasted 24 h;
- race-report and gender-report impression totals agree.

Gender pairs use the gender-report totals (`*_g`) and race pairs use the race-report totals (`*_r`). The two reach totals differ in 5 of 72 rows, by at most 2 accounts.

### 2.2 Measures

| Measure | Definition (per deployment) |
|---|---|
| Reported variance | ½ · (\|s₁ − e₁\| + \|s₂ − e₂\|), where s = a group's share of **total impressions** and e = the reference share. The dataset's `*-variance-eligible` columns (see 2.5). |
| Unique reach | Meta-reported accounts reached by the ad (dimension-matched total). |
| Cost per 1,000 reached (CPP) | spend ÷ unique reach × 1,000 (recomputed; the README's "per 100" label is wrong). |
| CPM | spend ÷ impressions × 1,000. |
| Frequency | impressions ÷ unique reach. Group frequency uses group impressions ÷ group reach. |
| Frequency ratio | Black ÷ White group frequency (race pairs); Female ÷ Male group frequency (gender pairs). |
| Reach-share analog | The variance formula applied to **reach** shares instead of impression shares, with the same reference. This is a comparison device only, because the reference is defined for impressions. |

Pair-level change is **On − Off** in percentage points (pp) for variance and shares. For counts and costs it is the **% change, (On ÷ Off − 1) × 100**.

### 2.3 Statistics

- Pairs are summarised by the mean and median change, and by counts of pairs that are lower, higher or unchanged.
- **Tests.** Within each dimension (n = 18 pairs), tests are the exact two-sided Wilcoxon signed-rank test and the exact sign test.
- **Pooled tests.** The gender and race pairs of one `exp_id` ran concurrently with the same creative, so they are not independent. They are averaged into **18 experiment-level values** before pooled testing and bootstrapping.
- **95% CIs.** Percentile bootstrap of the mean change (10,000 resamples, seed 480), resampling pairs within a dimension or experiment IDs when pooled. The CIs do not model clustering by creative. With only 6 creatives, the report also gives how many creatives move in the same direction.
- **Association.** Spearman ρ, with a two-sided permutation p-value (10,000 permutations, seed 480).
- p-values are descriptive. Many comparisons are reported and none is corrected for multiplicity.
- The exact tests agree with SciPy 1.16 to six decimals. All tables are byte-identical under Python 3.14 / pandas 3.0 and Python 3.13 / pandas 2.3.

### 2.4 Data-quality rules applied (from `DATA_QA.md`)

- `-1` cost sentinels are set to NaN. There is one in this file: a male CPC where clicks were zero. CPC is not used.
- CPP is cost per **1,000** people reached.
- `or_*` and `og_*` unit-cost fields are not used. Unknown-race and unknown-gender counts stay in the share denominators, which matches the published `*_frac` columns. They are at most 0.4% of race-report reach and 1.6% of gender-report reach.
- Ad IDs (stored in scientific notation) are never used as keys.
- The ZIP is read in place and verified against its SHA-256 before and after each run.

### 2.5 Addendum to `DATA_QA.md` issue 6: what "reported variance" is

The published `r-variance-eligible` and `g-variance-eligible` columns are reproduced **exactly** (maximum absolute error < 2 × 10⁻¹⁶) by the formula in 2.2. The inputs are impression shares and the reference shares that the paper states (Sec. 4.2.1): **Black 0.42 / White 0.58** and **female 0.55 / male 0.45**.

The paper estimated these references as the mean delivery ratio across its VRS-enabled ads. "Reported variance" is therefore the **researchers' calculation against their own estimate** of Meta's eligible ratio. It is not a figure exported by Meta, and Meta's actual reference remains unobservable.

One consequence matters for interpretation. Because the reference is estimated from VRS-on outcomes, VRS-on variance under this reference is close to zero on average by construction. Section 3.2 tests how much the result depends on the choice of reference.

---

## 3. Results

### 3.1 Computed here vs. reported by the original researchers

| Quantity | Reported by original researchers (arXiv v1) | Computed here | Status |
|---|---|---|---|
| Mean change in unique reach, 36 pairs | −9.82% (Sec. 4.2.3) | −9.98% (mean of per-pair % changes); −10.53% (change in mean reach) | close, not exact |
| Mean change in cost per 1,000 reached, 36 pairs | +12.02% (Sec. 4.2.3) | +12.05% (mean of per-pair % changes); +11.27% (change in mean CPP) | close, not exact |
| Race pairs with variance > 10% without VRS | 18 of 18 (Sec. 4.2.1) | 18 of 18 | reproduced |
| Race pairs with variance < 10% with VRS | 18 of 18 | 18 of 18 | reproduced |
| Race pairs with variance < 5% with VRS | 15 of 18 | 15 of 18 | reproduced |
| Gender pairs with variance < 5% without VRS | 15 of 18 | 15 of 18 | reproduced |
| Eligible-ratio estimate, Black / White / Male / Female | 0.42 / 0.58 / 0.45 / 0.55 (Sec. 4.2.1) | 0.417 / 0.582 / 0.452 / 0.542 (mean impression share over the 36 VRS-on ads) | Black, White and Male round to the reported values; Female rounds to 0.54 (0.55 = 1 − 0.45) |
| Hair-ad (HA) pairs where both groups lose reach ("leveling down") | HA1-g, HA2-g, HA2-r, HA3-g (Sec. 4.2.3) | HA1-g, HA2-g, HA2-r, HA3-g | reproduced |
| HA pairs where cost per 1,000 reached does not rise | HA1-r, HA1-g (Sec. 4.2.3) | Total CPP fell only in HA1-r (−3.8%). In HA1-g, total CPP rose (+12.3%) but male CPP fell (−11.8%). | matches only if group-level CPP is counted |

The paper does not say whether its percentages are means of per-pair changes or changes in means. The per-pair mean comes closest, but the remaining gaps (0.16 and 0.03 points) cannot be resolved from the published data.

### 3.2 Reported variance

| Pairs | Mean Off → On | Median Off → On | Mean change (95% CI) | Lower / higher with VRS | Wilcoxon p |
|---|---|---|---|---|---|
| Gender (n = 18) | 2.73% → 1.56% | 2.20% → 1.09% | −1.16 pp (−2.23 to −0.14) | 12 / 6 | 0.074 |
| Race (n = 18) | 14.60% → 2.92% | 13.97% → 3.00% | −11.69 pp (−13.54 to −9.93) | 18 / 0 | < 0.001 |

**Race.** Without VRS, race variance ranged from 10.1% to 22.4%. With VRS, it was at most 7.0%, and lower in every pair and every creative. The Black (DMA-inferred) share of impressions was 52.0–64.4% without VRS and 35.6–48.9% with VRS.

**Gender.** Gender variance was already small without VRS: all 18 pairs were under 10% and 15 were under 5%. VRS lowered it in 12 pairs and **raised** it in 6 (EA2-g, EA3-g, EB3-g, FA3-g, IA1-g, IA3-g). The evidence for an overall change is weak. The bootstrap CI for the mean change excludes zero, but neither the Wilcoxon test (p = 0.074) nor the sign test (p = 0.238) rejects a median change of zero.

**Cross-dimension check.** Every VRS-on copy was declared as housing, whatever its g/r label, so both attributes are affected in every pair. Race variance in the *gender* pairs fell from 16.38% to 2.14% (18/18 lower, p < 0.001). Gender variance in the *race* pairs fell from 3.16% to 1.19% (14/18 lower, p = 0.014). The g/r label marks which attribute the researchers evaluated, not a different treatment.

**Sensitivity to the reference distribution** (same deliveries, different e in the formula):

| Reference used for e | Race: Off → On | Race pairs lower with VRS | Race pairs < 10% with VRS | Gender: Off → On | Gender pairs lower |
|---|---|---|---|---|---|
| Paper's estimate (0.42 Black; 0.55 female) | 14.60% → 2.92% | 18/18 | 18/18 | 2.73% → 1.56% | 12/18 |
| Post-matching audience, paper App. D (0.43; 0.55) | 13.60% → 3.29% | 18/18 | 18/18 | 2.73% → 1.56% | 12/18 |
| Uploaded audience composition (0.50; 0.50) | 6.60% → 9.09% | 5/18 (p = 0.038, higher on average) | 10/18 | 5.30% → 4.04% | 11/18 |

VRS moved the Black (DMA-inferred) impression share from about 56.5% to about 40.9%, which is from above one half to below it. Measured against a 50:50 reference, the average gap therefore grows. Measured against references near 0.42–0.43, it shrinks sharply. The paper's match-rate estimate (App. D) supports a reference near 0.43. The 50:50 row shows the same deliveries against the composition of the uploaded lists.

### 3.3 Unique reach, impressions and cost

| Measure (36 pairs) | Mean Off → On | Mean % change (95% CI) | Median % change | Lower / higher / unchanged | Wilcoxon p (18 experiment-level units) |
|---|---|---|---|---|---|
| Unique reach (accounts) | 897.0 → 802.6 | −9.98% (−14.01 to −6.48) | −9.55% | 31 / 4 / 1 | < 0.001 |
| Impressions | 1,784.9 → 1,518.6 | −14.20% (−18.73 to −9.93) | −15.02% | 33 / 3 / 0 | < 0.001 |
| Impressions per account reached | 1.99 → 1.89 | −4.80% (−6.31 to −3.24) | −4.16% | 32 / 4 / 0 | < 0.001 |
| Cost per 1,000 reached (USD) | 22.45 → 24.98 | +12.05% (+7.21 to +18.08) | +8.80% | 4 / 31 / 1 | < 0.001 |
| Cost per 1,000 impressions (USD) | 11.35 → 13.27 | +18.07% (+11.87 to +25.29) | +16.39% | 1 / 35 / 0 | < 0.001 |
| Spend (USD) | 19.95 → 19.88 | −0.31% (−0.96 to +0.20) | 0.00% | 12 / 14 / 10 | 0.90 |

**By dimension:**
- Unique reach fell by a mean of 9.63% in gender pairs (CI −14.45 to −5.63; 16/18 lower) and 10.33% in race pairs (CI −14.39 to −6.28; 15/18 lower).
- CPP rose by 11.59% (gender) and 12.50% (race).

**Exceptions.** Reach rose with VRS in four pairs (EA3-g, EB1-r, HA1-r, IA1-g), and those same four pairs had lower CPP. IA1-r was exactly unchanged on both measures.

**By creative.** Reach was lower on average for 6 of 6 creatives in both dimensions, and CPP higher for 6 of 6. The largest reach losses were for the hair ad (gender −18.6%, race −14.6%) and the golf ad (−17.2%, −18.0%). The smallest were insurance in gender pairs (−2.8%) and education CSU in race pairs (−4.8%).

**Spend.** Spend was essentially equal across conditions. Two VRS-on ads underspent noticeably (FA2-g $18.17, GA2-g $18.93), so part of their lower reach reflects lower spend; CPP adjusts for this.

**In short:** VRS-on copies bought fewer impressions at a higher price per impression and showed the ad slightly less often per account. Together these produced lower reach for about the same budget.

### 3.4 Is lower variance accompanied by reduced reach?

**Across pairs:**
- Variance fell in 30 of 36 pairs, and reach also fell in 27 of those 30.
- Reach also fell in 4 of the 6 pairs where variance did not fall.
- Reach reductions therefore accompany VRS broadly, not only where variance changed.

**Within dimensions:**
- **Race:** variance fell in 18/18 pairs and reach fell in 15 of them. The *size* of the variance reduction is unrelated to the size of the reach change (Spearman ρ = −0.06, permutation p = 0.81).
- **Gender:** all 12 pairs with lower variance also had lower reach. The correlation is strong: larger reductions in gender variance went with larger reach losses (ρ = +0.72, p = 0.001). The hair and golf creatives had both the largest mean variance reductions (−2.6 and −3.2 pp) and the largest reach losses. With six creatives, this cannot be separated from creative-specific effects.

**Which groups lost reach:**

| Group | Mean reach Off → On | Mean % change | Pairs lower | Wilcoxon p | Mean % change in group CPP |
|---|---|---|---|---|---|
| Black (DMA-inferred), race pairs | 487.8 → 340.6 | −29.7% | 18/18 | < 0.001 | +2.4% |
| White (DMA-inferred), race pairs | 422.9 → 473.7 | +12.3% | 3/18 (14 higher, 1 unchanged) | 0.001 | +26.5% |
| Female, gender pairs | 491.8 → 425.8 | −12.5% | 17/18 | < 0.001 | +14.4% |
| Male, gender pairs | 385.7 → 358.8 | −6.0% | 14/18 | 0.018 | +9.6% |

**Leveling down.** This report operationalises the paper's term as a pair in which variance fell *and* both groups lost unique reach.
- **Race:** without VRS, the Black (DMA-inferred) group was above its reference share in all 18 pairs. With VRS it lost reach while the White (DMA-inferred) group did not lose reach in 15 pairs (14 gained, 1 unchanged). Both groups lost reach in 3 pairs (EA3-r, GA3-r, HA2-r), all with lower variance, so 3/18 meet the definition.
- **Gender:** both groups lost reach in 14/18 pairs, and in 11 of these variance also fell (EA1-g, EB1-g, EB2-g, FA1-g, FA2-g, GA1-g, GA2-g, GA3-g, HA1-g, HA2-g, HA3-g).
- **Total: 14 of 36 pairs.** For the hair ad, the four pairs match the paper's list (Section 3.1).

### 3.5 Impressions versus unique reach

| Deployments (n = 18 each) | Group-1 share of impressions | Group-1 share of unique reach | Gap (pp) | Group-1 / group-2 frequency | Mean frequency ratio |
|---|---|---|---|---|---|
| Race, VRS off (group 1 = Black, DMA-inferred) | 56.5% | 53.4% | +3.2 | 2.10 / 1.85 | 1.14 |
| Race, VRS on | 40.9% | 41.8% | −0.9 | 1.87 / 1.94 | 0.96 |
| Gender, VRS off (group 1 = Female) | 54.8% | 55.7% | −1.0 | 1.96 / 2.04 | 0.96 |
| Gender, VRS on | 53.8% | 54.0% | −0.2 | 1.87 / 1.88 | 0.99 |

**Race pairs** (all three changes p < 0.001):
- With VRS, the Black (DMA-inferred) share of impressions fell by 15.65 pp, and its share of unique reach fell by 11.58 pp (18/18 pairs each).
- Without VRS, reached Black (DMA-inferred) accounts saw the ad more often than White (DMA-inferred) accounts in all 18 pairs (frequency ratio > 1). With VRS, the ratio was below 1 in 13/18 pairs; it fell by 0.18 on average (18/18).
- Impression-based variance fell by 11.69 pp; the same formula on reach shares fell by 9.32 pp. Roughly **one-fifth of the measured variance reduction reflects how often reached accounts saw the ad, not which accounts were reached.** This is approximate, because the reference is defined for impressions.

**Gender pairs:** the pattern runs the other way, and it is small.
- The female share of unique reach fell by more (−1.78 pp; 15/18; p = 0.002) than the female share of impressions (−1.02 pp; 13/18; p = 0.14).
- The reach-share analog barely moved (−0.59 pp; 9/18 lower; p = 0.26).

**Why this matters.** The quantity that VRS and the reported variance track is a share of **impressions**. A group's share of impressions can differ from its share of distinct people reached, because frequency differs between groups. In these data, the two measures diverge most in the race comparisons without VRS.

---

## 4. Figures

All figures are in `figures/` as 300-dpi PNG and vector PDF. Orange squares are VRS off and blue circles are VRS on. Blue dots in the change charts are pair-level On-vs-Off changes.

**Figure 1 — `fig1_variance_paired`.** Reported variance for each pair, VRS off (left) and on (right), with lines joining the two copies. Panel A shows the 18 gender pairs; dark lines mark the 6 pairs where variance rose. Panel B shows the 18 race pairs. Horizontal lines mark the 5% and 10% thresholds used in the paper. Medians are labelled. *Reading:* race variance drops in every pair from 10–22% to under 7%. Gender variance starts low and moves in both directions.

**Figure 2 — `fig2_reach_cost_by_creative`.** Percent change with VRS on, by creative. Columns are unique reach (left) and cost per 1,000 reached (right); rows are gender pairs (A, B) and race pairs (C, D). Each dot is one replicate and the black tick is the creative mean. *Reading:* nearly all dots lie left of zero for reach and right of zero for cost. Effects are largest for the hair and golf creatives, and the few exceptions are visible as individual dots.

**Figure 3 — `fig3_variance_vs_reach`.** Change in reported variance (x, in pp) against % change in unique reach (y), one dot per pair. Panel subtitles give quadrant counts and Spearman ρ. *Reading:* the lower-left quadrant (variance down, reach down) holds most pairs. In gender pairs, bigger variance reductions sit lower (ρ = +0.72). In race pairs the scatter is flat (ρ = −0.06). The x-axis scales differ between panels.

**Figure 4 — `fig4_impressions_vs_reach_shares`.** Each deployment's group-1 share of unique reach (x) against its share of impressions (y). Panel A shows the Black (DMA-inferred) share in race deployments; panel B shows the female share in gender deployments. The diagonal marks equal shares, and the horizontal line marks the reference share. *Reading:* points above the diagonal give that group more impressions per account reached. In panel A, VRS-off points sit above the diagonal and above the reference. VRS-on points cluster around the reference and close to the diagonal. Panel B shows little separation between conditions.

**Figure 5 — `fig5_group_reach_changes`.** Percent change in each group's unique reach, one dot per pair. Panel A plots White (DMA-inferred) against Black (DMA-inferred) in race pairs; panel B plots male against female in gender pairs. The shaded lower-left quadrant contains pairs where both groups lost reach, and hair-ad pairs are labelled. *Reading:* in race pairs, VRS mostly shifts reach from one group to the other (upper-left quadrant). In gender pairs, both groups usually lose reach (shaded quadrant).

## 5. Limitations

1. **Small, specific sample.**
   - The data cover 18 pairs per dimension, from 6 creatives × 3 replicates.
   - All campaigns were short ($20, 24 h), ran in one U.S. state (North Carolina voter lists) and were deployed in Nov–Dec 2024.
   - Results describe Meta's implementation at that time and may not hold for larger, longer or real housing campaigns.
2. **Dependence among observations.**
   - Replicates share creatives, and the g/r pairs of one ID ran concurrently.
   - The pooled analyses average the g/r pairs, but no analysis models creative-level clustering.
   - The CIs are therefore likely too narrow for claims about "ads in general".
3. **On and Off copies ran on different audience partitions.** Each paired difference includes any difference between those partitions and in the competition each one faced, as the paper notes.
4. **Race is inferred from geography.**
   - The researchers inferred race from DMA partitions; they omitted the "flip" check, which swaps the DMA sets, and cited prior work instead (App. B).
   - Black/White differences are therefore confounded with regional differences between DMA sets, such as ad prices and competition. This may explain part of the group-level cost differences.
5. **The reference distribution is estimated, and partly circular.**
   - "Reported variance" uses the researchers' estimate of Meta's eligible ratio, derived from VRS-on outcomes themselves.
   - Meta's actual reference and its BISG-based race measurement are not observable.
   - Conclusions about variance depend on the reference chosen (Section 3.2).
6. **The reach-share analog is approximate.** It reuses a reference defined for impressions.
7. **Platform-reported metrics.** Reach is Meta's estimate of unique accounts, not verified people. Small groups such as unknown gender (≤ 1.6% of reach) are excluded from group comparisons.
8. **Reproduction gaps.** The paper's −9.82% and +12.02% are matched only to within 0.16 and 0.03 points. Its statement about HA1-g cost matches only if group-level cost is counted.
9. **Multiple comparisons.** Many p-values are reported without correction. They describe the data; they do not confirm hypotheses.
10. **Files not analysed.** `data_heccomp.csv` (housing vs. credit vs. job declarations) and `data_budget_split.csv` (the paper's alternative) are not analysed here.

## 6. Interpretation boundaries

- A difference in delivery between groups is a measured **disparity**. These data cannot show intent, nor the mechanism behind it: auction competition, regional price differences, match rates and user behaviour are all candidate explanations. Disparity alone does not establish unlawful discrimination.
- The ads are deliberately mislabelled probes, designed to switch VRS on. They show how VRS behaves on these ads, not how real housing listings were delivered.
- These data do not settle which measure is the normatively relevant one: impressions or unique reach, and which reference distribution. Section 3.2 and Section 3.5 show that the answer changes the size, and for race against a 50:50 reference even the direction, of the measured "variance reduction".

## 7. Reproduce

Run from the project folder (`DS480_Paper2/`):

```bash
python -m pip install -r meta_vrs/requirements.txt
```

```bash
python meta_vrs/qa_meta_vrs.py
```

```bash
python meta_vrs/analyze_vrs.py
```

The ZIP is expected at `meta_vrs/data_raw/` and is never modified. A different path can be passed as the first argument.

| Output | Content |
|---|---|
| `output/pairs_36.csv` | One row per matched pair: Off/On values, changes, group reach, reach pattern |
| `output/deployments_72.csv` | One row per deployment with derived shares, frequencies, costs and alternative-reference variances |
| `output/summary_paired.csv` | Section 3.2–3.3 summaries with CIs and tests |
| `output/summary_by_creative.csv` | Creative-level means |
| `output/tradeoff_variance_vs_reach.csv` | Section 3.4 quadrant counts and Spearman tests |
| `output/group_reach_changes.csv`, `output/reach_patterns_leveling_down.csv` | Section 3.4 group-level tables |
| `output/impressions_vs_reach_levels.csv`, `output/impressions_vs_reach_paired.csv` | Section 3.5 |
| `output/variance_benchmark_sensitivity.csv`, `output/variance_cross_dimension.csv` | Section 3.2 robustness checks |
| `output/paper_vs_independent.csv` | Section 3.1 |
| `output/key_results.txt` | Plain-text log of every number above |
