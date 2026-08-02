import cv2
import numpy as np
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, Label, Button, Frame
from PIL import Image, ImageTk

SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.jfif')
selected_image_path = None
MAX_PREVIEW_SIZE = (500, 500)

# 全域變數：儲存原圖、比例
original_image = None
scale_x = scale_y = 1.0

def generate_color_mask(image):
    """生成彩色區域和白色區域的 mask"""
    h, w = image.shape[:2]
    img_float = image.astype(np.float32)
    
    # ----- 彩色區域檢測 -----
    diff_rg = np.abs(img_float[:,:,0] - img_float[:,:,1])
    diff_rb = np.abs(img_float[:,:,0] - img_float[:,:,2])
    diff_gb = np.abs(img_float[:,:,1] - img_float[:,:,2])
    color_mask = ((diff_rg > 20) | (diff_rb > 20) | (diff_gb > 20)).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # 膨脹彩色區域 2 像素
    color_mask = cv2.dilate(color_mask, np.ones((3,3), np.uint8), iterations=2)

    # ----- 白色區域檢測 (R, G, B 都 > 240) -----
    white_mask = ((img_float[:,:,0] > 240) & 
                  (img_float[:,:,1] > 240) & 
                  (img_float[:,:,2] > 240)).astype(np.uint8) * 255
    
    # 白色區域額外膨脹 2 像素
    white_mask = cv2.dilate(white_mask, np.ones((3,3), np.uint8), iterations=4)

    # 合併兩個 mask
    combined_mask = cv2.bitwise_or(color_mask, white_mask)
    
    return combined_mask

def process_image(image_path, output_folder):
    """處理單張圖片"""
    try:
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)

        image_path = Path(image_path)
        safe_path = str(image_path.absolute())

        # 讀取圖片
        with open(safe_path, 'rb') as f:
            image_array = np.frombuffer(f.read(), np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if image is None:
            raise ValueError("圖片讀取失敗")

        h, w = image.shape[:2]

        # 生成 mask (包含彩色和白色區域)
        mask = generate_color_mask(image)

        # Inpaint 修復
        result = cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)
        
        # 固定區域黑化
        result[:40, :] = (0, 0, 0)              # 上方 40 行
        result[h-100:, :] = (0, 0, 0)           # 下方 100 行
        result[:, :25] = (0, 0, 0)              # 左方 25 行
        result[400:485, 20:40] = (0, 0, 0)      # 左中小區塊
        result[50:105, 800:920] = (0, 0, 0)     # 右上小區塊
        result[0:105, 1000:1024] = (0, 0, 0)    # 右上邊區塊

        # 輸出路徑
        output_path = output_folder / image_path.name
        save_extension = image_path.suffix.lower()
        if save_extension == '.jfif':
            save_extension = '.jpg'
            output_path = output_folder / (image_path.stem + '.jpg')

        # 儲存圖片
        is_success, buffer = cv2.imencode(save_extension, result)
        if is_success:
            with open(str(output_path.absolute()), 'wb') as f:
                f.write(buffer)
        else:
            raise ValueError(f"圖片編碼失敗 (格式: {save_extension})")

        return True, ""
    except Exception as e:
        return False, str(e)


def process_folder(input_folder, output_folder, progress_callback=None):
    """處理資料夾的主要函數"""
    input_folder = Path(input_folder) if not isinstance(input_folder, Path) else input_folder
    if not input_folder.is_dir():
        raise ValueError(f"錯誤: {input_folder} 不是有效資料夾")

    output_folder = Path(output_folder) if not isinstance(output_folder, Path) else output_folder
    output_folder.mkdir(exist_ok=True)

    success_count, failure_count = 0, 0
    error_files = []
    
    for item in input_folder.rglob("*"):
        if item.is_file() and item.suffix.lower() in SUPPORTED_FORMATS:
            rel_path = item.relative_to(input_folder)
            target_folder = output_folder / rel_path.parent
            target_folder.mkdir(parents=True, exist_ok=True)
            
            success, error_msg = process_image(item, target_folder)
            if success:
                success_count += 1
            else:
                failure_count += 1
                error_files.append((item.name, error_msg))
                print(f"✗ 處理失敗: {item.name}")
                print(f"  原因: {error_msg}")
            
            if progress_callback:
                progress_callback()
    
    return success_count, failure_count, error_files

