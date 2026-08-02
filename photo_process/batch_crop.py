import cv2
import numpy as np
from pathlib import Path
from tkinter import filedialog
import tkinter as tk
import sys
import traceback

# 設定系統編碼
sys.stdout.reconfigure(encoding='utf-8')

# 目標尺寸
TARGET_WIDTH = 1600
TARGET_HEIGHT = 1200

# 裁剪參數：設定裁剪區域
CROP_PARAMS = {
    'left': 235,
    'upper': 90,
    'width': 1024,
    'height': 1024
}
EXCLUDE_FOLDERS = ['移出圖片']
SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.jfif')

def process_folder(input_folder, progress_callback=None):
    """處理資料夾主函數"""
    if not isinstance(input_folder, Path):
        input_folder = Path(input_folder).resolve()
    
    if not input_folder.is_dir():
        raise ValueError(f"錯誤: {input_folder} 不是有效資料夾")
    
    # 修改輸出目錄，直接使用 IMG_Cut
    output_base = input_folder.parent / 'IMG_Cut'
    output_base.mkdir(parents=True, exist_ok=True)
    
    success_count = failure_count = 0
    error_files = []  # 新增錯誤檔案清單
    processed_count = 0
    
    # 遍歷所有子目錄
    for path in input_folder.rglob("*"):
        if any(excluded in path.parts for excluded in EXCLUDE_FOLDERS):
            continue
        
        if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS:
            processed_count += 1
            try:
                # 修改輸出路徑計算方式
                rel_path = path.parent.relative_to(input_folder)
                if str(rel_path) == '.':  # 如果是根目錄
                    output_folder = output_base
                else:
                    output_folder = (output_base / rel_path).resolve()
                output_folder.mkdir(parents=True, exist_ok=True)
                
                result = crop_image(path, output_folder)
                if result is True:
                    success_count += 1
                    #if processed_count % 50 == 0:  # 每50張顯示進度
                    #    print(f"處理進度: {processed_count} 張 (成功: {success_count}, 失敗: {failure_count})")
                else:
                    failure_count += 1
                    error_files.append((path.name, str(result)))
                    # 即時顯示錯誤
                    print(f"✗ 失敗 [{failure_count}]: {path.name}")
                    print(f"  原因: {result}")
                    
            except Exception as e:
                failure_count += 1
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                error_files.append((path.name, error_msg))
                # 即時顯示錯誤
                print(f"✗ 異常 [{failure_count}]: {path.name}")
                print(f"  原因: {str(e)}")
            
            if progress_callback:
                progress_callback()
    
    return success_count, failure_count, error_files

def crop_image(image_path, output_folder):
    """裁切圖片"""
    try:
        # 使用完整的 Unicode 路徑讀取圖片
        file_array = np.fromfile(str(image_path), dtype=np.uint8)
        if file_array.size == 0:
            return "檔案為空或無法讀取"
        
        img = cv2.imdecode(file_array, cv2.IMREAD_COLOR)
        if img is None:
            return f"無法解碼圖片 (可能是損壞的檔案或不支援的格式)"
        
        # 檢查圖片尺寸
        height, width = img.shape[:2]
        original_size = f"{width}x{height}"
        
        # 如果尺寸不是 1600x1200，先 resize
        if width != TARGET_WIDTH or height != TARGET_HEIGHT:
            try:
                img = cv2.resize(img, (TARGET_WIDTH, TARGET_HEIGHT), interpolation=cv2.INTER_LANCZOS4)
            except Exception as resize_error:
                return f"Resize失敗 (原始尺寸: {original_size}): {str(resize_error)}"
        
        # 使用固定區域裁切
        right = CROP_PARAMS['left'] + CROP_PARAMS['width']
        lower = CROP_PARAMS['upper'] + CROP_PARAMS['height']
        
        # 檢查裁切範圍是否有效
        if right > img.shape[1] or lower > img.shape[0]:
            return f"裁切範圍超出圖片邊界 (圖片: {img.shape[1]}x{img.shape[0]}, 裁切需要: {right}x{lower})"
        
        cropped = img[CROP_PARAMS['upper']:lower, CROP_PARAMS['left']:right]
        
        # 檢查裁切結果
        if cropped.size == 0:
            return f"裁切結果為空 (原始尺寸: {original_size})"
        
        # 使用 imencode 處理中文路徑的寫入
        output_path = output_folder / image_path.name
        
        # 確認副檔名有效
        extension = image_path.suffix.lower()
        if extension == '.jfif':
            extension = '.jpg'  # JFIF 使用 JPEG 編碼
        
        success, img_encoded = cv2.imencode(extension, cropped)
        
        if not success:
            return f"編碼失敗 (格式: {extension})"
        
        # 嘗試寫入檔案
        try:
            img_encoded.tofile(str(output_path))
        except Exception as write_error:
            return f"寫入檔案失敗: {str(write_error)}"
        
        return True
    
    except Exception as e:
        return f"未預期的錯誤: {str(e)}"

