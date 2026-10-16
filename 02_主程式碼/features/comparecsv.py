import pandas as pd
import matplotlib.pyplot as plt
try:
    from ._paths import reference
except ImportError:
    from _paths import reference

# === 1. 讀取 CSV ===
csv_a_path = reference('metadata_old.csv')   # 第一個 CSV
csv_b_path = reference('dataset_original.csv')           # 第二個 CSV

df_a = pd.read_csv(csv_a_path)
df_b = pd.read_csv(csv_b_path)

# === 2. 從 image_name 取出數值（97.8_1.jpg → 97.8）===
def extract_score(image_name):
    return float(image_name.split("_")[0])

df_a["score"] = df_a["image_name"].apply(extract_score)
df_b["score"] = df_b["image_name"].apply(extract_score)

# === 3. 定義分區函式 ===
def score_to_group(x):
    if x < 15:
        return "-15"
    elif x < 30:
        return "15-29"
    elif x < 60:
        return "30-59"
    elif x < 90:
        return "60-89"
    else:
        return "90-"

df_a["group"] = df_a["score"].apply(score_to_group)
df_b["group"] = df_b["score"].apply(score_to_group)

# === 4. 各區間數量統計 ===
groups = ["-15", "15-29", "30-59", "60-89", "90-"]

count_a = df_a["group"].value_counts().reindex(groups, fill_value=0)
count_b = df_b["group"].value_counts().reindex(groups, fill_value=0)

# === 5. 畫對比長條圖 ===
x = range(len(groups))
width = 0.35

plt.figure(figsize=(8, 5))
plt.bar(x, count_b, width, label="Old dataset", color="#EEA4A4")
plt.bar([i + width for i in x], count_a, width, label="New dataset", color="#A2EDA2")

plt.xticks([i + width / 2 for i in x], groups)
plt.xlabel("eGFR Category")
plt.ylabel("Image Count")
plt.title("Image Count Comparison by eGFR")
plt.legend()

plt.tight_layout()
plt.show()
