import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import traceback
from image_RB import process_folder as process_rb
from auto_assort import process_folder as process_assort
from auto_mask import process_folder as process_mask
from batch_crop import process_folder as process_crop
from format_converter import process_folder as process_convert, count_files
from image_stats import ImageStats
from image_enhance import process_folder as process_enhance

SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.jfif'}

class ImageProcessorGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("圖片處理工具")
        self.window.geometry("700x600")
        
        # 初始化進度條相關屬性
        self.progress_bar = None
        self.status_label = None
        self.total_files = 0
        self.processed_files = 0
        self.message_timer = None
        
        # 設定主題樣式
        self.style = ttk.Style()
        self._configure_styles()
        
        self.setup_ui()
        self.stats = ImageStats()

    def _configure_styles(self):
        """配置所有按鈕樣式"""
        # 基本按鈕樣式
        self.style.configure('Custom.TButton',
                           padding=10,
                           font=('微軟正黑體', 12, 'bold'),
                           width=20,
                           relief='raised',
                           borderwidth=3)
        
        self.style.map('Custom.TButton',
                      foreground=[('pressed', '#000066'), 
                                ('active', '#000099'),
                                ('!disabled', '#000033')],
                      background=[('pressed', '#99CCFF'), 
                                ('active', '#CCE5FF'),
                                ('!disabled', '#E6F3FF')],
                      relief=[('pressed', 'sunken'),
                             ('!pressed', 'raised')],
                      borderwidth=[('pressed', 2),
                                 ('!pressed', 3)])

        # 狀態標籤樣式
        self.style.configure('success.TLabel', 
                           foreground='#2E7D32',
                           font=('微軟正黑體', 12))
        self.style.configure('error.TLabel', 
                           foreground='#C62828',
                           font=('微軟正黑體', 12))
        self.style.configure('info.TLabel', 
                           foreground='#1565C0',
                           font=('微軟正黑體', 12))

        # 功能按鈕的獨特樣式
        button_styles = {
            'crop.TButton': {'background': '#81C784', 'hover': '#66BB6A', 'pressed': '#4CAF50'},
            'rb.TButton': {'background': '#4FC3F7', 'hover': '#29B6F6', 'pressed': '#03A9F4'},
            'assort.TButton': {'background': '#BA68C8', 'hover': '#AB47BC', 'pressed': '#9C27B0'},
            'mask.TButton': {'background': '#FFB74D', 'hover': '#FFA726', 'pressed': '#FF9800'},
            'convert.TButton': {'background': '#FF7043', 'hover': '#FF5722', 'pressed': '#E64A19'},
            'enhance.TButton': {'background': '#64B5F6', 'hover': '#42A5F5', 'pressed': '#2196F3'}
        }
        
        for style_name, colors in button_styles.items():
            self.style.configure(style_name,
                               padding=10,
                               font=('微軟正黑體', 12, 'bold'),
                               width=20,
                               background=colors['background'])
            self.style.map(style_name,
                         background=[('active', colors['hover']),
                                   ('pressed', colors['pressed'])],
                         relief=[('pressed', 'sunken')])

    def setup_ui(self):
        """建立使用者介面"""
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # 標題
        title_label = ttk.Label(main_frame, 
                              text="圖片處理工具", 
                              font=('微軟正黑體', 24, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=20)
        
        # 按鈕框架
        button_frame = ttk.Frame(main_frame, padding="10")
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        # 主要功能按鈕 (4 row x 2 col)
        buttons = [
            ("批次裁切", self.run_batch_crop, 'crop.TButton', 0, 0),
            ("藍線去除", self.run_rb_process, 'rb.TButton', 0, 1),
            ("遮罩生成", self.run_mask_generator, 'mask.TButton', 1, 0),
            ("圖片分類", self.run_assort, 'assort.TButton', 1, 1),
            ("去噪增強", self.run_image_enhance, 'enhance.TButton', 2, 0),
            ("格式轉換 (JFIF→JPG)", self.run_jfif_converter, 'convert.TButton', 2, 1),
        ]

        for text, command, style, row, col in buttons:
            btn = ttk.Button(button_frame, text=text, command=command, style=style)
            btn.grid(row=row, column=col, pady=12, padx=10, sticky='ew')

        # 說明與統計按鈕 (放在第 3 行，2 列)
        help_btn = ttk.Button(button_frame, text="使用說明", 
                             command=self.run_help, style='Custom.TButton')
        help_btn.grid(row=3, column=0, pady=(35, 0), padx=10, sticky='ew')

        stats_btn = ttk.Button(button_frame, text="統計報告", 
                              command=self.run_stats, style='Custom.TButton')
        stats_btn.grid(row=3, column=1, pady=(35, 0), padx=10, sticky='ew')

        # 狀態顯示區域
        status_frame = ttk.Frame(main_frame, padding="10")
        status_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky='ew')
        
        self.status_label = ttk.Label(status_frame, text="", style='info.TLabel')
        self.status_label.pack(pady=5)
        
        self.progress_bar = ttk.Progressbar(status_frame, length=300, mode='indeterminate')
        self.progress_bar.pack(pady=5)
        self.progress_bar.pack_forget()

    def create_progress_window(self):
        """顯示進度條"""
        if self.progress_bar:
            self.progress_bar.stop()
            self.progress_bar["mode"] = "determinate"
            self.progress_bar["value"] = 0
        self.status_label.config(text="正在處理圖片...")
        self.progress_bar.pack(pady=5)
        self.window.update()

    def update_progress(self):
        """更新進度條"""
        if self.total_files > 0:
            progress = (self.processed_files / self.total_files) * 100
            self.progress_bar["value"] = progress
            self.status_label.config(
                text=f"處理進度: {progress:.1f}% ({self.processed_files}/{self.total_files})"
            )
            self.window.update()

    def close_progress_window(self):
        """關閉進度條"""
        if self.progress_bar:
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            self.status_label.config(text="")
            self.window.update()

    def show_status_message(self, message, style='info'):
        """顯示狀態訊息（5秒後自動消失）"""
        if self.message_timer:
            self.window.after_cancel(self.message_timer)
        
        self.status_label.config(text=message, style=f'{style}.TLabel')
        
        def reset_status():
            self.status_label.config(text="", style='info.TLabel')
            self.message_timer = None
            
        self.message_timer = self.window.after(5000, reset_status)

    def process_with_progress(self, process_func, folder, process_subdirs, output_dir):
        """統一的處理流程（含進度顯示）"""
        try:
            # 計算總檔案數 
            if process_func == process_convert:
                self.total_files = count_files(folder)
            else:
                self.total_files = sum(
                    1 for path in folder.rglob("*") 
                    if path.is_file()
                    and path.suffix.lower() in SUPPORTED_FORMATS
                    and not any('移出圖片' in p.parts for p in path.parents)
                    and not (process_func == process_enhance and path.suffix.lower() == '.png')  # ← 新增這行
                )

            
            self.processed_files = 0
            self.create_progress_window()
            
            def update_callback(idx=None, total=None):
                self.processed_files += 1
                self.update_progress()
                
            # 根據不同函數調用相應的處理方式
            if process_func == process_rb:
                base_output_dir = folder.parent / output_dir
                base_output_dir.mkdir(parents=True, exist_ok=True)
                result = process_func(folder, base_output_dir, update_callback)
            elif process_func in [process_crop, process_convert]:
                result = process_func(folder, update_callback)
            else:
                result = process_func(folder, update_callback)
            
            self.close_progress_window()
            
            # 處理回傳結果並顯示狀態
            if result:
                if isinstance(result, tuple) and len(result) == 3:
                    success, failure, error_files = result
                else:
                    success, failure = result
                
                if failure == 0:
                    self.show_status_message(f"✅ 完成！成功處理 {success} 張圖片", 'success')
                else:
                    status_text = f"⚠️ 完成 (成功:{success} 失敗:{failure})"
                    style = 'error' if failure > success else 'info'
                    self.show_status_message(status_text, style)
            
            return result
            
        except Exception as e:
            self.close_progress_window()
            self.show_status_message("處理過程發生錯誤", 'error')
            traceback.print_exc()
            return None

    def select_folder(self):
        """選擇資料夾並詢問是否處理子資料夾"""
        folder_path = filedialog.askdirectory(title="選擇要處理的圖片資料夾")
        if not folder_path:
            return None
        
        folder = Path(folder_path)
        if not folder.exists():
            return None

        confirm_dialog = tk.Toplevel(self.window)
        confirm_dialog.title("確認")
        confirm_dialog.grab_set()
        confirm_dialog.resizable(False, False)
        confirm_dialog.geometry(
            "+%d+%d" % (self.window.winfo_rootx()+200, self.window.winfo_rooty()+200)
        )

        result = {"value": None}

        def on_yes():
            result["value"] = True
            confirm_dialog.destroy()

        def on_no():
            result["value"] = False
            confirm_dialog.destroy()

        def on_close():
            result["value"] = None
            confirm_dialog.destroy()

        label = ttk.Label(
            confirm_dialog, 
            text="是否處理所有子資料夾中的圖片？\n\n選擇「是」將處理所有子資料夾\n選擇「否」只處理選擇的資料夾", 
            padding=20
        )
        label.pack()
        btn_frame = ttk.Frame(confirm_dialog)
        btn_frame.pack(pady=10) 
        yes_btn = ttk.Button(btn_frame, text="是", command=on_yes)
        yes_btn.pack(side=tk.LEFT, padx=10)
        no_btn = ttk.Button(btn_frame, text="否", command=on_no)
        no_btn.pack(side=tk.LEFT, padx=10)
        confirm_dialog.protocol("WM_DELETE_WINDOW", on_close)
        confirm_dialog.wait_window()

        if result["value"] is None:
            return None
        return (folder, result["value"])

    def run_jfif_converter(self):
        """執行 JFIF 到 JPG 的轉換"""
        result = self.select_folder()
        if not result:
            return
            
        folder, process_subdirs = result
        jfif_count = count_files(folder)
        
        if jfif_count == 0:
            self.show_status_message("未找到 .jfif 檔案", 'info')
            messagebox.showinfo("提示", "在選擇的資料夾中未找到任何 .jfif 檔案")
            return
        
        confirm = messagebox.askyesno(
            "確認轉換", 
            f"找到 {jfif_count} 個 JFIF 檔案\n\n轉換後將刪除原始 .jfif 檔案\n是否繼續？"
        )
        
        if not confirm:
            self.show_status_message("已取消轉換", 'info')
            return
        
        result = self.process_with_progress(process_convert, folder, process_subdirs, None)
        
        if result and result[1] > 0:  # result[1] 是 failure 數量
            success, failure, error_files = result
            error_msg = f"成功: {success}\n失敗: {failure}\n\n失敗的檔案:\n"
            for file, error in error_files[:5]:
                error_msg += f"- {Path(file).name}: {error}\n"
            if len(error_files) > 5:
                error_msg += f"\n... 還有 {len(error_files)-5} 個錯誤"
            
            messagebox.showwarning("轉換結果", error_msg)

    def run_rb_process(self):
        """執行藍線去除"""
        result = self.select_folder()
        if result:
            folder, process_subdirs = result
            self.process_with_progress(process_rb, folder, process_subdirs, "IMG_RB")

    def run_assort(self):
        """執行圖片分類"""
        result = self.select_folder()
        if result:
            folder, process_subdirs = result
            results = self.process_with_progress(process_assort, folder, process_subdirs, "IMG_train")
            
            if results:
                method1_summary, method2_summary = results
                summary_message = "方法一分配結果:\n" + "\n".join(method1_summary) + "\n\n"
                summary_message += "方法二分配結果:\n" + "\n".join(method2_summary)
                messagebox.showinfo("分類結果統計", summary_message)

    def run_mask_generator(self):
        """執行遮罩生成"""
        result = self.select_folder()
        if result:
            folder, process_subdirs = result
            self.process_with_progress(process_mask, folder, process_subdirs, "IMG_Mask")

    def run_batch_crop(self):
        """執行批次裁切"""
        result = self.select_folder()
        if result:
            folder, process_subdirs = result
            self.process_with_progress(process_crop, folder, process_subdirs, "IMG_Cut")
    
    def run_image_enhance(self):
        result = self.select_folder()
        if not result:
            return
        
        folder, process_subdirs = result
        
        # 建立選擇方法的彈窗
        method_window = tk.Toplevel(self.window)
        method_window.title("選擇增強方法")
        method_window.grab_set()
        method_window.resizable(False, False)
        method_window.geometry("+%d+%d" % (self.window.winfo_rootx()+200, self.window.winfo_rooty()+200))
        
        method_var = tk.StringVar(value="srad")  # 預設值
        
        ttk.Label(method_window, text="請選擇圖片增強方法：", font=('微軟正黑體', 12)).pack(padx=20, pady=10)
        ttk.Radiobutton(method_window, text="SRAD", variable=method_var, value="srad").pack(anchor='w', padx=20)
        ttk.Radiobutton(method_window, text="小波 (Wavelet)", variable=method_var, value="wavelet").pack(anchor='w', padx=20)
        ttk.Radiobutton(method_window, text="SRAD+小波", variable=method_var, value="both").pack(anchor='w', padx=20)
        ttk.Radiobutton(method_window, text="不去噪", variable=method_var, value="none").pack(anchor='w', padx=20)
        
        def on_confirm():
            method = method_var.get()
            method_window.destroy()
            # 設定預設參數（可根據 image_enhance.py 的預設值調整）
            params = {
                'denoise_method': method,
                'num_iter': 10,
                'delta_t': 0.04,
                'decay_factor': 1.5,
                'wavelet_type': 'db4',
                'wavelet_level': 3,
                'wavelet_threshold': 1.0,
                'clip_limit': 1.5,
                'sharpen_amount': 0.2,
                'gamma': 0.98,
                'use_second_clahe': True,
                'use_srad': method in ['srad', 'both'],
                'use_wavelet': method in ['wavelet', 'both']
            }
            self.process_with_progress(
                lambda f, cb: process_enhance(f, cb, params=params),
                folder, process_subdirs, None
            )
        
        ttk.Button(method_window, text="確認", command=on_confirm).pack(pady=15)
        method_window.protocol("WM_DELETE_WINDOW", method_window.destroy)


    def run_stats(self):
        """執行統計功能"""
        self.stats.run_stats_gui(self.window)

    def run_help(self):
        """顯示使用說明"""
        self.stats.show_help_dialog(self.window)

if __name__ == "__main__":
    app = ImageProcessorGUI()
    app.window.mainloop()