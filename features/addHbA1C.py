import pandas as pd
import numpy as np

# ---------- 參數 ----------
csv_file = r"D:\coding\python\senior_project\model\features\metadata_HbA1C.csv"
excel_file = r"D:\coding\python\senior_project\model\features\add_HbA1C.xlsx"
EGFR_TOLERANCE = 0.2   # 容許誤差，可依實際情況調整（0.1 / 0.2 / 0.5）

# ---------- 讀取資料 ----------
df_csv = pd.read_csv(csv_file)
df_xls = pd.read_excel(excel_file)

# ---------- 從 image_name 取出 eGFR ----------
# 97.8_1.jpg -> 97.8
df_csv['egfr_from_image'] = (
    df_csv['image_name']
    .str.split('_')
    .str[0]
    .astype(float)
)

# 確保型別正確
df_xls['matched_eGFR'] = pd.to_numeric(df_xls['matched_eGFR'], errors='coerce')

# ---------- 建立查詢函式 ----------
def find_dm_label(egfr_value, ref_df, tol):
    """
    依 eGFR 近似比對，回傳 是否有糖尿病
    """
    diff = (ref_df['matched_eGFR'] - egfr_value).abs()
    candidates = ref_df[diff <= tol]

    if candidates.empty:
        return np.nan

    # 若多筆，取差距最小的
    idx = diff.loc[candidates.index].idxmin()
    return ref_df.loc[idx, '是否有糖尿病']

# ---------- 套用 ----------
df_csv['是否有糖尿病'] = df_csv['egfr_from_image'].apply(
    lambda x: find_dm_label(x, df_xls, EGFR_TOLERANCE)
)

# ---------- 沒配到的設為 0 ----------
df_csv['是否有糖尿病'] = df_csv['是否有糖尿病'].fillna(0).astype(int)

# ---------- 清理中間欄位 ----------
df_csv.drop(columns=['egfr_from_image'], inplace=True)

# ---------- 輸出 ----------
output_csv = "image_features_with_DM.csv"
df_csv.to_csv(output_csv, index=False, encoding='utf-8-sig')

print(f"完成，輸出檔案：{output_csv}")
print(df_csv['是否有糖尿病'].value_counts())