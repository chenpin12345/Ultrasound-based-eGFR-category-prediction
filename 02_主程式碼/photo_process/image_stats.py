from pathlib import Path
from collections import defaultdict
from datetime import datetime

class ImageStats:
    def __init__(self):
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.jfif'}

    def count_images(self, folder_path: Path) -> dict:
        """統計資料夾中的圖片數量"""
        stats = defaultdict(int)
        if not folder_path.exists():
            return stats
        for file in folder_path.rglob('*'):
            if file.is_file() and file.suffix.lower() in self.supported_formats:
                stats[file.suffix.lower()] += 1
        return dict(stats)

    def get_img_root(self) -> Path:
        """自動尋找與photo_process同層的IMG資料夾"""
        current = Path(__file__).resolve()
        photo_process_dir = current.parent
        img_dir = photo_process_dir.parent / "IMG"
        return img_dir

    def get_folder_stats(self) -> dict:
        """分析IMG資料夾下四個功能資料夾的分布"""
        img_root = self.get_img_root()
        folders = {
            'rb_processed': img_root / "IMG_RB",
            'assorted': img_root / "IMG_train",
            'masked': img_root / "IMG_Mask",
            'cropped': img_root / "IMG_Cut"
        }
        stats = {}
        for folder_type, folder_path in folders.items():
            stats[folder_type] = {
                'path': str(folder_path),
                'exists': folder_path.exists(),
                'counts': self.count_images(folder_path) if folder_path.exists() else {},
                'total': sum(self.count_images(folder_path).values()) if folder_path.exists() else 0,
                'subfolders': self.analyze_subfolders(folder_path) if folder_path.exists() else {}
            }
        return stats

    def analyze_subfolders(self, folder_path: Path) -> dict:
        """遞迴分析子資料夾的圖片分布"""
        result = {}
        for sub in folder_path.iterdir():
            if sub.is_dir():
                result[sub.name] = {
                    'counts': self.count_images(sub),
                    'total': sum(self.count_images(sub).values())
                }
        return result

    def generate_report(self) -> str:
        """生成統計報告"""
        stats = self.get_folder_stats()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = f"IMG資料夾統計報告 (生成時間: {timestamp})\n"
        folder_names = {
            'rb_processed': '● 藍線去除(RB)',
            'assorted': '● 分類結果(train)',
            'masked': '● 遮罩生成(Mask)',
            'cropped': '● 裁切結果(Cut)'
        }
        for folder_type, data in stats.items():
            folder_name = folder_names.get(folder_type, folder_type)
            report += f"{folder_name}\n"
            report += f"路徑: {data['path']}\n"
            if data['exists']:
                report += f"▲ 總計: {data['total']} 張圖片\n"
                if data['counts']:
                    report += "▲ 分布:\n"
                    for ext, count in data['counts'].items():
                        report += f"  {ext} {count} 張\n"
                # 子資料夾分析
                if data['subfolders']:
                    report += "子資料夾分布:\n"
                    for sub_name, sub_data in data['subfolders'].items():
                        report += f"  {sub_name}: {sub_data['total']} 張"
                        if sub_data['counts']:
                            report += " ("
                            report += ", ".join(f"{ext}:{cnt}" for ext, cnt in sub_data['counts'].items())
                            report += ")"
                        report += "\n"
            else:
                report += "資料夾不存在\n"
            report += "\n"
        return report

    def run_stats_gui(self, parent_window):
        """顯示統計報告（兩兩並排區塊）"""
        import tkinter as tk
        from tkinter import ttk

        try:
            report = self.generate_report()
            lines = report.splitlines()
            # 修正：正確分割四個 section，忽略空行、分隔線與標題
            sections = []
            current_section = []
            for line in lines:
                # 跳過標題與分隔線
                if not line.strip() or set(line.strip()) == {"="} or "IMG資料夾統計報告" in line or "生成時間" in line:
                    continue
                if any(x in line for x in ["藍線去除", "分類結果", "遮罩生成", "裁切結果"]):
                    if current_section:
                        sections.append(current_section)
                        current_section = []
                current_section.append(line)
            if current_section:
                sections.append(current_section)
            # sections: [RB, train, Mask, Cut]

            # 建立新視窗
            report_window = tk.Toplevel(parent_window)
            report_window.title("圖片統計報告")
            report_window.geometry("1000x800")

            # 主框架
            main_frame = ttk.Frame(report_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # 標題
            title_label = ttk.Label(main_frame, text=lines[0], font=('微軟正黑體', 16, 'bold'), foreground='#1565C0')
            title_label.pack(pady=(0, 10))

            # 兩行，每行兩個區塊
            grid_frame = ttk.Frame(main_frame)
            grid_frame.pack(fill=tk.BOTH, expand=True)

            for row in range(2):
                for col in range(2):
                    idx = row * 2 + col
                    if idx >= len(sections):
                        continue
                    section = sections[idx]
                    section_frame = ttk.LabelFrame(
                        grid_frame,
                        text="",
                        labelanchor='n',
                        padding=10,
                        style='section.TLabelframe'
                    )
                    section_frame.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')
                    grid_frame.grid_columnconfigure(col, weight=1)
                    grid_frame.grid_rowconfigure(row, weight=1)

                    # 內容用Text顯示
                    text_area = tk.Text(section_frame, wrap=tk.WORD, font=('微軟正黑體', 12), height=14, width=40, bd=0, highlightthickness=0)
                    text_area.pack(fill=tk.BOTH, expand=True)
                    # 設定tag樣式
                    text_area.tag_configure('section', font=('微軟正黑體', 20, 'bold'), foreground='#2E7D32')
                    text_area.tag_configure('path', font=('微軟正黑體', 10, 'italic'), foreground='#616161')
                    text_area.tag_configure('total', font=('微軟正黑體', 12, 'bold'), foreground='#C62828')
                    text_area.tag_configure('format', font=('微軟正黑體', 12), foreground='#1565C0')
                    text_area.tag_configure('subfolder', font=('微軟正黑體', 12, 'bold'), foreground='#6A1B9A')
                    text_area.tag_configure('normal', font=('微軟正黑體', 12), foreground='#222222')

                    # 將section標題插入文字框
                    text_area.insert(tk.END, section[0] + "\n", 'section')

                    for line in section[1:]:
                        if line.startswith("路徑:"):
                            text_area.insert(tk.END, line + "\n", 'path')
                        elif line.startswith("▲ 總計:"):
                            text_area.insert(tk.END, line + "\n", 'total')
                        elif line.startswith("▲ 分布:"):
                            text_area.insert(tk.END, line , 'total')
                        elif line.startswith("  ."):
                            text_area.insert(tk.END, line, 'total')
                        elif line.startswith("子資料夾分布:"):
                            text_area.insert(tk.END, "\n\n" + line + "\n", 'subfolder')
                        elif line.startswith("  ") and ":" in line:
                            text_area.insert(tk.END, line + "\n", 'subfolder')
                        elif "不存在" in line:
                            text_area.insert(tk.END, line + "\n", 'total')
                        elif line.strip() == "":
                            text_area.insert(tk.END, "\n", 'normal')
                        else:
                            text_area.insert(tk.END, line + "\n", 'normal')
                    text_area.config(state=tk.DISABLED)
        except Exception as e:
            import traceback
            print(f"統計報告生成失敗: {str(e)}")
            traceback.print_exc()

    def show_help_dialog(self, parent_window):
        import tkinter as tk
        from tkinter import ttk

        help_text_lines = [
            "【圖片處理工具使用說明】",
            "",
            "★功能介紹★",
            "1.批次裁切：將圖片裁切為指定區域，結果存於 IMG/IMG_Cut。",
            "2.藍線去除：去除圖片中的藍色線條，結果存於 IMG/IMG_RB。",
            "3.遮罩生成：偵測藍十字並產生遮罩，結果存於 IMG/IMG_Mask。",
            "4.圖片分類：分配訓練/驗證/測試集，結果存於 IMG/IMG_train。",
            "5.去噪增強：對選取資料夾裡所有圖片增強, 結果會自動覆蓋回去。",
            "6.格式轉換：對選取資料夾裡所有圖片轉換, 結果會自動覆蓋回去。",
            "7.統計報告：分析各功能資料夾下圖片數量與分布。",
            "",
            "★操作流程★",
            "請依序選擇功能，選擇來源資料夾，並依提示操作。",
            "1. 將原始圖片放入 IMG_Original 資料夾。",
            "2. 點擊批次裁切，並選擇 IMG_Original 資料夾。",
            "3. 點擊藍線去除，並選擇 IMG_Cut 資料夾。",
            "4. 點擊遮罩生成，並選擇 IMG_Cut 資料夾。",
            "5. 點擊圖片分類，依據需求選擇 IMG_Cut 或 IMG_RB 資料夾。",
            "6. 點擊統計報告，查看各功能資料夾下圖片數量與分布。",
            "",
            "(可選)點擊去噪增強，並對選取資料夾裡做增強(SRAD+CLAHE)。",
            "(可選)點擊格式轉換，並對選取資料夾裡做轉換(jfif->jpg)。",
            "",
            "★注意事項★",
            "1. 請確保圖片格式為 jpg、jpeg、png、bmp、gif、webp、jfif(須轉檔)。"
        ]

        help_win = tk.Toplevel(parent_window)
        help_win.title("使用說明")
        help_win.geometry("520x560")
        help_win.resizable(False, False)
        frame = ttk.Frame(help_win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(frame, wrap=tk.WORD, font=('微軟正黑體', 12), height=18, width=50)
        text.pack(fill=tk.BOTH, expand=True)

        # 設定tag樣式
        text.tag_configure('title', foreground='#C62828', font=('微軟正黑體', 18, 'bold'))
        text.tag_configure('section', foreground='#1565C0', font=('微軟正黑體', 15, 'bold'))
        text.tag_configure('normal', font=('微軟正黑體', 12), foreground='#222222')

        for line in help_text_lines:
            if line.startswith("【圖片處理工具使用說明】"):
                text.insert(tk.END, line + "\n", 'title')
            elif line.startswith("★功能介紹★") or line.startswith("★操作流程★") or line.startswith("★注意事項★"):
                text.insert(tk.END, line + "\n", 'section')
            else:
                text.insert(tk.END, line + "\n", 'normal')

        text.config(state=tk.DISABLED)
        ok_btn = ttk.Button(frame, text="關閉", command=help_win.destroy)
        ok_btn.pack(pady=10)
