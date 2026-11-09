# ds480-meta-housing-vrs

DS480 Paper 2 data analysis of Meta's Variance Reduction System (VRS), based on the public dataset from [Imana et al. (2025)](https://arxiv.org/abs/2506.16560).

The script compares **36 matched VRS-on/off experiments** (18 race and 18 gender pairs), focusing on delivery variance, unique reach, and advertising cost.

## Files

- `meta_vrs/analyze_vrs.py` — analysis and figure generation
- `meta_vrs/requirements.txt` — Python dependencies

## How to run

1. Download `vrs_ad_delivery_data-2025-05-23.zip` from the [public dataset](https://ant.isi.edu/datasets/addelivery-vrs/).
2. Save the ZIP at `meta_vrs/data_raw/vrs_ad_delivery_data-2025-05-23.zip`.
3. From the repository folder, run:

```bash
python -m pip install -r meta_vrs/requirements.txt
python meta_vrs/analyze_vrs.py
```

Results are saved in `meta_vrs/output/` (tables and summary) and `meta_vrs/figures/` (charts).

The raw dataset is not included. Race estimates are based on geographic inference, and the experimental ads were not actual housing listings.
