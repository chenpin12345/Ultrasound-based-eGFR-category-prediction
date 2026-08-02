import os
import shutil
import random
import traceback
from pathlib import Path
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox

SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')


# -------------------- 方法一: Segmentation --------------------
def generate_dataset_segmentation(input_dir, k=5, test_ratio=0.15):
    """先抽 external test，再做 K-fold (Segmentation)"""
    
    mask_dir = input_dir.parent / "IMG_Mask"
    
    # --- Step 1: collect all images ---
    all_imgs = [f for f in input_dir.rglob("*.*") if f.suffix.lower() in SUPPORTED_FORMATS]
    random.shuffle(all_imgs)
    
    # --- Step 2: external test ---
    test_count = int(len(all_imgs) * test_ratio)
    test_imgs = all_imgs[:test_count]
    remain_imgs = all_imgs[test_count:]
    
    # --- Step 3: K folds on remaining data ---
    fold_size = len(remain_imgs) // k
    folds = []
    for i in range(k):
        start = i * fold_size
        end = len(remain_imgs) if i == k - 1 else (i + 1) * fold_size
        folds.append(remain_imgs[start:end])
    
    # --- Step 4: create main output directory ---
    out_base = input_dir.parent / f"dataset_seg_k{k}"
    out_base.mkdir(exist_ok=True)
    
    # --- Step 5: create folds directory with original folds + test ---
    folds_dir = out_base / "folds"
    folds_dir.mkdir(exist_ok=True)
    
    # Create test folder in folds
    test_fold_dir = folds_dir / "test"
    (test_fold_dir / "images").mkdir(parents=True, exist_ok=True)
    (test_fold_dir / "masks").mkdir(parents=True, exist_ok=True)
    
    for f in test_imgs:
        shutil.copy2(f, test_fold_dir / "images" / f.name)
        mask = mask_dir / f"{f.stem}.png"
        if mask.exists():
            shutil.copy2(mask, test_fold_dir / "masks" / mask.name)
    
    # Create k fold folders
    for i in range(k):
        fold_dir = folds_dir / f"fold_{i+1}"
        (fold_dir / "images").mkdir(parents=True, exist_ok=True)
        (fold_dir / "masks").mkdir(parents=True, exist_ok=True)
        
        for f in folds[i]:
            shutil.copy2(f, fold_dir / "images" / f.name)
            mask = mask_dir / f"{f.stem}.png"
            if mask.exists():
                shutil.copy2(mask, fold_dir / "masks" / mask.name)
    
    # --- Step 6: create k complete training datasets ---
    for i in range(k):
        ds = out_base / f"dataset_{i+1}"
        for split in ["train", "val", "test"]:
            (ds / split / "images").mkdir(parents=True, exist_ok=True)
            (ds / split / "masks").mkdir(parents=True, exist_ok=True)
        
        # test set (same for every dataset)
        for f in test_imgs:
            shutil.copy2(f, ds / "test" / "images" / f.name)
            mask = mask_dir / f"{f.stem}.png"
            if mask.exists():
                shutil.copy2(mask, ds / "test" / "masks" / mask.name)
        
        # val = current fold
        val_imgs = folds[i]
        # train = other folds
        train_imgs = [img for j in range(k) if j != i for img in folds[j]]
        
        # validation
        for f in val_imgs:
            shutil.copy2(f, ds / "val" / "images" / f.name)
            mask = mask_dir / f"{f.stem}.png"
            if mask.exists():
                shutil.copy2(mask, ds / "val" / "masks" / mask.name)
        
        # training
        for f in train_imgs:
            shutil.copy2(f, ds / "train" / "images" / f.name)
            mask = mask_dir / f"{f.stem}.png"
            if mask.exists():
                shutil.copy2(mask, ds / "train" / "masks" / mask.name)
    
    return out_base


