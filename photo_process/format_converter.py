from pathlib import Path
from PIL import Image

def process_folder(folder, progress_callback=None):
    """將資料夾中的 JFIF 檔案轉換為 JPG"""
    success = 0
    failure = 0
    error_files = []
    
    # 搜尋所有 JFIF 檔案（包含子資料夾）
    jfif_files = list(folder.rglob("*.jfif"))
    
    if len(jfif_files) == 0:
        return (0, 0, [])
    
    for file_path in jfif_files:
        try:
            # 讀取圖片
            with Image.open(file_path) as img:
                # 轉換為 RGB 模式（如果是 RGBA 或其他模式）
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 建立新的檔案路徑（保持相同目錄，只改副檔名）
                new_path = file_path.with_suffix('.jpg')
                
                # 儲存為 JPG
                img.save(new_path, 'JPEG', quality=95)
            
            # 刪除原始檔案
            file_path.unlink()
            
            success += 1
            
        except Exception as e:
            failure += 1
            error_files.append((str(file_path), str(e)))
        
        finally:
            # 調用進度回調
            if progress_callback:
                progress_callback()
    
    return (success, failure, error_files)

def count_files(folder):
    """計算資料夾中 JFIF 檔案的數量"""
    return len(list(folder.rglob("*.jfif")))