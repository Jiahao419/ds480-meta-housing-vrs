# Meta VRS Ad Delivery Analysis

DS480 Paper 2 analysis of Meta's Variance Reduction System (VRS), using the [public dataset from Imana et al. (2025)](https://ant.isi.edu/datasets/addelivery-vrs/).

## Uploaded files

- `meta_vrs/analyze_vrs.py` — Python analysis script
- `meta_vrs/requirements.txt` — required Python packages
- `DATA_QA.md` — data checks and cleaning notes
- `meta_vrs.zip` — uploaded project archive

## Run

The script uses `vrs_ad_delivery_data-2025-05-23.zip` from the public dataset. Place it in `meta_vrs/data_raw/` before running:

```bash
python -m pip install -r meta_vrs/requirements.txt
python meta_vrs/analyze_vrs.py
```

The script generates result tables and figures locally. They are not uploaded as separate folders in this repository.
