import os 
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from skimage import measure
from skimage.feature import graycomatrix
from skimage.util import img_as_ubyte
from scipy.ndimage import find_objects
from tqdm import tqdm

# ==================== 參數設定區 ====================
CONFIG = {
    'glcm_levels': 32,
    'glcm_distances': [1, 2],
    'glcm_angles': [0, np.pi/4, np.pi/2, 3*np.pi/4],
    'contrast_kernel_min': 20,
    'contrast_kernel_max': 50,
    'contrast_kernel_scale': 0.35,
    'min_roi_pixels': 100,
    'denoise_kernel': 3,
    'epsilon': 1e-10,
    
    # 標準化設定
    'normalize_features': False,     # 是否進行特徵標準化
    'normalization_method': 'minmax' # 'zscore', 'minmax', 或 None
}

# === 資料夾設定 ===
image_dir = Path(__file__).resolve().parent.parent.parent / "IMG" / "IMG_RB"
mask_dir = Path(__file__).resolve().parent.parent.parent / "IMG" / "IMG_Mask"
csv_path = Path(__file__).parent / "metadata_old.csv"
output_csv = csv_path.parent / "metadata_with_features.csv"

# 讀取 metadata
try:
    df = pd.read_csv(csv_path)
    print(f"✓ 成功載入 {len(df)} 筆資料")
except FileNotFoundError:
    print(f"✗ 錯誤: 找不到檔案 {csv_path}")
    exit(1)

# ==================== 輔助函數 ====================
def find_image_file(image_dir, img_stem):
    """遞迴搜尋影像檔案"""
    for root, dirs, files in os.walk(image_dir):
        for f in files:
            if Path(f).stem == img_stem:
                return Path(root) / f
    return None

def find_mask_file(mask_dir, img_stem):
    """遞迴搜尋遮罩檔案"""
    for root, dirs, files in os.walk(mask_dir):
        for f in files:
            if Path(f).stem == img_stem:
                return Path(root) / f
    return None