if __name__ == "__main__":
    try:
        # 建立 root 視窗但隱藏它
        root = tk.Tk()
        root.withdraw()
        
        # 使用對話框選擇資料夾
        folder_path = filedialog.askdirectory(title="選擇要處理的圖片資料夾")
        if not folder_path:  # 使用者取消選擇
            print("已取消操作")
            exit()
        
        test_folder = Path(folder_path)
        print(f"\n{'='*60}")
        print(f"開始處理資料夾: {test_folder}")
        print(f"{'='*60}\n")
        
        # 執行處理
        success, failure, error_files = process_folder(test_folder)
        
        # 顯示結果
        print(f"\n{'='*60}")
        print("處理完成！")
        print(f"{'='*60}")
        print(f"✓ 成功處理: {success} 張圖片")
        print(f"✗ 處理失敗: {failure} 張圖片")
        print(f"📁 輸出位置: {test_folder.parent / 'IMG_Cut'}")
        
        # 顯示錯誤統計
        if error_files:
            print(f"\n{'='*60}")
            print("錯誤類型統計")
            print(f"{'='*60}")
            
            # 統計錯誤類型
            error_types = {}
            for filename, error in error_files:
                # 取得錯誤的主要類型（取第一行或前50字元）
                error_key = error.split('\n')[0][:80]
                if error_key not in error_types:
                    error_types[error_key] = []
                error_types[error_key].append(filename)
            
            # 顯示錯誤統計
            for i, (error_type, files) in enumerate(error_types.items(), 1):
                print(f"\n[錯誤類型 {i}] {error_type}")
                print(f"影響檔案數: {len(files)}")
                print(f"範例檔案:")
                for f in files[:3]:  # 只顯示前3個
                    print(f"  • {f}")
                if len(files) > 3:
                    print(f"  ... 還有 {len(files)-3} 個檔案")
            
            # 將詳細錯誤記錄寫入檔案
            error_log_path = test_folder.parent / 'IMG_Cut' / 'error_log.txt'
            with open(error_log_path, 'w', encoding='utf-8') as f:
                f.write("圖片處理失敗詳細記錄\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"總共失敗: {failure} 張圖片\n")
                f.write(f"處理時間: {Path.cwd()}\n\n")
                f.write("=" * 80 + "\n\n")
                
                for i, (filename, error) in enumerate(error_files, 1):
                    f.write(f"[{i}] 檔案: {filename}\n")
                    f.write(f"錯誤訊息:\n{error}\n")
                    f.write("-" * 80 + "\n\n")
            
            print(f"\n📄 詳細錯誤記錄已儲存至: {error_log_path}")
        
        print(f"\n{'='*60}\n")
    
    except Exception as e:
        print(f"\n{'!'*60}")
        print(f"執行時發生嚴重錯誤: {str(e)}")
        print(f"{'!'*60}")
        traceback.print_exc()