def load_image_preview(image_path, highlight_color=(0,0,255), alpha=0.5, fix=False, max_size=(500,500)):
    """載入圖片並在原圖上高亮標注，或做 inpaint 修復"""
    global original_image, scale_x, scale_y
    image_path = Path(image_path)
    image_array = np.frombuffer(image_path.read_bytes(), np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("圖片讀取失敗")
    original_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    h, w = image.shape[:2]

    # 生成 mask (包含彩色和白色區域)
    mask = generate_color_mask(image)

    if fix:
        result = cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)
        result[:40, :] = (0, 0, 0)              # 上方 40 行
        result[h-110:, :] = (0, 0, 0)           # 下方 110 行
        result[:, :25] = (0, 0, 0)              # 左方 25 行
        result[400:485, 20:40] = (0, 0, 0)      # 左中小區塊
        result[50:105, 800:920] = (0, 0, 0)     # 右上小區塊
        result[0:105, 1000:1024] = (0, 0, 0)    # 右上邊區塊
        img_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
    else:
        highlighted = image.copy()
        overlay = np.full_like(image, highlight_color)
        highlighted[mask > 0] = cv2.addWeighted(image, 1-alpha, overlay, alpha, 0)[mask > 0]
        img_rgb = cv2.cvtColor(highlighted, cv2.COLOR_BGR2RGB)

    pil_img = Image.fromarray(img_rgb)
    scale_x = image.shape[1] / max_size[0]
    scale_y = image.shape[0] / max_size[1]
    pil_img.thumbnail(max_size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(pil_img)

def select_image():
    global selected_image_path
    file_path = filedialog.askopenfilename(
        title="選擇圖片",
        filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.webp *.jfif")]
    )
    if file_path:
        selected_image_path = file_path
        try:
            # 顯示原圖預覽
            preview_img = load_image_preview(file_path, fix=False, max_size=(preview_frame.winfo_width(), preview_frame.winfo_height()))
            preview_label.config(image=preview_img)
            preview_label.image = preview_img

            # 顯示修復預覽
            inpaint_img = load_image_preview(file_path, fix=True, max_size=(inpaint_frame.winfo_width(), inpaint_frame.winfo_height()))
            inpaint_label.config(image=inpaint_img)
            inpaint_label.image = inpaint_img

        except Exception as e:
            print(f"載入失敗: {e}")

def refresh_previews():
    """視窗縮放時刷新圖片縮放"""
    if selected_image_path:
        try:
            preview_img = load_image_preview(selected_image_path, fix=False, max_size=(preview_frame.winfo_width(), preview_frame.winfo_height()))
            preview_label.config(image=preview_img)
            preview_label.image = preview_img

            inpaint_img = load_image_preview(selected_image_path, fix=True, max_size=(inpaint_frame.winfo_width(), inpaint_frame.winfo_height()))
            inpaint_label.config(image=inpaint_img)
            inpaint_label.image = inpaint_img
        except:
            pass

# 測試用主程式
if __name__ == "__main__":
    try:
        root = tk.Tk()
        root.title("色域選取與修復預覽")

        # 按鈕區
        btn_frame = Frame(root)
        btn_frame.pack(pady=5)
        btn_select = Button(btn_frame, text="選擇圖片", command=select_image)
        btn_select.pack(side="left", padx=5)

        # 預覽區
        preview_container = Frame(root)
        preview_container.pack(fill="both", expand=True, padx=10, pady=10)

        preview_frame = Frame(preview_container, bd=2, relief="sunken", width=500, height=500)
        preview_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        preview_frame.pack_propagate(False)
        preview_label = Label(preview_frame)
        preview_label.pack(fill="both", expand=True)

        inpaint_frame = Frame(preview_container, bd=2, relief="sunken", width=500, height=500)
        inpaint_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        inpaint_frame.pack_propagate(False)
        inpaint_label = Label(inpaint_frame)
        inpaint_label.pack(fill="both", expand=True)

        # 座標與顏色顯示
        coord_label = Label(root, text="滑鼠座標：", font=("Consolas", 11))
        coord_label.pack(pady=5)

        def show_original_position(event):
            """顯示原圖座標與顏色"""
            global original_image, scale_x, scale_y
            if original_image is None:
                return

            # 將預覽座標轉回原圖座標
            orig_x = int(event.x * scale_x)
            orig_y = int(event.y * scale_y)

            if 0 <= orig_x < original_image.width and 0 <= orig_y < original_image.height:
                r, g, b = original_image.getpixel((orig_x, orig_y))
                coord_label.config(text=f"原圖座標: ({orig_x}, {orig_y})  顏色: R={r} G={g} B={b}")

        # 綁定滑鼠事件
        preview_label.bind("<Motion>", show_original_position)
        inpaint_label.bind("<Motion>", show_original_position)

        root.bind("<Configure>", lambda e: refresh_previews())
        root.mainloop()

    except Exception as e:
        print(f"執行錯誤: {str(e)}")
        import traceback
        traceback.print_exc()