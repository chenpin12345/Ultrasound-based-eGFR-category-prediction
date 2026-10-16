"""
test_gui.py - 統一測試GUI
支援三種模型的測試
"""
import os
import glob
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import pandas as pd
import numpy as np
from trainer import Config


class UnifiedTestGUI:
    """統一測試GUI"""
    
    def __init__(self, inference_pipeline, test_dir, metadata_path=None, model_type=None):
        self.inference_pipeline = inference_pipeline
        self.test_dir = os.path.abspath(test_dir)
        self.config = Config()
        self.model_type = model_type
        self.use_tta = False  # 預設關閉 TTA
        
        # 統計
        self.correct_count = 0
        self.total_count = 0
        self.confusion_matrix = np.zeros((self.config.class_num, self.config.class_num), dtype=int)
        
        # 資料
        self.image_cache = {}
        self.image_paths = []
        self.image_items = []
        self.selected_item = None
        
        # 載入metadata
        self.metadata_dict = self._load_metadata(metadata_path)
        
        # 創建GUI
        self.window = tk.Toplevel()
        self._create_gui()
        self.load_images()
    
    def _load_metadata(self, path):
        """載入metadata - 自動適配 Config.meta_cols"""
        if not path or not os.path.exists(path):
            print("⚠️  未提供metadata.csv")
            return {}
        
        try:
            df = pd.read_csv(path)
            
            # 從 Config 獲取 metadata 配置
            from trainer import Config
            meta_config = Config.get_metadata_config()
            required_cols = meta_config.meta_cols
            binary_cols = meta_config.binary_cols
            
            print(f"✓ 根據 Config 載入欄位: {required_cols}")
            
            # 檢查缺失欄位
            missing_cols = set(required_cols) - set(df.columns)
            if missing_cols:
                print(f"⚠️  CSV 缺少欄位: {missing_cols}")
                print(f"   這些欄位在推論時會使用預設值")
            
            metadata = {}
            
            for _, row in df.iterrows():
                meta_dict = {}
                
                # 自動處理所有 Config 定義的欄位
                for col in required_cols:
                    if col in df.columns:
                        value = row[col]
                        
                        # 使用 MetadataConfig 的預處理器
                        if col in meta_config.field_preprocessors:
                            # 有自訂預處理器 (如 gender)
                            meta_dict[col] = meta_config.field_preprocessors[col](value)
                        elif pd.isna(value):
                            # 缺失值 -> None (推論時用 fallback)
                            meta_dict[col] = None
                        elif col in binary_cols:
                            # 二元欄位: 轉為 float
                            meta_dict[col] = float(value)
                        else:
                            # 連續欄位: 保持浮點數精度
                            meta_dict[col] = float(value)
                    else:
                        # CSV 不存在此欄位 -> None
                        meta_dict[col] = None
                
                metadata[row['image_name']] = meta_dict
            
            print(f"✓ 載入 {len(metadata)} 筆 metadata (共 {len(required_cols)} 個欄位)")
            
            # 驗證: 檢查第一筆資料
            if metadata:
                first_key = list(metadata.keys())[0]
                sample = metadata[first_key]
                print(f"✓ 範例 ({first_key}):")
                for col in required_cols:
                    val = sample.get(col)
                    print(f"  {col}: {val} {'(binary)' if col in binary_cols else ''}")
            
            return metadata
            
        except Exception as e:
            import traceback
            print(f"❌ 載入 metadata 失敗: {e}")
            traceback.print_exc()
            return {}
    
    def _create_gui(self):
        """創建GUI"""
        self.window.title("統一測試視窗")
        self.window.geometry("1150x1100")
        
        # 配置樣式
        self.style = ttk.Style()
        self._configure_styles()
        
        # 主框架
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=3)
        self.window.grid_columnconfigure(1, weight=4)
        self.window.grid_columnconfigure(2, weight=4)
        
        # 三個區域
        self._create_image_list()
        self._create_control_panel()
        self._create_result_panel()
    
    def _configure_styles(self):
        """配置樣式"""
        styles = {
            "ImageItem.TFrame": {"padding": 5, "background": "white"},
            "Selected.ImageItem.TFrame": {"padding": 5, "background": "lightblue"},
            "Action.TButton": {"padding": (20, 10), "font": ("Arial", 12, "bold")},
            "Result.TLabel": {"font": ("Arial", 14, "bold"), "padding": (5, 2)}
        }
        for name, props in styles.items():
            self.style.configure(name, **props)
    
    def _create_image_list(self):
        """左側圖片列表"""
        frame = ttk.LabelFrame(self.window, text="圖片列表")
        frame.grid(row=0, column=0, padx=2, pady=2, sticky="nsew")
        
        container = ttk.Frame(frame)
        container.pack(fill=tk.BOTH, expand=True, padx=2)
        
        self.canvas = tk.Canvas(container, width=350)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas, width=350)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=350)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1*(e.delta//120), "units"))
    
    def _create_control_panel(self):
        """中間控制面板"""
        frame = ttk.LabelFrame(self.window, text="功能表")
        frame.grid(row=0, column=1, padx=2, pady=2, sticky="nsew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        container = ttk.Frame(frame)
        container.grid(row=0, column=0)
        
        self.tta_var = tk.BooleanVar(value=False)
        tta_checkbox = ttk.Checkbutton(
            container,
            text="使用 TTA (6x增強)",
            variable=self.tta_var,
            command=self._toggle_tta
        )
        tta_checkbox.pack(pady=5)

        buttons = [
            ("預測此圖片", self.predict_current),
            ("全部預測", self.predict_all),
            ("重置狀態", self.reset)
        ]
        
        for text, cmd in buttons:
            ttk.Button(
                container, text=text, command=cmd,
                style="Action.TButton", width=15
            ).pack(pady=12)
    
    def _create_result_panel(self):
        """右側結果顯示"""
        frame = ttk.LabelFrame(self.window, text="預測結果")
        frame.grid(row=0, column=2, padx=2, pady=2, sticky="nsew")
        frame.configure(width=420)
        frame.grid_propagate(False)
        
        frame.grid_rowconfigure(self.config.class_num, weight=1)
        
        # 圖片顯示
        display_frame = ttk.Frame(frame, width=350, height=350)
        display_frame.grid(row=0, column=0, padx=35, pady=(10, 5))
        display_frame.grid_propagate(False)
        
        self.display_label = tk.Label(display_frame, bg="white")
        self.display_label.place(relwidth=1, relheight=1)
        
        # 結果標籤
        self.result_label = ttk.Label(frame, font=("Arial", 14, "bold"))
        self.result_label.grid(row=1, column=0, padx=55, pady=2, sticky="w")
        
        # Metadata顯示
        self.meta_label = ttk.Label(frame, font=("Arial", 11))
        self.meta_label.grid(row=2, column=0, padx=55, pady=2, sticky="w")
        
        # 機率顯示
        prob_frame = ttk.Frame(frame)
        prob_frame.grid(row=3, column=0, padx=55, pady=2, sticky="w")
        
        self.entropy_label = ttk.Label(prob_frame, style="Result.TLabel")
        self.entropy_label.pack(anchor="w")
        
        self.prob_labels = []
        for i in range(self.config.class_num):
            label = ttk.Label(prob_frame, font=("Arial", 10))
            label.pack(anchor="w", pady=0)
            self.prob_labels.append(label)
        
        # 準確率
        self.accuracy_label = ttk.Label(frame, font=("Arial", 13, "bold"))
        self.accuracy_label.grid(row=4, column=0, padx=55, pady=2, sticky="w")
        
        # 混淆矩陣
        cm_frame = ttk.LabelFrame(frame, text="Confusion Matrix")
        cm_frame.grid(row=5, column=0, padx=10, pady=5, sticky="nsew")
        
        self.cm_canvas = tk.Canvas(cm_frame, bg="white")
        self.cm_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.draw_confusion_matrix()
    
    def load_images(self):
        """載入所有圖片"""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.image_items = []
        self.image_paths = []
        
        for class_dir in sorted(os.listdir(self.test_dir)):
            class_path = os.path.join(self.test_dir, class_dir)
            if not os.path.isdir(class_path):
                continue
            
            for img_path in glob.glob(os.path.join(class_path, "*.[jp][pn][g]")):
                try:
                    self._create_image_item(img_path, class_dir)
                    self.image_paths.append(img_path)
                except Exception as e:
                    print(f"載入失敗: {img_path} - {e}")
        
        if self.image_items:
            self.select_image(self.image_items[0])
    
    def _create_image_item(self, img_path, class_dir):
        """創建圖片項目"""
        item_frame = ttk.Frame(self.scrollable_frame, style="ImageItem.TFrame")
        item_frame.pack(fill=tk.X, padx=5, pady=2)
        item_frame.path = img_path
        
        # 縮圖
        image = Image.open(img_path).convert('RGB')
        thumb = image.copy()
        thumb.thumbnail((100, 100))
        photo = ImageTk.PhotoImage(thumb)
        self.image_cache[img_path] = photo
        
        img_label = tk.Label(item_frame, image=photo, bg="white")
        img_label.image = photo
        img_label.pack(side=tk.LEFT, padx=5)
        
        # 名稱
        name_label = tk.Label(
            item_frame,
            text=f"{class_dir}/{os.path.basename(img_path)}",
            wraplength=160,
            bg="white"
        )
        name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 綁定點擊
        for widget in (item_frame, img_label, name_label):
            widget.bind('<Button-1>', lambda e, f=item_frame: self.select_image(f))
        
        self.image_items.append(item_frame)
    
    def select_image(self, frame):
        """選擇圖片"""
        if not frame or not frame.winfo_exists():
            return
        
        if self.selected_item and self.selected_item.winfo_exists():
            self._update_item_style(self.selected_item, False)
        
        self._update_item_style(frame, True)
        self.selected_item = frame
        
        path = frame.path
        if path in self.image_paths:
            idx = self.image_paths.index(path)
            self.image_paths = [path] + self.image_paths[:idx] + self.image_paths[idx+1:]
    
    def _update_item_style(self, widget, selected):
        """更新項目樣式"""
        bg_color = "lightblue" if selected else "white"
        
        if isinstance(widget, ttk.Frame):
            widget.configure(style=f"{'Selected.' if selected else ''}ImageItem.TFrame")
        elif isinstance(widget, tk.Label):
            widget.configure(bg=bg_color)
        
        for child in widget.winfo_children():
            self._update_item_style(child, selected)
    
    def _toggle_tta(self):
        """切換 TTA 模式"""
        self.use_tta = self.tta_var.get()
        status = "已開啟" if self.use_tta else "已關閉"
        print(f"TTA 模式: {status}")

    def predict_current(self):
        """預測當前圖片"""
        if not self.image_paths:
            return False
        
        try:
            image_path = self.image_paths.pop(0)
            image = Image.open(image_path).convert('RGB')
            dir_name = os.path.basename(os.path.dirname(image_path))
            true_label = self.config.DIR_TO_CLASS[dir_name]
            fname = os.path.basename(image_path)
            meta = self.metadata_dict.get(fname)
            
            # 獲取 metadata 配置
            from trainer import Config
            meta_config = Config.get_metadata_config()
            
            fname = os.path.basename(image_path)
            meta = self.metadata_dict.get(fname)
            
            # ✨ 自動組裝所有 metadata 欄位（使用 ** 解包）
            metadata_kwargs = {}
            if meta:
                for col in meta_config.meta_cols:
                    if col in meta:
                        metadata_kwargs[col] = meta[col]

            if self.use_tta:
                # 使用 TTA 預測
                if self.model_type in ['ResNet', 'CoralResNet']:
                    pred_class, proba = self.inference_pipeline.predict_with_tta(image_path, **metadata_kwargs)
                    print(f"[{self.model_type}] TTA 推論: 8x增強平均")
                
                elif self.model_type in ['MLP', 'CoralMLP', 'XGBOOST', 'RF']:
                    pred_class, proba = self.inference_pipeline.predict_with_tta(
                        image_path, **metadata_kwargs
                    )
                    print(f"[{self.model_type}] TTA 推論: 8x增強平均")

                
                else:
                    raise Exception(f"❌ 不支援的模型類型: {self.model_type}")
            
            else:
                # 原始預測（不使用 TTA）
                if self.model_type in ['ResNet', 'CoralResNet', 'MNIST_ResNet']:
                    pred_class, proba = self.inference_pipeline.predict(image_path, **metadata_kwargs)

                elif self.model_type in ['MLP', 'CoralMLP', 'XGBOOST', 'RF']:
                    pred_class, proba = self.inference_pipeline.predict(
                        image_path, **metadata_kwargs
                    )
                
                else:
                    raise Exception(f"❌ 不支援的模型類型: {self.model_type}")
            
            # 計算損失和更新統計
            loss = -np.log(proba[true_label] + 1e-10)
            self.confusion_matrix[true_label][pred_class] += 1
            self.total_count += 1
            if pred_class == true_label:
                self.correct_count += 1
            
            # 更新顯示
            self._update_display(
                image,
                self.config.CLASS_NAMES[true_label],
                self.config.CLASS_NAMES[pred_class],
                proba,
                loss,
                meta
            )
            
            self._remove_item(image_path)
            self.draw_confusion_matrix()
            if self.image_items:
                self.select_image(self.image_items[0])
            
            return True
        
        except Exception as e:
            print(f"❌ 預測失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def predict_all(self):
        """全部預測"""
        while self.predict_current():
            self.window.update()
        
        # 預測完成後輸出統計資訊
        self._print_metrics()
    
    def reset(self):
        """重置狀態"""
        self.correct_count = 0
        self.total_count = 0
        self.confusion_matrix = np.zeros((self.config.class_num, self.config.class_num), dtype=int)
        self.load_images()
        self.display_label.configure(image='')
        self.result_label.config(text='')
        self.meta_label.config(text='')
        self.entropy_label.config(text='')
        for label in self.prob_labels:
            label.config(text='')
        self.accuracy_label.config(text='')
        self.draw_confusion_matrix()
    
    def _update_display(self, image, true_label, pred_label, probs, loss, meta):
        """更新顯示"""
        # 顯示圖片
        display_img = image.resize((350, 350))
        photo = ImageTk.PhotoImage(display_img)
        self.display_label.configure(image=photo)
        self.display_label.image = photo
        
        # 結果
        self.result_label.config(
            text=f"True: {true_label} | Pred: {pred_label}",
            foreground="green" if true_label == pred_label else "red"
        )
        
        # Metadata
        if not meta:
            self.meta_label.config(text="無 Metadata")
        else:
            text=""
            if 'age' in meta:
                text += f"年齡: {meta['age']} 歲 | "
            if 'gender' in meta:
                text += f"性別: {meta['gender']}"
            self.meta_label.config(text=text.strip(" | "))

        # 損失
        self.entropy_label.config(text=f"Loss: {loss:.4f}")

        # 機率
        max_prob = np.max(probs)
        for i, (prob, label) in enumerate(zip(probs, self.prob_labels)):
            label.configure(
                text=f"{self.config.CLASS_NAMES[i]}: {prob:.4f}",
                foreground="green" if (i == list(self.config.CLASS_NAMES.keys())[list(self.config.CLASS_NAMES.values()).index(pred_label)] and true_label == pred_label) else
                          "red" if prob == max_prob else "#666666"
            )
        
        # 準確率
        acc = self.correct_count / self.total_count * 100 if self.total_count > 0 else 0
        self.accuracy_label.config(
            text=f"Accuracy: {self.correct_count}/{self.total_count} ({acc:.2f}%)"
        )
    
    def _remove_item(self, path):
        """移除項目"""
        for item in self.image_items[:]:
            if item.path == path:
                item.destroy()
                self.image_items.remove(item)
                break
    
    def draw_confusion_matrix(self):
        """繪製混淆矩陣"""
        self.cm_canvas.delete("all")
        self.cm_canvas.update()
        
        w = self.cm_canvas.winfo_width()
        h = self.cm_canvas.winfo_height()
        margin = 60
        
        cell_size = min((w - margin) / self.config.class_num, (h - margin) / self.config.class_num)
        start_x = margin + (w - margin - cell_size * self.config.class_num) / 2
        start_y = margin + (h - margin - cell_size * self.config.class_num) / 2
        
        # 標題
        middle=self.config.class_num / 2
        self.cm_canvas.create_text(
            start_x + cell_size * middle, start_y - 35,
            text="Predicted", font=("Arial", 11, "bold")
        )
        self.cm_canvas.create_text(
            start_x - 40, start_y + cell_size * middle,
            text="True", font=("Arial", 11, "bold"), angle=90
        )
        
        # 繪製矩陣
        max_val = np.max(self.confusion_matrix) if np.max(self.confusion_matrix) > 0 else 1
        
        for i in range(self.config.class_num):
            self.cm_canvas.create_text(
                start_x - 15, start_y + i * cell_size + cell_size / 2,
                text=self.config.CLASS_SHORT[i], font=("Arial", 9)
            )
            
            for j in range(self.config.class_num):
                if i == 0:
                    self.cm_canvas.create_text(
                        start_x + j * cell_size + cell_size / 2, start_y - 15,
                        text=self.config.CLASS_SHORT[j], font=("Arial", 9)
                    )
                
                x1, y1 = start_x + j * cell_size, start_y + i * cell_size
                x2, y2 = x1 + cell_size, y1 + cell_size
                
                value = self.confusion_matrix[i][j]
                
                if value > 0:
                    intensity = int(255 * (1 - value / max_val * 0.7))
                    color = f"#{intensity:02x}{intensity:02x}ff" if i == j else f"#ff{intensity:02x}{intensity:02x}"
                else:
                    color = "white"
                
                self.cm_canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="gray")
                self.cm_canvas.create_text(
                    x1 + cell_size / 2, y1 + cell_size / 2,
                    text=str(value), font=("Arial", 10, "bold"),
                    fill="black" if value < max_val * 0.5 else "white"
                )
    
    def _print_metrics(self):
        """計算並輸出每類的 precision, recall, F1"""
        print("\n" + "="*60)
        print("預測完成 - 分類指標")
        print("="*60)
        
        for i in range(self.config.class_num):
            class_name = self.config.CLASS_NAMES[i]
            
            # TP: 真實為i且預測為i
            tp = self.confusion_matrix[i][i]
            
            # FP: 真實不為i但預測為i (該列的總和，不包括對角線)
            fp = np.sum(self.confusion_matrix[:, i]) - tp
            
            # FN: 真實為i但預測不為i (該行的總和，不包括對角線)
            fn = np.sum(self.confusion_matrix[i, :]) - tp
            
            # 計算指標
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            
            print(f"\n{class_name}:")
            print(f"  Precision: {precision:.4f}")
            print(f"  Recall:    {recall:.4f}")
            print(f"  F1-Score:  {f1:.4f}")
        
        # 總體準確率
        total_accuracy = self.correct_count / self.total_count if self.total_count > 0 else 0.0
        print(f"\n{'─'*60}")
        print(f"Overall Accuracy: {total_accuracy:.4f} ({self.correct_count}/{self.total_count})")
        print("="*60 + "\n")


# ==================== 啟動函數 ====================
def launch_test_gui(inference_pipeline, test_dir, metadata_path=None, model_type=None):
    """啟動測試GUI"""
    gui = UnifiedTestGUI(inference_pipeline, test_dir, metadata_path, model_type)
    return gui