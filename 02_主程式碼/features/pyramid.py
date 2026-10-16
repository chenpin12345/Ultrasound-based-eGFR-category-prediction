import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# ===============================
# Global plotting style (SCI-like)
# ===============================
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 12,
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "legend.fontsize": 11,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False
})

def plot_age_gender_pyramids(
    csv_path,
    show_dataset_level=True,
    show_patient_level=True
):
    import pandas as pd
    import matplotlib.pyplot as plt

    # ===============================
    # Global plotting style (SCI-like)
    # ===============================
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 12,
        "axes.labelsize": 13,
        "axes.titlesize": 14,
        "legend.fontsize": 11,
        "axes.spines.top": False,
        "axes.spines.right": False
    })

    # -------------------------------------------------
    # Load data
    # -------------------------------------------------
    df = pd.read_csv(csv_path)
    df["age"] = df["age"].astype(int)
    df["gender"] = df["gender"].astype(str)
    df["person_id"] = df["image_name"].apply(lambda x: x.split("_")[0])
    df_unique = df.drop_duplicates(subset="person_id")

    # -------------------------------------------------
    # Decide number of subplots
    # -------------------------------------------------
    plots = []
    if show_dataset_level:
        plots.append("dataset")
    if show_patient_level:
        plots.append("patient")

    if len(plots) == 0:
        raise ValueError("At least one of show_dataset_level or show_patient_level must be True.")

    fig, axes = plt.subplots(
        1, len(plots),
        figsize=(7 * len(plots), 6),
        sharey=True
    )

    if len(plots) == 1:
        axes = [axes]

    panel_idx = 0

    # =================================================
    # (A) Dataset-level pyramid
    # =================================================
    if show_dataset_level:
        ax = axes[panel_idx]
        panel_idx += 1

        age_gender_img = df.groupby(["age", "gender"]).size().unstack(fill_value=0)
        male = -age_gender_img.get("男", 0)
        female = age_gender_img.get("女", 0)

        ax.barh(age_gender_img.index, male, color="gray", label="Male")
        ax.barh(age_gender_img.index, female, color="lightgray", label="Female")

        ax.set_title("(a) Dataset-level Age–Gender Distribution")
        ax.set_xlabel("Number of Images")
        ax.set_ylabel("Age (years)")
        ax.legend(frameon=False)
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        formatter = FuncFormatter(lambda x, pos: f"{abs(int(x))}")
        ax.xaxis.set_major_formatter(formatter)

    # =================================================
    # (B) Patient-level pyramid
    # =================================================
    if show_patient_level:
        ax = axes[panel_idx]

        age_gender_pat = df_unique.groupby(["age", "gender"]).size().unstack(fill_value=0)
        male = -age_gender_pat.get("男", 0)
        female = age_gender_pat.get("女", 0)

        ax.barh(age_gender_pat.index, male, color="gray", label="Male")
        ax.barh(age_gender_pat.index, female, color="lightgray", label="Female")

        title_prefix = "(b)" if show_dataset_level else ""
        ax.set_title(f"{title_prefix} Patient-level Age–Gender Distribution")
        ax.set_xlabel("Number of Patients")
        ax.legend(frameon=False)
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        formatter = FuncFormatter(lambda x, pos: f"{abs(int(x))}")
        ax.xaxis.set_major_formatter(formatter)

    fig.supylabel("Age (years)")
    plt.tight_layout()
    plt.savefig("age_gender_distribution.png", dpi=300, bbox_inches="tight")
    plt.show()

if __name__ == "__main__":
    try:
        from ._paths import reference
    except ImportError:
        from _paths import reference
    csv_path = reference('metadata_old.csv')
    plot_age_gender_pyramids(
        csv_path,
        show_dataset_level=False,
        show_patient_level=True
    )

    # --------------------------
    # Terminal output: mean & std
    # --------------------------
    df = pd.read_csv(csv_path)
    df["age"] = df["age"].astype(int)
    df["person_id"] = df["image_name"].apply(lambda x: x.split("_")[0])
    df_unique = df.drop_duplicates(subset="person_id")

    mean_age = df_unique["age"].mean()
    std_age = df_unique["age"].std()
    print("===== Patient-level Age Statistics =====")
    print(f"Mean age: {mean_age:.2f} years")
    print(f"Standard deviation: {std_age:.2f} years")
    print("=======================================")

    # 計算總人數
    total_patients = len(df_unique)

    # 計算男女數量
    male_count = (df_unique["gender"] == "男").sum()
    female_count = (df_unique["gender"] == "女").sum()

    # 計算比例
    male_pct = male_count / total_patients * 100
    female_pct = female_count / total_patients * 100

    print(f"Males: {male_count} ({male_pct:.2f}%)")
    print(f"Females: {female_count} ({female_pct:.2f}%)")
