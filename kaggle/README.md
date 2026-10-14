# Kaggle companion package

`Real_Madrid_VAR_null_goals_Kaggle.pdf` supplements the article draft in `../article/` (unchanged). It contains the revised abstract, explicit inclusion rules, a data dictionary, reproducible code and sensitivity analyses.

| File | Purpose |
|---|---|
| `reproduce.py` | Recomputes the headline estimates and every sensitivity table from `data/processed/` (about 1 minute, seed 2026) |
| `make_figures.py` | Figures used in the PDF |
| `data_dictionary.py`, `data_dictionary.csv` | Column-level documentation; the script fails if a column is undocumented |
| `build_pdf.py` | Builds the PDF from the tables in `outputs/` |
| `outputs/` | CSV/JSON results, figures, and the manual-audit key and blank form for comparison clubs |
| `requirements.txt` | Package versions used |

```
pip install -r kaggle/requirements.txt
python kaggle/reproduce.py
python kaggle/make_figures.py
python kaggle/data_dictionary.py
python kaggle/build_pdf.py
```

The manual audit of comparison clubs described in section 6 of the PDF has not been performed; `outputs/manual_audit_form.csv` is blank.