# ==================== 特徵提取函數 ====================
def texture_features(img, mask_binary):
    """提取紋理特徵: Entropy 和 Contrast Ratio"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    if CONFIG['denoise_kernel'] > 0:
        gray = cv2.medianBlur(gray, CONFIG['denoise_kernel'])
    
    roi_pixels = gray[mask_binary == 1]
    
    # 檢查 ROI 是否有效
    if roi_pixels.size < CONFIG['min_roi_pixels']:
        return 0, 0
    
    mean_intensity = np.mean(roi_pixels)
    
    # ==================== 計算 Entropy ====================
    labeled_mask = measure.label(mask_binary)
    slices = find_objects(labeled_mask)
    
    if not slices:
        entropy_mean = 0
    else:
        regions = measure.regionprops(labeled_mask)
        if len(regions) == 0:
            entropy_mean = 0
        else:
            largest_region = max(regions, key=lambda r: r.area)
            bbox = largest_region.bbox
            
            cropped_gray = gray[bbox[0]:bbox[2], bbox[1]:bbox[3]]
            cropped_mask = mask_binary[bbox[0]:bbox[2], bbox[1]:bbox[3]]
            
            gray_masked = cropped_gray.copy()
            gray_masked[cropped_mask == 0] = 0
            
            max_val = np.max(gray_masked)
            if max_val == 0:
                entropy_mean = 0
            else:
                levels = CONFIG['glcm_levels']
                gray_scaled = (gray_masked / max_val * (levels - 1)).astype(np.uint8)
                
                try:
                    glcm = graycomatrix(
                        gray_scaled,
                        distances=CONFIG['glcm_distances'],
                        angles=CONFIG['glcm_angles'],
                        levels=levels,
                        symmetric=True,
                        normed=True
                    )
                    
                    glcm_sum = glcm.sum(axis=(0, 1), keepdims=True)
                    probs = glcm / (glcm_sum + CONFIG['epsilon'])
                    entropy_map = -np.sum(probs * np.log2(probs + CONFIG['epsilon']), axis=(0, 1))
                    entropy_mean = np.mean(entropy_map)
                    
                except Exception as e:
                    print(f"  警告: GLCM 計算失敗 - {e}")
                    entropy_mean = 0
    
    # ==================== 計算 Contrast Ratio ====================
    roi_area = np.sum(mask_binary)
    kernel_size = int(np.sqrt(roi_area) * CONFIG['contrast_kernel_scale'])
    kernel_size = np.clip(kernel_size, 
                         CONFIG['contrast_kernel_min'], 
                         CONFIG['contrast_kernel_max'])
    kernel_size = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
    
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    dilated_mask = cv2.dilate(mask_binary.astype(np.uint8), kernel, iterations=1)
    
    ring_mask = dilated_mask - mask_binary
    ring_mask = np.clip(ring_mask, 0, 1)
    
    background_pixels = gray[ring_mask == 1]
    
    if background_pixels.size < 10:
        contrast_ratio = 1.0
    else:
        background_mean = np.mean(background_pixels)
        contrast_ratio = mean_intensity / (background_mean + CONFIG['epsilon'])
    
    return entropy_mean, contrast_ratio

def shape_features(mask_binary):
    """提取形狀特徵: 長軸長度"""
    if np.sum(mask_binary) < CONFIG['min_roi_pixels']:
        return 0
    
    labeled_mask = measure.label(mask_binary)
    regions = measure.regionprops(labeled_mask)
    
    if len(regions) == 0:
        return 0
    
    region = max(regions, key=lambda r: r.area)
    length = region.major_axis_length
    
    return length

# ==================== 主要處理流程 ====================
print("\n開始處理影像...")

length_list, entropy_list, contrast_list = [], [], []
error_count = 0

for idx, row in tqdm(df.iterrows(), total=len(df), desc="處理進度"):
    img_name = row['image_name']
    img_stem = Path(img_name).stem
    
    img_path = find_image_file(image_dir, img_stem)
    mask_path = find_mask_file(mask_dir, img_stem)
    
    if img_path is None or not img_path.exists():
        error_count += 1
        for lst in [length_list, entropy_list, contrast_list]:
            lst.append(np.nan)
        continue
    
    if mask_path is None or not mask_path.exists():
        error_count += 1
        for lst in [length_list, entropy_list, contrast_list]:
            lst.append(np.nan)
        continue
    
    img = cv2.imread(str(img_path))
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    
    if img is None or mask is None:
        error_count += 1
        for lst in [length_list, entropy_list, contrast_list]:
            lst.append(np.nan)
        continue
    
    if mask.shape != img.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]), 
                         interpolation=cv2.INTER_NEAREST)
    
    _, mask_binary = cv2.threshold(mask, 127, 1, cv2.THRESH_BINARY)
    
    try:
        length = shape_features(mask_binary)
        entropy, contrast_ratio = texture_features(img, mask_binary)
        
        length_list.append(length)
        entropy_list.append(entropy)
        contrast_list.append(contrast_ratio)
        
    except Exception as e:
        print(f"\n✗ 處理失敗: {img_name} - {e}")
        error_count += 1
        for lst in [length_list, entropy_list, contrast_list]:
            lst.append(np.nan)

# ==================== 寫入原始特徵 ====================
df['Length_px'] = length_list
df['Entropy'] = entropy_list
df['Contrast_Ratio'] = contrast_list

# ==================== 特徵標準化 ====================
if CONFIG.get('normalize_features', False):
    method = CONFIG.get('normalization_method', 'zscore')
    
    if method == 'zscore':
        # Z-score 標準化: (x - mean) / std
        for col in ['Length_px', 'Entropy', 'Contrast_Ratio']:
            valid_data = df[col].dropna()
            if len(valid_data) > 0:
                mean_val = valid_data.mean()
                std_val = valid_data.std()
                if std_val > 0:
                    df[f'{col}_norm'] = (df[col] - mean_val) / std_val
                else:
                    df[f'{col}_norm'] = 0
    
    elif method == 'minmax':
        # Min-Max 正規化: (x - min) / (max - min)
        for col in ['Length_px', 'Entropy', 'Contrast_Ratio']:
            valid_data = df[col].dropna()
            if len(valid_data) > 0:
                min_val = valid_data.min()
                max_val = valid_data.max()
                if max_val > min_val:
                    df[f'{col}_norm'] = (df[col] - min_val) / (max_val - min_val)
                else:
                    df[f'{col}_norm'] = 0

df[['image_name', 'age', 'gender', 'Length_px', 'Entropy', 'Contrast_Ratio']].to_csv(output_csv, index=False)

# ==================== 統計報告 ====================
print(f"\n{'='*60}")
print(f"處理完成!")
print(f"{'='*60}")
print(f"總筆數: {len(df)}")
print(f"成功處理: {len(df) - error_count} 筆")
print(f"失敗/缺失: {error_count} 筆")


print(f"\n原始特徵統計:")
for col in ['Length_px', 'Entropy', 'Contrast_Ratio']:
    valid_count = df[col].notna().sum()
    if valid_count > 0:
        print(f"  {col:15s} - 有效: {valid_count:4d}, "
              f"範圍: [{df[col].min():.4f}, {df[col].max():.4f}], "
              f"均值: {df[col].mean():.4f}")

if CONFIG.get('normalize_features', False):
    method = CONFIG.get('normalization_method', 'zscore')
    print(f"\n標準化特徵統計 (方法: {method}):")
    for col in ['Length_px_norm', 'Entropy_norm', 'Contrast_Ratio_norm']:
        if col in df.columns:
            valid_count = df[col].notna().sum()
            if valid_count > 0:
                print(f"  {col:20s} - 有效: {valid_count:4d}, "
                      f"範圍: [{df[col].min():.4f}, {df[col].max():.4f}], "
                      f"均值: {df[col].mean():.4f}")

print(f"\n輸出檔案: {output_csv}")
print(f"{'='*60}\n")