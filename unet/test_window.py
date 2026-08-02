import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import torch
from torchvision import transforms
from PIL import Image
import matplotlib.font_manager as fm
import os
from PIL import Image, ImageTk
import math
import numpy as np
import cv2
import glob

class TestWindow:
    def __init__(self, model, device, test_image_dir):
        # 設定中文字型
        self.font = fm.FontProperties(fname=r'C:\Windows\Fonts\msjh.ttc')
        self.test_image_dir = test_image_dir
        self.test_images = []
        self.image_items = []  # 新增圖片項目列表
        self.image_paths = []  # 新增圖片路徑列表
        self.image_cache = {}  # 新增圖片快取
        self.selected_item = None  # 新增選中項目追褶
        
        self.window = tk.Toplevel()
        self.window.title("UNet 測試視窗")  # 更新標題
        self.window.geometry("1200x900")
        self.model = model
        self.device = device
        self.current_image = None
        self.current_mask = None
        
        self.thumbnail_size = (100, 100)
        self.thumbnails = []
        
        # 新增GUI設定
        self.GUI_CONFIG = {
            'window_size': "1550x900",
            'thumbnail_size': (100, 100),
            'display_size': (500, 500),
            'button_width': 8,
            'button_height': 3,
            'button_padding': 10,
            'section_weights': [10, 45, 45],
            'left_frame_width': 250,  # 增加左側框架寬度
            'preview_frame_height': 512,
            'metrics_height': 200,
        }
        
        # 修改樣式設定
        self.style = ttk.Style()
        styles = {
            "ImageItem.TFrame": {"padding": 5, "background": "white"},
            "Selected.ImageItem.TFrame": {"padding": 5, "background": "lightblue"},
            "ImageItem.TLabel": {"background": "white"},
            "Selected.ImageItem.TLabel": {"background": "lightblue"},
            "Action.TButton": {
                "padding": 10,
                "font": ("Arial", 11, "bold"),
                "width": 8,
                "height": 3
            }
        }
        
        for style_name, props in styles.items():
            self.style.configure(style_name, **props)
        
        # GUI初始化
        self._create_gui()
        # 載入圖片
        self.load_images()

        # 初始化評估指標
        self.metrics = {
            'total_dice': 0,
            'total_count': 0,
        }

    def _create_gui(self):
        # 建立主要框架，使用grid佈局
        self.window.grid_rowconfigure(0, weight=1)
        # 修正：左側區塊 weight 設為 0，minsize 設定為 left_frame_width，避免被推擠
        self.window.grid_columnconfigure(0, weight=0, minsize=self.GUI_CONFIG['left_frame_width'])
        self.window.grid_columnconfigure(1, weight=0, minsize=350)
        self.window.grid_columnconfigure(2, weight=45)

        # 左側區域：圖片列表和按鈕
        left_frame = self._create_left_frame()
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # 中間區域：原始圖片和預測結果
        middle_frame = self._create_middle_frame()
        middle_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        # 右側區域：結果疊加和評估指標
        right_frame = self._create_right_frame()
        right_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)

    def _create_left_frame(self):
        frame = ttk.LabelFrame(self.window, text="圖片列表")

        # 創建捲動區域
        scroll_container = ttk.Frame(frame)
        scroll_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 調整 canvas, scrollable_frame, scroll_container 都要明確設定寬度，避免自動縮小
        canvas_width = self.GUI_CONFIG['left_frame_width'] + 20
        self.canvas = tk.Canvas(scroll_container, width=canvas_width, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas, width=canvas_width)
        self.scrollable_frame.config(width=canvas_width)
        
        # 配置捲動，設定相同的寬度
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all"),
                width=canvas_width  # 設定相同的寬度
            )
        )
        
        # 設定視窗寬度與畫布相同
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=canvas_width)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # 放置捲動元件
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 滑鼠滾輪事件
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 建立按鈕容器，固定高度
        button_container = ttk.Frame(frame)
        button_container.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # 建立三個按鈕
        buttons = [
            ("預測此圖", self.predict),  # 改成 predict
            ("預測全部", self.predict_all),
            ("重置狀態", self.reset_state)
        ]

        for text, command in buttons:
            btn = ttk.Button(
                button_container,
                text=text,
                command=command,
                style="Action.TButton"
            )
            btn.pack(fill=tk.X, pady=3, ipady=8)  # 使用 ipady 增加按鈕高度
        
        return frame

    def _create_middle_frame(self):
        preview_size = (290, 290)
        self._mask_preview_size = preview_size

        frame = ttk.LabelFrame(self.window, text="遮罩視覺化", width=preview_size[0])
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.config(width=preview_size[0])
        frame.pack_propagate(False)

        # 建立三個固定寬度的內層 frame，恢復上下padding
        gt_frame = tk.Frame(frame, width=preview_size[0], height=preview_size[1], bg="white")
        gt_frame.grid_propagate(False)
        gt_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=(10, 5))
        self.gt_mask_preview = tk.Label(
            gt_frame, bg="white",
            width=preview_size[0], height=preview_size[1]
        )
        self.gt_mask_preview.pack(expand=False, fill=None, padx=0, pady=0)
        gt_frame.pack_propagate(False)

        pred_frame = tk.Frame(frame, width=preview_size[0], height=preview_size[1], bg="white")
        pred_frame.grid_propagate(False)
        pred_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=5)
        self.pred_mask_preview = tk.Label(
            pred_frame, bg="white",
            width=preview_size[0], height=preview_size[1]
        )
        self.pred_mask_preview.pack(expand=False, fill=None, padx=0, pady=0)
        pred_frame.pack_propagate(False)

        overlay_frame = tk.Frame(frame, width=preview_size[0], height=preview_size[1], bg="white")
        overlay_frame.grid_propagate(False)
        overlay_frame.grid(row=2, column=0, sticky="nsew", padx=0, pady=(5, 10))
        self.overlay_mask_preview = tk.Label(
            overlay_frame, bg="white",
            width=preview_size[0], height=preview_size[1]
        )
        self.overlay_mask_preview.pack(expand=False, fill=None, padx=0, pady=0)
        overlay_frame.pack_propagate(False)

        return frame

    def _create_right_frame(self):
        frame = ttk.Frame(self.window)
        frame.grid_rowconfigure(0, weight=3)
        frame.grid_rowconfigure(1, weight=2)
        frame.grid_columnconfigure(0, weight=1)

        # 上方：結果疊加顯示
        overlay_frame = ttk.LabelFrame(frame, text="結果疊加")
        overlay_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        # 修正：限制 overlay_preview 的最大尺寸且不允許自動擴張
        self.overlay_preview = tk.Label(overlay_frame, bg="white", width=self.GUI_CONFIG['display_size'][0], height=self.GUI_CONFIG['display_size'][1])
        self.overlay_preview.pack(expand=False, fill=None, padx=0, pady=0)
        overlay_frame.pack_propagate(False)  # 防止 frame 被內容自動撐大

        # 下方：評估指標
        metrics_frame = ttk.LabelFrame(frame, text="評估指標")
        metrics_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # 當前圖片的 Dice Score
        self.dice_label = ttk.Label(metrics_frame, text="This Dice Score: --", font=("Arial", 12))
        self.dice_label.pack(pady=5)
        
        # 平均 Dice Score
        self.mean_dice_label = ttk.Label(metrics_frame, text="Mean Dice Score: --", font=("Arial", 12))
        self.mean_dice_label.pack(pady=5)
        
        return frame

    def _on_mousewheel(self, event):
        try:
            if self.canvas.winfo_exists():
                self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except Exception:
            pass  # 控制元件已被銷毀，忽略錯誤

    def _create_image_item(self, img_path):
        try:
            item_frame = ttk.Frame(self.scrollable_frame, style="ImageItem.TFrame")
            # 修正：讓每個 item_frame 向右填滿
            item_frame.pack(fill=tk.X, expand=True, padx=2, pady=1)
            item_frame.path = img_path

            content_frame = ttk.Frame(item_frame, style="ImageItem.TFrame")
            # 修正：讓 content_frame 也向右填滿
            content_frame.pack(fill=tk.X, expand=True)
            
            # 載入圖片並創建縮圖
            image = Image.open(img_path).convert('RGB')
            thumb = image.copy()
            thumb.thumbnail(self.GUI_CONFIG['thumbnail_size'])
            photo = ImageTk.PhotoImage(thumb)
            
            # 建立圖片標籤
            img_label = ttk.Label(content_frame, image=photo, style="ImageItem.TLabel")
            img_label.image = photo
            img_label.pack(side=tk.LEFT, padx=2)
            
            # 建立檔名標籤，增加文字寬度限制
            filename = os.path.basename(img_path)
            name_label = ttk.Label(
                content_frame,
                text=filename,
                style="ImageItem.TLabel",
                wraplength=self.GUI_CONFIG['left_frame_width'] - 20  # 根據框架寬度動態設定
            )
            name_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            
            # 保存圖片快取
            self.image_cache[img_path] = photo
            
            # 綁定點擊事件
            for widget in (item_frame, content_frame, img_label, name_label):
                widget.bind('<Button-1>', lambda e, f=item_frame: self.on_image_select(f))
            
            self.image_items.append(item_frame)
            
        except Exception as e:
            print(f"Error creating item for {img_path}: {e}")

    def load_images(self):
        """載入測試集圖片並創建縮圖"""
        if not os.path.exists(self.test_image_dir):
            print(f"Error: Test directory does not exist: {self.test_image_dir}")
            return

        try:
            # 清空現有的圖片列表
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            
            self.image_items = []
            self.image_paths = []
            self.test_images = []
            
            # 直接遍歷測試資料夾中的所有檔案
            valid_extensions = ('.png', '.jpg', '.jpeg', '.bmp')
            valid_files = [f for f in sorted(os.listdir(self.test_image_dir)) 
                         if f.lower().endswith(valid_extensions)]
            
            # 只在初次載入時顯示找到的圖片數量
            if not hasattr(self, '_initialized'):
                print(f"找到 {len(valid_files)} 張圖片")
                self._initialized = True
            
            for filename in valid_files:
                img_path = os.path.join(self.test_image_dir, filename)
                if os.path.isfile(img_path):
                    try:
                        self.test_images.append(filename)
                        self.image_paths.append(img_path)
                        self._create_image_item(img_path)
                    except Exception as e:
                        print(f"無法載入圖片 {filename}")
            
            # 如果有圖片，選擇第一張
            if self.image_items:
                self.on_image_select(self.image_items[0])
            else:
                self.display_empty_state()
                
        except Exception as e:
            print(f"載入圖片過程發生錯誤")
            self.display_empty_state()

    def display_empty_state(self):
        """顯示初始空白狀態"""
        # 清空所有預覽區域，並維持遮罩視覺化區塊的寬高不變
        mask_disp_size = getattr(self, "_mask_preview_size", (240, 240))
        blank = ImageTk.PhotoImage(Image.new("RGB", mask_disp_size, (255, 255, 255)))
        if hasattr(self, "gt_mask_preview"):
            self.gt_mask_preview.configure(image=blank, width=mask_disp_size[0], height=mask_disp_size[1])
            self.gt_mask_preview.image = blank
        if hasattr(self, "pred_mask_preview"):
            self.pred_mask_preview.configure(image=blank, width=mask_disp_size[0], height=mask_disp_size[1])
            self.pred_mask_preview.image = blank
        if hasattr(self, "overlay_mask_preview"):
            self.overlay_mask_preview.configure(image=blank, width=mask_disp_size[0], height=mask_disp_size[1])
            self.overlay_mask_preview.image = blank
        # 右側大張疊加區域
        if hasattr(self, "overlay_preview"):
            blank_big = ImageTk.PhotoImage(Image.new("RGB", self.GUI_CONFIG['display_size'], (255, 255, 255)))
            self.overlay_preview.configure(image=blank_big)
            self.overlay_preview.image = blank_big
        # 兼容舊欄位
        if hasattr(self, "original_preview"):
            self.original_preview.configure(image='')
        if hasattr(self, "result_preview"):
            self.result_preview.configure(image='')

    def on_image_select(self, selected_frame):
        """處理圖片選擇事件"""
        if not selected_frame or not selected_frame.winfo_exists():
            return
            
        # 更新選擇狀態
        if self.selected_item and self.selected_item.winfo_exists():
            # 更新之前選中項目的樣式
            self._set_item_style(self.selected_item, False)
        
        # 更新新選中項目的樣式
        self._set_item_style(selected_frame, True)
        self.selected_item = selected_frame
        
        # 載入圖片但不顯示
        try:
            self.current_image = Image.open(selected_frame.path).convert('RGB')
        except Exception as e:
            print(f"Error loading selected image: {e}")

    def _set_item_style(self, item_frame, is_selected):
        """設定項目的視覺樣式"""
        style_suffix = "Selected.ImageItem" if is_selected else "ImageItem"
        
        def update_widget_style(widget):
            if isinstance(widget, ttk.Frame):
                widget.configure(style=f"{style_suffix}.TFrame")
            elif isinstance(widget, ttk.Label):
                widget.configure(style=f"{style_suffix}.TLabel")
            for child in widget.winfo_children():
                update_widget_style(child)
        
        update_widget_style(item_frame)

    def refine_mask(self, mask):
        """先保留最大連通區 → 形態學補洞與去雜訊 → floodFill補小洞 → 邊緣平滑"""
        mask = (mask > 0).astype(np.uint8)

        # 保留最大連通區塊
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num_labels <= 1:
            return mask
        largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        mask = (labels == largest_label).astype(np.uint8)

        # 形態學補洞（Close）+ 去雜訊（Open）
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (10, 10))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = (mask > 0).astype(np.uint8)

        # floodFill 補小洞（與背景不相連的內部洞）
        h, w = mask.shape[:2]
        mask_copy = mask.copy()
        floodfill_mask = np.zeros((h + 2, w + 2), np.uint8)
        cv2.floodFill(mask_copy, floodfill_mask, (0, 0), 1)  # 填背景為 1
        holes = (mask_copy == 0).astype(np.uint8)
        mask = mask | holes

        # 邊緣平滑
        blurred = cv2.GaussianBlur(mask.astype(np.float32), (25, 25), 0)
        _, smoothed = cv2.threshold(blurred, 0.5, 1, cv2.THRESH_BINARY)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (50, 50))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        blurred = cv2.GaussianBlur(mask.astype(np.float32), (25, 25), 0)
        _, smoothed = cv2.threshold(blurred, 0.5, 1, cv2.THRESH_BINARY)
        
        return smoothed.astype(np.uint8)

    def predict(self):
        """預測當前圖片"""
        # 修正：若沒有選中圖片或圖片列表為空則直接返回
        if self.current_image is None or self.selected_item is None or not self.image_items:
            return

        try: 
            current_item = self.selected_item
            with torch.no_grad():
                self.model.eval()
                transform = transforms.Compose([
                    transforms.Resize((512, 512)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
                ])
                image = transform(self.current_image).unsqueeze(0).to(self.device)
                output = self.model(image)
                # If output is a dict, get the tensor (commonly 'out' or 'mask')
                if isinstance(output, dict):
                    if 'out' in output:
                        output_tensor = output['out']
                    elif 'mask' in output:
                        output_tensor = output['mask']
                    else:
                        raise ValueError("Model output dict does not contain 'out' or 'mask' key.")
                else:
                    output_tensor = output
                pred_mask = torch.argmax(output_tensor, dim=1).squeeze().cpu().numpy()

            # 找到對應的遮罩
            img_dir = os.path.dirname(current_item.path)
            base_dir = os.path.dirname(img_dir)
            img_name = os.path.splitext(os.path.basename(current_item.path))[0] + '.png'
            mask_path = os.path.join(base_dir, "masks", img_name)

            true_mask = None
            if os.path.exists(mask_path):
                true_mask = np.array(Image.open(mask_path).convert('L')) > 128
                pred_mask_binary = pred_mask > 0
                pred_mask_binary = self.refine_mask(pred_mask_binary) # 形態學修正
                if true_mask.shape != pred_mask_binary.shape:
                    true_mask = cv2.resize(true_mask.astype(np.uint8), pred_mask_binary.shape[::-1]) > 0
                self.update_metrics(pred_mask_binary, true_mask)
            else:
                pred_mask_binary = pred_mask > 0
                # pred_mask_binary = self.refine_mask(pred_mask_binary)  # 沒有 true mask 也修正

            # 遮罩縮圖尺寸
            mask_disp_size = getattr(self, "_mask_preview_size", (180, 180))

            # 顯示原始遮罩(藍)
            gt_mask_img = np.zeros((512, 512, 3), dtype=np.uint8)
            if true_mask is not None:
                gt_mask = cv2.resize(true_mask.astype(np.uint8), (512, 512), interpolation=cv2.INTER_NEAREST)
                gt_mask_img[gt_mask == 1] = [0, 0, 255]
            gt_mask_pil = Image.fromarray(gt_mask_img).resize(mask_disp_size, Image.NEAREST)
            gt_mask_photo = ImageTk.PhotoImage(gt_mask_pil)
            self.gt_mask_preview.configure(image=gt_mask_photo, width=mask_disp_size[0], height=mask_disp_size[1])
            self.gt_mask_preview.image = gt_mask_photo

            # 顯示預測遮罩(綠)
            pred_mask_img = np.zeros((512, 512, 3), dtype=np.uint8)
            pred_mask_resized = cv2.resize(pred_mask_binary.astype(np.uint8), (512, 512), interpolation=cv2.INTER_NEAREST)
            pred_mask_img[pred_mask_resized == 1] = [0, 255, 0]
            pred_mask_pil = Image.fromarray(pred_mask_img).resize(mask_disp_size, Image.NEAREST)
            pred_mask_photo = ImageTk.PhotoImage(pred_mask_pil)
            self.pred_mask_preview.configure(image=pred_mask_photo, width=mask_disp_size[0], height=mask_disp_size[1])
            self.pred_mask_preview.image = pred_mask_photo

            # 疊加遮罩(藍在下(原始遮罩)、綠在上(預測遮罩)、綠超出藍的地方紅色)
            overlay_img = np.zeros((512, 512, 3), dtype=np.uint8)
            if true_mask is not None:
                gt = cv2.resize(true_mask.astype(np.uint8), (512, 512), interpolation=cv2.INTER_NEAREST)
            else:
                gt = np.zeros((512, 512), dtype=np.uint8)
            pred = pred_mask_resized

            # 藍底（原始遮罩）
            overlay_img[gt == 1] = [0, 0, 255]
            # 綠色覆蓋（預測遮罩）
            overlay_img[pred == 1] = [0, 255, 0]
            # 綠超出藍的地方紅色（預測有但原始沒有）
            only_pred = (pred == 1) & (gt == 0)
            overlay_img[only_pred] = [255, 0, 0]

            # 塞滿白格子（無padding）
            overlay_pil = Image.fromarray(overlay_img).resize(mask_disp_size, Image.NEAREST)
            overlay_photo = ImageTk.PhotoImage(overlay_pil)
            self.overlay_mask_preview.configure(
                image=overlay_photo,
                padx=0, pady=0,
                borderwidth=0,
                relief="flat"
            )
            self.overlay_mask_preview.image = overlay_photo

            # 顯示右側大張結果疊加（與舊版一致）
            overlay_img_full = np.array(self.current_image.resize(self.GUI_CONFIG['display_size']))
            mask_rgb = np.zeros_like(overlay_img_full)
            pred_mask_full = cv2.resize(pred_mask_binary.astype(np.uint8), self.GUI_CONFIG['display_size'][::-1], interpolation=cv2.INTER_NEAREST)
            mask_rgb[pred_mask_full == 1] = [0, 255, 0]
            alpha = 0.5
            overlay_array = cv2.addWeighted(overlay_img_full, 1, mask_rgb, alpha, 0)
            overlay_img_full_pil = Image.fromarray(overlay_array)
            overlay_photo_full = ImageTk.PhotoImage(overlay_img_full_pil)
            # 修正：設定 image 並強制寬高，避免自動撐大
            self.overlay_preview.configure(image=overlay_photo_full, width=self.GUI_CONFIG['display_size'][0], height=self.GUI_CONFIG['display_size'][1])
            self.overlay_preview.image = overlay_photo_full

            # 預測完移除左側圖片
            if current_item and current_item in self.image_items:
                idx = self.image_items.index(current_item)
                current_item.destroy()
                self.image_items.remove(current_item)
                self.image_paths.pop(idx)
                self.test_images.pop(idx)
                # 自動選擇下一張
                if self.image_items:
                    next_idx = min(idx, len(self.image_items) - 1)
                    self.on_image_select(self.image_items[next_idx])
                else:
                    self.selected_item = None

        except Exception as e:
            print(f"Error during prediction: {e}")
            messagebox.showerror("錯誤", f"預測過程發生錯誤：{str(e)}")

    def update_display(self, original_image):
        # 更新原始圖片
        display_img = original_image.resize((self.GUI_CONFIG['display_size']))
        photo = ImageTk.PhotoImage(display_img)
        self.original_preview.configure(image=photo)
        self.original_preview.image = photo

        # 進行預測
        transform = transforms.Compose([
            transforms.Resize(self.GUI_CONFIG['display_size']),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        input_tensor = transform(original_image).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            output = self.model(input_tensor)
            pred_mask = torch.argmax(output, dim=1).squeeze().cpu().numpy()

        # 更新預測結果
        result_img = Image.fromarray((pred_mask * 255).astype('uint8'))
        result_photo = ImageTk.PhotoImage(result_img)
        self.result_preview.configure(image=result_photo)
        self.result_preview.image = result_photo

        # 創建疊加效果
        overlay_img = original_image.copy().resize(self.GUI_CONFIG['display_size'])
        overlay_array = np.array(overlay_img)
        mask_rgb = np.zeros((*pred_mask.shape, 3), dtype=np.uint8)
        mask_rgb[pred_mask == 1] = [0, 255, 0]  # 使用綠色表示預測區域
        
        # 混合原始圖片和遮罩
        alpha = 0.5
        overlay_array = cv2.addWeighted(
            overlay_array, 1, mask_rgb, alpha, 0
        )
        
        overlay_img = Image.fromarray(overlay_array)
        overlay_photo = ImageTk.PhotoImage(overlay_img)
        self.overlay_preview.configure(image=overlay_photo)
        self.overlay_preview.image = overlay_photo

        # 更新評估指標
        # self.update_metrics(pred_mask, true_mask)

    def calculate_dice_score(self, pred_mask, true_mask):
        """計算 Dice Score"""
        intersection = np.logical_and(pred_mask == 1, true_mask == 1).sum()
        pred_sum = (pred_mask == 1).sum()
        true_sum = (true_mask == 1).sum()
        
        dice = (2.0 * intersection) / (pred_sum + true_sum) if (pred_sum + true_sum) > 0 else 0
        return dice

    def update_metrics(self, pred_mask, true_mask):
        """更新評估指標"""
        # 計算當前圖片的 Dice Score
        current_dice = self.calculate_dice_score(pred_mask, true_mask)
        
        # 更新總體指標
        self.metrics['total_dice'] += current_dice
        self.metrics['total_count'] += 1
        
        # 更新當前圖片的 Dice Score 顯示
        self.dice_label.config(text=f"This Dice Score: {current_dice:.4f}")
        
        # 更新平均 Dice Score 顯示
        mean_dice = self.metrics['total_dice'] / self.metrics['total_count']
        self.mean_dice_label.config(text=f"Mean Dice Score: {mean_dice:.4f}")

    def predict_all(self):
        """預測所有圖片"""
        for item in self.image_items[:]:
            self.on_image_select(item)
            self.predict()
            self.window.update()

    def reset_state(self):
        """重置視窗狀態"""
        self.current_image = None

        # 重置評估指標
        self.metrics = {
            'total_dice': 0,
            'total_count': 0,
        }

        # 重置指標顯示
        self.dice_label.config(text="This Dice Score: --")
        self.mean_dice_label.config(text="Mean Dice Score: --")

        # 清空左側圖片列表
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.image_items = []
        self.image_paths = []
        self.test_images = []

        # 清空預覽圖片並維持排版
        self.display_empty_state()

        # 重新載入圖片
        self.load_images()