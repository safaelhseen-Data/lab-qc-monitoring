"""
Synthetic QC data generator for a diesel fuel testing lab.
Produces:
  - lab_qc_data.csv : ~90 days of daily test results (3 samples/day)
  - specs.csv       : specification limits per test
Built-in "problems" to discover in your analysis:
  1. Flash point instrument drift starting around day 60 (needs recalibration)
  2. A handful of random outliers (typos / bad measurements)
  3. A few missing values
  4. Some genuinely out-of-spec samples
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

START = pd.Timestamp("2026-07-01")
DAYS = 90
SAMPLES_PER_DAY = 3

ANALYSTS = ["Analyst_A", "Analyst_B", "Analyst_C"]
INSTRUMENTS = {
    "density": "DMA-4500",
    "viscosity": "SVM-3001",
    "flash_point": "FP-Pensky-01",
    "water_ppm": "KF-Coulometer-02",
    "sulfur_ppm": "XRF-S-05",
}

# Process means and standard deviations (in-control behavior)
PARAMS = {
    "density": (832.0, 2.5),      # kg/m3 @15C
    "viscosity": (3.20, 0.15),    # cSt @40C
    "flash_point": (68.0, 1.8),   # C
    "water_ppm": (95.0, 22.0),    # mg/kg
    "sulfur_ppm": (7.0, 1.2),     # mg/kg
}

rows = []
sid = 1
for d in range(DAYS):
    date = START + pd.Timedelta(days=d)
    if date.dayofweek == 4:  # skip Fridays (weekend in KSA)
        continue
    for s in range(SAMPLES_PER_DAY):
        row = {
            "sample_id": f"DSL-{sid:04d}",
            "date": date.date().isoformat(),
            "product": "Diesel",
            "batch": f"B{(d // 5) + 1:03d}",
            "analyst": rng.choice(ANALYSTS),
        }
        for test, (mu, sd) in PARAMS.items():
            value = rng.normal(mu, sd)
            # Problem 1: flash point drifts upward-downward slowly after day 60
            if test == "flash_point" and d >= 60:
                value -= (d - 60) * 0.18
            # Batch-to-batch variation for density
            if test == "density":
                value += ((d // 5) % 4 - 1.5) * 0.4
            row[test] = value
        rows.append(row)
        sid += 1

df = pd.DataFrame(rows)

# Problem 2: random outliers (e.g. decimal typo or contaminated sample)
outlier_idx = rng.choice(df.index, size=5, replace=False)
df.loc[outlier_idx[0], "viscosity"] *= 2.1
df.loc[outlier_idx[1], "water_ppm"] += 380
df.loc[outlier_idx[2], "sulfur_ppm"] += 14
df.loc[outlier_idx[3], "density"] -= 18
df.loc[outlier_idx[4], "flash_point"] -= 12

# Problem 3: missing values
for col in ["viscosity", "water_ppm", "sulfur_ppm", "density"]:
    idx = rng.choice(df.index, size=3, replace=False)
    df.loc[idx, col] = np.nan

# Rounding to realistic instrument resolution
df["density"] = df["density"].round(1)
df["viscosity"] = df["viscosity"].round(3)
df["flash_point"] = df["flash_point"].round(1)
df["water_ppm"] = df["water_ppm"].round(0)
df["sulfur_ppm"] = df["sulfur_ppm"].round(1)

# Specification limits (EN 590-like diesel)
specs = pd.DataFrame(
    [
        ["density", "kg/m3 @15C", 820.0, 845.0, "ASTM D4052"],
        ["viscosity", "cSt @40C", 2.0, 4.5, "ASTM D445"],
        ["flash_point", "C", 55.0, None, "ASTM D93"],
        ["water_ppm", "mg/kg", None, 200.0, "ASTM D6304"],
        ["sulfur_ppm", "mg/kg", None, 10.0, "ASTM D5453"],
    ],
    columns=["test", "unit", "min_limit", "max_limit", "method"],
)

# Problem 4 check: status flag per row based on specs
def status(r):
    for _, sp in specs.iterrows():
        v = r[sp["test"]]
        if pd.isna(v):
            continue
        if pd.notna(sp["min_limit"]) and v < sp["min_limit"]:
            return "OUT_OF_SPEC"
        if pd.notna(sp["max_limit"]) and v > sp["max_limit"]:
            return "OUT_OF_SPEC"
    return "OK"

df["status"] = df.apply(status, axis=1)

df.to_csv("lab_qc_data.csv", index=False)
specs.to_csv("specs.csv", index=False)

print(f"Rows: {len(df)}")
print(f"Out of spec: {(df['status'] == 'OUT_OF_SPEC').sum()}")
print("Missing values per column:")
print(df.isna().sum()[df.isna().sum() > 0].to_string())
print(df.head(6).to_string(index=False))