# -------------------- 方法二: Classification (Stratified) --------------------
def generate_dataset_classification(input_dir, k=5, test_ratio=0.15):
    """先抽 external test，再做 Stratified K-fold (Classification)"""
    
    # --- Step 1: collect images by class ---
    classes = [d.name for d in input_dir.iterdir() if d.is_dir()]
    class_imgs = {cls: [] for cls in classes}
    
    for cls in classes:
        for img in (input_dir / cls).glob("*.*"):
            if img.suffix.lower() in SUPPORTED_FORMATS:
                class_imgs[cls].append(img)
        random.shuffle(class_imgs[cls])
    
    # --- Step 2: stratified external test (保持類別比例) ---
    test_imgs = []
    remain_imgs = {cls: [] for cls in classes}
    
    for cls in classes:
        imgs = class_imgs[cls]
        test_count = int(len(imgs) * test_ratio)
        test_imgs.extend([(img, cls) for img in imgs[:test_count]])
        remain_imgs[cls] = imgs[test_count:]
    
    # --- Step 3: Stratified K folds (每個類別分別分 fold) ---
    folds = [[] for _ in range(k)]
    
    for cls in classes:
        imgs = remain_imgs[cls]
        fold_size = len(imgs) // k
        for i in range(k):
            start = i * fold_size
            end = len(imgs) if i == k - 1 else (i + 1) * fold_size
            folds[i].extend([(img, cls) for img in imgs[start:end]])
    
    # --- Step 4: create main output directory ---
    out_base = input_dir.parent / f"dataset_cls_k{k}"
    out_base.mkdir(exist_ok=True)
    
    # --- Step 5: create folds directory with original folds + test ---
    folds_dir = out_base / "folds"
    folds_dir.mkdir(exist_ok=True)
    
    # Create test folder in folds
    test_fold_dir = folds_dir / "test"
    for cls in classes:
        (test_fold_dir / cls).mkdir(parents=True, exist_ok=True)
    
    for img, cls in test_imgs:
        shutil.copy2(img, test_fold_dir / cls / img.name)
    
    # Create k fold folders
    for i in range(k):
        fold_dir = folds_dir / f"fold_{i+1}"
        for cls in classes:
            (fold_dir / cls).mkdir(parents=True, exist_ok=True)
        
        for img, cls in folds[i]:
            shutil.copy2(img, fold_dir / cls / img.name)
    
    # --- Step 6: create k complete training datasets ---
    for i in range(k):
        ds = out_base / f"dataset_{i+1}"
        for split in ["train", "val", "test"]:
            for cls in classes:
                (ds / split / cls).mkdir(parents=True, exist_ok=True)
        
        # test (same every dataset)
        for img, cls in test_imgs:
            shutil.copy2(img, ds / "test" / cls / img.name)
        
        # validation = current fold
        val_list = folds[i]
        # train = other folds
        train_list = [item for j in range(k) if j != i for item in folds[j]]
        
        # val
        for img, cls in val_list:
            shutil.copy2(img, ds / "val" / cls / img.name)
        
        # train
        for img, cls in train_list:
            shutil.copy2(img, ds / "train" / cls / img.name)
    
    return out_base


# -------------------- GUI --------------------
class KFoldGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("K-Fold 圖片工具")
        self.selected_folder = None
        self.k_value = tk.IntVar(value=5)
        self.setup_ui()
    
    def setup_ui(self):
        tk.Label(self.window, text="資料夾:").grid(row=0, column=0, padx=5, pady=5)
        self.folder_entry = tk.Entry(self.window, width=40)
        self.folder_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Button(self.window, text="瀏覽", command=self.browse_folder).grid(row=0, column=2, padx=5, pady=5)
        
        tk.Label(self.window, text="K 值:").grid(row=1, column=0, padx=5, pady=5)
        tk.Entry(self.window, textvariable=self.k_value, width=10).grid(row=1, column=1, sticky='w', padx=5, pady=5)
        
        tk.Button(self.window, text="方法一: Segmentation K-Fold", 
                 command=self.run_method1, width=35).grid(row=2, column=0, columnspan=3, pady=10)
        tk.Button(self.window, text="方法二: Classification Stratified K-Fold", 
                 command=self.run_method2, width=35).grid(row=3, column=0, columnspan=3, pady=10)
        
        # 說明文字
        info_text = """
說明：
1. 先從原始數據抽取 15% 作為 external test set
   (Classification 使用 stratified 保持類別比例)
2. 剩下的 85% 分成 K 個 fold (stratified)
3. 生成結構：
   - dataset_1 到 dataset_K（每個都是完整的 train/val/test）
   - folds 資料夾（包含原始的 fold_1 到 fold_K + test）
        """
        tk.Label(self.window, text=info_text, justify='left', 
                bg='lightyellow').grid(row=4, column=0, columnspan=3, padx=10, pady=10)
    
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.selected_folder = Path(folder)
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)
    
    def run_method1(self):
        if not self.selected_folder:
            messagebox.showwarning("警告", "請先選擇資料夾")
            return
        try:
            result_dir = generate_dataset_segmentation(self.selected_folder, self.k_value.get(), test_ratio=0.15)
            messagebox.showinfo("完成", f"Segmentation K-Fold 完成！\n輸出位置：{result_dir}")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("錯誤", str(e))
    
    def run_method2(self):
        if not self.selected_folder:
            messagebox.showwarning("警告", "請先選擇資料夾")
            return
        try:
            result_dir = generate_dataset_classification(self.selected_folder, self.k_value.get(), test_ratio=0.15)
            messagebox.showinfo("完成", f"Classification Stratified K-Fold 完成！\n輸出位置：{result_dir}")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("錯誤", str(e))
    
    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    app = KFoldGUI()
    app.run()