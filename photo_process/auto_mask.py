import cv2
import numpy as np
from pathlib import Path
import os
import traceback  # 新增這行以取得詳細錯誤訊息

# 定義顏色常數 (RGB轉HSV)
TARGET_COLORS = {
    'light_blue': {
        'lower': np.array([80, 20, 100]),    # 大幅降低飽和度和亮度要求
        'upper': np.array([200, 255, 255])   # 擴大色相範圍
    }
}

def process_folder(input_folder, update_callback=None):
    """處理資料夾主函數"""
    if not isinstance(input_folder, Path):
        input_folder = Path(input_folder)
    
    if not input_folder.is_dir():
        raise ValueError(f"錯誤: {input_folder} 不是有效資料夾")
    
    output_folder = input_folder.parent / "IMG_Mask"
    output_folder.mkdir(exist_ok=True)
    
    success_count = failure_count = 0
    supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.jfif')
    
    failed_files = []  # 追蹤失敗的檔案
    
    # 使用 rglob 遍歷所有子資料夾
    for file in input_folder.rglob("*"):
        if file.is_file() and file.suffix.lower() in supported_formats:
            try:
                # 計算相對路徑來保持目錄結構
                rel_path = file.relative_to(input_folder)
                target_folder = output_folder / rel_path.parent
                target_folder.mkdir(parents=True, exist_ok=True)
                
                generate_mask(file, target_folder)
                success_count += 1
                if update_callback:
                    update_callback()
            except Exception as e:
                print(f"錯誤 - {file.name}:")
                print(f"  原因: {str(e)}")
                print(f"  位置: {traceback.format_exc()}")
                failure_count += 1
                if update_callback:
                    update_callback()
    
    # 輸出處理結果到終端機
    print(f"\n處理完成! 成功: {success_count} 失敗: {failure_count}")
    
    return success_count, failure_count

def generate_mask(image_path, output_folder):
    """生成遮罩"""
    # 檢查檔案是否存在
    if not os.path.exists(str(image_path)):
        raise ValueError(f"找不到檔案: {image_path}")
    
    # 使用絕對路徑
    abs_path = str(image_path.absolute())
    img = cv2.imdecode(np.fromfile(abs_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"圖片讀取失敗: {abs_path}")
    
    # 轉換到HSV色彩空間
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 建立邊緣遮罩（忽略上下30像素）
    height = img.shape[0]
    edge_mask = np.ones(img.shape[:2], dtype=np.uint8)
    edge_mask[:30, :] = 0  # 上邊30像素
    edge_mask[-120:, :] = 0  # 下邊30像素
    
    # 使用單一較寬的顏色範圍
    color_mask = cv2.inRange(hsv, TARGET_COLORS['light_blue']['lower'], 
                                TARGET_COLORS['light_blue']['upper'])
    
    # 應用邊緣遮罩
    color_mask = cv2.bitwise_and(color_mask, color_mask, mask=edge_mask)
    
    # 增強形態學處理
    kernel = np.ones((7,7), np.uint8)  # 保持原始 kernel 大小
    # 增加膨脹操作的迭代次數以連接較遠的點
    dilated = cv2.dilate(color_mask, kernel, iterations=6)  # 增加 iterations
    # 保持原有的閉運算參數
    dilated = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # 找出所有輪廓
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        raise ValueError("未檢測到藍色十字標記")
    
    # 篩選合適的輪廓
    valid_contours = []
    img_area = img.shape[0] * img.shape[1]
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        # 放寬面積限制（圖片面積的0.1%到25%之間）
        if 0.001 * img_area < area < 0.25 * img_area:
            # 計算最小外接矩形
            rect = cv2.minAreaRect(cnt)
            center, (width, height), angle = rect
            
            if width == 0 or height == 0:
                continue
            
            # 檢查矩形中心是否在圖片中心區域
            img_center_x = img.shape[1] / 2
            img_center_y = img.shape[0] / 2
            center_x, center_y = center
            
            # 放寬中心偏移範圍（圖片寬度/高度的40%）
            max_x_offset = img.shape[1] * 0.4
            max_y_offset = img.shape[0] * 0.4
            
            if (abs(center_x - img_center_x) > max_x_offset or 
                abs(center_y - img_center_y) > max_y_offset):
                continue
            
            # 分析輪廓以找出主要方向
            vx, vy, x, y = cv2.fitLine(cnt, cv2.DIST_L2, 0, 0.01, 0.01)
            angle = np.arctan2(vy, vx) * 180 / np.pi
            
            # 儲存輪廓、面積、中心點和角度
            valid_contours.append((cnt, area, center, angle))
    
    if not valid_contours:
        raise ValueError("未找到符合條件的十字標記")
    
    # 使用最接近中心的輪廓
    max_contour = valid_contours[0][0]
    
    # 計算主要方向向量
    vx, vy, x, y = cv2.fitLine(max_contour, cv2.DIST_L2, 0, 0.01, 0.01)
    main_angle = np.arctan2(vy, vx) * 180 / np.pi
    
    # 計算包圍盒
    rect = cv2.minAreaRect(max_contour)
    center, (width, height), rect_angle = rect
    
    # 調整角度以配合方向向量
    if width < height:
        main_angle = main_angle - 90 if main_angle > 0 else main_angle + 90
    
    # 使用主要方向角度建立旋轉矩形
    rect = (center, (width, height), float(main_angle))
    box = cv2.boxPoints(rect)
    box = box.astype(np.intp)
    
    # 創建遮罩
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [box], 255)
    
    # 處理輸出路徑
    output_path = output_folder / image_path.name
    if not str(output_path).lower().endswith('.png'):
        output_path = output_path.with_suffix('.png')
    
    try:
        # 使用 imencode 和 fromfile 來處理中文路徑
        is_success, buffer = cv2.imencode('.png', mask)
        if not is_success:
            raise ValueError("遮罩編碼失敗")
            
        # 確保輸出目錄存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 直接寫入二進制數據
        with open(str(output_path), 'wb') as f:
            f.write(buffer.tobytes())
            
        return True
        
    except Exception as e:
        raise ValueError(f"無法儲存遮罩 ({str(output_path)}): {str(e)}")

if __name__ == "__main__":
    # 測試代碼
    pass
