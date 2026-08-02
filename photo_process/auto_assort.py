import cv2
import numpy as np
from pathlib import Path
import shutil
import random
import sys
from PIL import Image  # 匯入PIL的Image模組以進行圖片格式轉換

# 設定輸出編碼，避免亂碼
sys.stdout.reconfigure(encoding='utf-8')

# 支援的圖片格式
SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.jfif')

def process_folder(input_folder, update_callback=None, mask_folder=None):
    """處理資料夾主函數"""
    if not isinstance(input_folder, Path):
        input_folder = Path(input_folder)
    
    if not input_folder.is_dir():
        raise ValueError(f"錯誤: {input_folder} 不是有效資料夾")
    
    # 執行兩種分類方法並取得結果
    method1_summary = [split_dataset(input_folder, mask_folder=mask_folder)]  # 轉換為單一元素列表
    method2_summary = split_within_categories(input_folder)  # 已經是列表
    
    return method1_summary, method2_summary

def split_dataset(input_dir, output_dir=None, train_ratio=7, val_ratio=2, test_ratio=1, mask_folder=None):
    """方法一：直接分割所有圖片"""
    if output_dir is None:
        output_dir = input_dir.parent / "IMG_train"
    
    if not isinstance(input_dir, Path):
        input_dir = Path(input_dir)
    if not isinstance(output_dir, Path):
        output_dir = Path(output_dir)
        
    # 建立新的資料夾結構
    method1_dir = output_dir / "method1"
    dirs = {
        'train': {'images': method1_dir / "train" / "images", 
                 'masks': method1_dir / "train" / "masks"},
        'val': {'images': method1_dir / "val" / "images", 
               'masks': method1_dir / "val" / "masks"},
        'test': {'images': method1_dir / "test" / "images", 
                'masks': method1_dir / "test" / "masks"}
    }
    
    # 建立所有必要的資料夾
    for split_dirs in dirs.values():
        for dir_path in split_dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)
    
    # 找出所有圖片檔案
    all_files = list(input_dir.rglob("*.*"))
    all_files = [f for f in all_files if f.suffix.lower() in SUPPORTED_FORMATS]
    
    # 尋找對應的遮罩檔案
    mask_dir = Path(mask_folder) if mask_folder else input_dir.parent / "IMG_Mask"
    if not mask_dir.exists():
        print(f"警告: 遮罩資料夾 {mask_dir} 不存在")
    
    # 建立遮罩檔案字典，忽略副檔名
    mask_files = {}
    if mask_dir.exists():
        for mask_file in mask_dir.rglob("*.*"):
            if mask_file.suffix.lower() in SUPPORTED_FORMATS:
                # 使用不含副檔名的檔案名作為鍵值
                mask_files[mask_file.stem] = mask_file
                # 額外支援 xxx_mask 格式
                if mask_file.stem.endswith("_mask"):
                    base_name = mask_file.stem[:-5]  # 去掉"_mask"
                    mask_files[base_name] = mask_file
    
    # 只保留有對應遮罩的圖片
    valid_files = []
    for img_file in all_files:
        # 使用不含副檔名的檔案名尋找對應遮罩
        corresponding_mask = mask_files.get(img_file.stem)
        if corresponding_mask:
            valid_files.append((img_file, corresponding_mask))
        else:
            print(f"警告: 找不到圖片 {img_file.name} 的遮罩檔案")
    
    # 輸出處理結果統計
    print(f"找到 {len(valid_files)} 對有效的圖片-遮罩配對（共 {len(all_files)} 張圖片）")
    
    # 打亂檔案順序
    random.shuffle(valid_files)
    
    # 計算分配數量 (70/20/10 分割)
    total_files = len(valid_files)
    train_ratio, val_ratio, test_ratio = 7, 2, 1
    total_ratio = train_ratio + val_ratio + test_ratio
    
    train_count = (total_files * train_ratio) // total_ratio
    val_count = (total_files * val_ratio) // total_ratio
    
    # 分配檔案
    train_files = valid_files[:train_count]
    val_files = valid_files[train_count:train_count + val_count]
    test_files = valid_files[train_count + val_count:]
    
    # 複製檔案到對應資料夾
    for files, split in [(train_files, 'train'), 
                        (val_files, 'val'), 
                        (test_files, 'test')]:
        for img_file, mask_file in files:
            # 複製圖片 (保持原始格式)
            img_dest = dirs[split]['images'] / img_file.name
            shutil.copy2(img_file, img_dest)
            
            # 複製遮罩 (確保為PNG格式)
            # 若檔名為 xxx_mask，複製時移除 "_mask"
            mask_stem = mask_file.stem
            if mask_stem.endswith("_mask"):
                mask_stem = mask_stem[:-5]
            mask_dest = dirs[split]['masks'] / f"{mask_stem}.png"
            if mask_file.suffix.lower() != '.png':
                # 如果不是PNG，則轉換
                mask_img = Image.open(mask_file)
                mask_img.save(mask_dest, 'PNG')
            else:
                shutil.copy2(mask_file, mask_dest)
    
    # 返回分配結果
    return f"train={len(train_files)}(含遮罩), val={len(val_files)}(含遮罩), test={len(test_files)}(含遮罩)"

def split_within_categories(input_dir, output_dir=None, train_ratio=7, val_ratio=2, test_ratio=1):
    """方法二：按類別分割"""
    if output_dir is None:
        output_dir = input_dir.parent / "IMG_train"
    
    if not isinstance(input_dir, Path):
        input_dir = Path(input_dir)
    if not isinstance(output_dir, Path):
        output_dir = Path(output_dir)
    
    # 建立資料夾
    method2_dir = output_dir / "method2"
    train_dir = method2_dir / "train"
    val_dir = method2_dir / "val"
    test_dir = method2_dir / "test"

    for dir in [train_dir, val_dir, test_dir]:
        dir.mkdir(parents=True, exist_ok=True)  # 修正：必須 parents=True

    # 回傳每個類別的分配結果字串
    results = []
    for category_dir in input_dir.iterdir():
        if not category_dir.is_dir():
            continue
        
        category = category_dir.name
        # 建立對應的分類資料夾
        for dir in [train_dir, val_dir, test_dir]:
            (dir / category).mkdir(exist_ok=True)
            
        files = list(category_dir.glob("*.*"))
        files = [f for f in files if f.suffix.lower() in SUPPORTED_FORMATS]
        random.shuffle(files)
        
        total_files = len(files)
        train_count = (total_files * train_ratio) // (train_ratio + val_ratio + test_ratio)
        val_count = (total_files * val_ratio) // (train_ratio + val_ratio + test_ratio)
        
        train_files = files[:train_count]
        val_files = files[train_count:train_count + val_count]
        test_files = files[train_count + val_count:]
        
        for src, dst_dir in [(train_files, train_dir), 
                            (val_files, val_dir), 
                            (test_files, test_dir)]:
            for f in src:
                shutil.copy2(f, dst_dir / category / f.name)
                
        results.append(f"{category}: train={len(train_files)}, val={len(val_files)}, test={len(test_files)}")
    
    # 如果沒有結果，加入提示訊息
    if not results:
        results.append("未發現任何有效的分類資料夾")
    
    return results

if __name__ == "__main__":
    # 測試代碼
    pass
