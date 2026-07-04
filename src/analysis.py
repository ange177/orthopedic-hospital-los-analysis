"""
Orthopaedic Hospital Length of Stay Analysis

Identifies what drives Length of Stay (LOS) - specialty, comorbidities,
time to surgery, number of surgeries, age, sex, diagnosis (ICD code), and
discharge/transfer type - to support bed-capacity and discharge planning.

Run from the src/ folder:
    python analysis.py
Charts land in ../outputs/, and a plain-text findings summary is printed
to the console (redirect it to a file if you want a copy).
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import ttest_ind, pearsonr
import statsmodels.api as sm

DATA_DIR = "../data"
OUTPUT_DIR = "../outputs"

sns.set_style("whitegrid")


# ---------------------------------------------------------------------------
# 1. Load and clean
# ---------------------------------------------------------------------------

def parse_dates(series):
    """
    The date columns in this dataset mix two formats: 'DD-MM-YYYY HH:MM'
    and a second style like '2/4/19 0:00'. If you hand the whole column to
    pd.to_datetime() in one call, pandas infers a single format from the
    majority of rows and silently turns every non-matching row into NaT -
    no error, no warning you'd notice. An earlier pass at this analysis
    did exactly that: about 40% of admission/discharge dates were dropped
    without anyone realising, which roughly halved the specialty counts
    and quietly invalidated the comorbidity t-test. Parsing row by row
    avoids that.
    """
    return series.apply(
        lambda x: pd.to_datetime(x, dayfirst=True, errors="coerce") if pd.notna(x) else pd.NaT
    )


def load_data():
    hospital = pd.read_csv(f"{DATA_DIR}/hospital_data.csv", low_memory=False)
    icd_lookup = pd.read_csv(
        f"{DATA_DIR}/icd_codes.csv", header=None,
        names=["cat_code", "sub", "full_code", "desc_long", "desc_short", "category"],
    )

    for col in ["ADMISSION.DATE", "DISCHARGE.DATE", "FIRST.SURGERY.DATE"]:
        hospital[col] = parse_dates(hospital[col])

    hospital["LOS"] = (hospital["DISCHARGE.DATE"] - hospital["ADMISSION.DATE"]).dt.days
    hospital["TIME_TO_SURGERY"] = (hospital["FIRST.SURGERY.DATE"] - hospital["ADMISSION.DATE"]).dt.days

    # a couple of rows have first-surgery timestamps a day before admission
    # (probably a scheduling/admin timestamp quirk) - drop those as invalid
    hospital.loc[hospital["TIME_TO_SURGERY"] < 0, "TIME_TO_SURGERY"] = np.nan

    # ICD codes in hospital_data have a dot (e.g. M17.1); the lookup table
    # doesn't. Matching on the full code barely works (~22% match) because
    # the lookup includes 7th-character extensions this dataset doesn't
    # use, so we map on the 3-character chapter prefix instead (M17, S72,
    # T84, ...) which gets a ~92% match and still gives a clinically
    # meaningful category.
    icd_lookup["prefix"] = icd_lookup["full_code"].str[:3]
    prefix_to_category = icd_lookup.groupby("prefix")["category"].agg(lambda x: x.value_counts().index[0])
    hospital["ICD_PREFIX"] = hospital["ICD"].str.split(".").str[0]
    hospital["ICD_CATEGORY"] = hospital["ICD_PREFIX"].map(prefix_to_category)

    hospital["TRANSFERRED"] = ~hospital["TRANSFER.PLACE"].str.strip().isin(["HOME", ""])
    hospital["SEX"] = hospital["SEX"].str.strip()

    return hospital


# ---------------------------------------------------------------------------
# 2. Descriptive statistics by specialty
# ---------------------------------------------------------------------------

def specialty_summary(df):
    summary = df.dropna(subset=["LOS"]).groupby("SERVICE")["LOS"].agg(
        ["count", "mean", "std", "median", "max"]
    ).sort_values("mean", ascending=False)
    return summary


# ---------------------------------------------------------------------------
# 3. Comorbidities
# ---------------------------------------------------------------------------

def comorbidity_analysis(df):
    with_com = df.loc[df["COMORBIDITIES"] == 1, "LOS"].dropna()
    without_com = df.loc[df["COMORBIDITIES"] == 0, "LOS"].dropna()

    t_stat, p_value = ttest_ind(with_com, without_com, equal_var=False)

    return {
        "mean_with": with_com.mean(),
        "mean_without": without_com.mean(),
        "n_with": len(with_com),
        "n_without": len(without_com),
        "t_stat": t_stat,
        "p_value": p_value,
    }


# ---------------------------------------------------------------------------
# 4. Correlations
# ---------------------------------------------------------------------------

def correlation_analysis(df):
    results = {}
    pairs = {
        "Time to surgery": "TIME_TO_SURGERY",
        "Number of surgeries": "NUMBER.OF.SURGERIES",
        "Age": "AGE",
    }
    for label, col in pairs.items():
        valid = df.dropna(subset=[col, "LOS"])
        r, p = pearsonr(valid[col], valid["LOS"])
        results[label] = {"r": r, "p": p, "n": len(valid)}
    return results


# ---------------------------------------------------------------------------
# 5. Regression - isolates each factor's independent effect on LOS
# ---------------------------------------------------------------------------

def regression_analysis(df):
    model_df = df.dropna(subset=[
        "LOS", "TIME_TO_SURGERY", "COMORBIDITIES", "NUMBER.OF.SURGERIES", "AGE", "SEX"
    ]).copy()
    model_df["SEX_M"] = (model_df["SEX"] == "M").astype(int)

    predictors = ["TIME_TO_SURGERY", "COMORBIDITIES", "NUMBER.OF.SURGERIES", "AGE", "SEX_M"]
    X = sm.add_constant(model_df[predictors])
    y = model_df["LOS"]

    model = sm.OLS(y, X).fit()
    return model, len(model_df)


# ---------------------------------------------------------------------------
# 6. Diagnosis (ICD) categories
# ---------------------------------------------------------------------------

def icd_category_analysis(df, min_cases=200):
    valid = df.dropna(subset=["LOS", "ICD_CATEGORY"])
    summary = valid.groupby("ICD_CATEGORY")["LOS"].agg(["mean", "count"])
    summary = summary[summary["count"] >= min_cases].sort_values("mean", ascending=False)
    return summary


# ---------------------------------------------------------------------------
# 7. Discharge outcome / transfer analysis
# ---------------------------------------------------------------------------

def discharge_analysis(df):
    transfer_summary = df.dropna(subset=["LOS"]).groupby("TRANSFERRED")["LOS"].agg(["mean", "count"])

    reason_summary = df.dropna(subset=["LOS"]).groupby("REASON.FOR.DISCHARGE")["LOS"].agg(
        ["mean", "count"]
    ).sort_values("count", ascending=False)

    return transfer_summary, reason_summary


# ---------------------------------------------------------------------------
# 8. Visualisations
# ---------------------------------------------------------------------------

def make_visualisations(df, specialty_stats, icd_stats, regression_model):
    # Chart 1 - average LOS by specialty
    plt.figure(figsize=(12, 7))
    top_specialties = specialty_stats.sort_values("mean")
    sns.barplot(x=top_specialties["mean"], y=top_specialties.index, color="#2E75B6")
    plt.title("Average Length of Stay by Specialty")
    plt.xlabel("Average LOS (days)")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/chart1_los_by_specialty.png", dpi=200)
    plt.close()

    # Chart 2 - comorbidities box plot
    plt.figure(figsize=(7, 6))
    sns.boxplot(data=df, x="COMORBIDITIES", y="LOS", showfliers=False)
    plt.title("LOS by Comorbidity Status (outliers hidden for readability)")
    plt.xlabel("Comorbidities (0 = No, 1 = Yes)")
    plt.ylabel("LOS (days)")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/chart2_comorbidities_boxplot.png", dpi=200)
    plt.close()

    # Chart 3 - time to surgery scatter
    plt.figure(figsize=(8, 6))
    sample = df.dropna(subset=["TIME_TO_SURGERY", "LOS"]).sample(
        n=min(5000, df["TIME_TO_SURGERY"].notna().sum()), random_state=1
    )
    sns.scatterplot(data=sample, x="TIME_TO_SURGERY", y="LOS", alpha=0.3)
    plt.title("Time Until First Surgery vs Length of Stay")
    plt.xlabel("Time to first surgery (days)")
    plt.ylabel("LOS (days)")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/chart3_time_to_surgery_scatter.png", dpi=200)
    plt.close()

    # Chart 4 - violin plot
    plt.figure(figsize=(7, 6))
    capped = df.copy()
    capped["LOS_capped"] = capped["LOS"].clip(upper=60)  # for readability only
    sns.violinplot(data=capped, x="COMORBIDITIES", y="LOS_capped")
    plt.title("LOS Distribution by Comorbidity Status (capped at 60 days for display)")
    plt.xlabel("Comorbidities (0 = No, 1 = Yes)")
    plt.ylabel("LOS (days)")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/chart4_comorbidities_violin.png", dpi=200)
    plt.close()

    # Chart 5 - regression coefficients
    plt.figure(figsize=(8, 5))
    coefs = regression_model.params.drop("const").sort_values()
    colors = ["#C0504D" if v < 0 else "#4472C4" for v in coefs]
    plt.barh(coefs.index, coefs.values, color=colors)
    plt.title("Regression Coefficients - Effect on LOS (days)")
    plt.xlabel("Change in LOS (days) per unit increase")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/chart5_regression_coefficients.png", dpi=200)
    plt.close()

    # Chart 6 - top diagnosis categories by LOS
    plt.figure(figsize=(10, 7))
    top10 = icd_stats.head(10).sort_values("mean")
    sns.barplot(x=top10["mean"], y=top10.index, color="#A9D08E")
    plt.title("Top 10 Diagnosis Categories by Average LOS (min. 200 cases)")
    plt.xlabel("Average LOS (days)")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/chart6_top_diagnoses_by_los.png", dpi=200)
    plt.close()

    # Chart 7 - correlation heatmap
    plt.figure(figsize=(6, 5))
    corr_cols = ["LOS", "TIME_TO_SURGERY", "NUMBER.OF.SURGERIES", "AGE"]
    sns.heatmap(df[corr_cols].corr(), annot=True, cmap="coolwarm", vmin=-1, vmax=1)
    plt.title("Correlation Matrix")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/chart7_correlation_heatmap.png", dpi=200)
    plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    df = load_data()
    print(f"Loaded {len(df):,} records | {df['LOS'].notna().sum():,} with a valid LOS\n")

    specialty_stats = specialty_summary(df)
    print("=== LOS by specialty (top 10) ===")
    print(specialty_stats.head(10).round(1), "\n")

    com = comorbidity_analysis(df)
    print("=== Comorbidities ===")
    print(f"With comorbidities: {com['mean_with']:.2f} days (n={com['n_with']:,})")
    print(f"Without comorbidities: {com['mean_without']:.2f} days (n={com['n_without']:,})")
    print(f"t-test: t={com['t_stat']:.2f}, p={com['p_value']:.4f}\n")

    corr = correlation_analysis(df)
    print("=== Correlations with LOS ===")
    for label, stats in corr.items():
        print(f"{label}: r={stats['r']:.3f}, p={stats['p']:.4g}, n={stats['n']:,}")
    print()

    model, n = regression_analysis(df)
    print("=== Regression: LOS ~ time to surgery + comorbidities + surgeries + age + sex ===")
    print(f"n = {n:,}, R-squared = {model.rsquared:.3f}")
    print(model.params.round(3), "\n")

    icd_stats = icd_category_analysis(df)
    print("=== Top diagnosis categories by average LOS (min 200 cases) ===")
    print(icd_stats.head(10).round(1), "\n")

    transfer_summary, reason_summary = discharge_analysis(df)
    print("=== LOS by transfer status ===")
    print(transfer_summary.round(1), "\n")
    print("=== LOS by discharge reason (top 6 by volume) ===")
    print(reason_summary.head(6).round(1), "\n")

    make_visualisations(df, specialty_stats, icd_stats, model)
    print(f"7 charts saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
