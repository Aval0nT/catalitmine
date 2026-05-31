"""
feature_engineering.py — Phase 5: Feature matrix construction

Converts catalyst system records from DB into a numeric feature matrix
for ML training. Handles:
  - One-hot encoding of active_metal, promoter, support
  - Elemental property vectors (atomic number, electronegativity, etc.)
  - Reaction condition features (T, P, GHSV, H2/CO2 ratio)
  - Optional: Materials Project structural features

Input:  db/catalysis.db
Output: data/05_normalized/feature_matrix_<date>.csv
        data/05_normalized/feature_matrix_<date>.pkl
"""
# TODO: implement in Phase 5
