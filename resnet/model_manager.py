"""
model_manager.py - 統一統計值管理
將 mean+std 直接記錄在訓練紀錄中
"""

import tkinter as tk 
from tkinter import ttk, messagebox
import json
import os
from datetime import datetime
import torch
import numpy as np
from sklearn.metrics import accuracy_score
from trainer import Config

record_path = os.path.join(os.path.dirname(__file__), "..", "model", "model_records.json")
record_path = os.path.abspath(record_path)
model_dir = os.path.join(os.path.dirname(record_path))

# ====================== 修改後的儲存函數 ======================
def save_training_record(model_name, model_type, lr, wd, batch_size, val_acc, 
                        test_acc=None, note="", train_stats=None):
    """
    儲存訓練紀錄到 JSON（包含統計值）
    
    Args:
        model_name: 模型名稱
        model_type: 模型類型 ("ResNet", "MLP", "XGBoost", "RF", "CoralResNet", "CoralMLP")
        lr: 學習率
        wd: weight decay
        batch_size: batch size
        val_acc: 驗證準確率
        test_acc: 測試準確率 (可選)
        note: 備註
        train_stats: 訓練集統計值字典 (可選)
            格式: {
                'age': {'mean': 50.5, 'std': 15.2},
                'gender': {'mean': 0.5, 'std': 0.5},
                'Length_px': {'mean': 200.0, 'std': 50.0},
                'Entropy': {'mean': 0.5, 'std': 0.1},
                'Contrast_Ratio': {'mean': 1.0, 'std': 0.2}
            }
    """
    record = {
        "model_name": model_name,
        "model_type": model_type,
        "lr": lr,
        "weight_decay": wd,
        "batch_size": batch_size,
        "val_acc": val_acc,
        "test_acc": test_acc if test_acc is not None else 0.0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": note+",seed="+str(Config.SEED),
        "train_stats": train_stats  #  直接記錄統計值
    }

    if os.path.exists(record_path):
        with open(record_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    else:
        records = []

    records.append(record)

    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)
    
    print(f"✓ 訓練紀錄已儲存: {model_name}")
    if train_stats:
        print(f"✓ 統計值已記錄在模型紀錄中")


def get_model_stats(model_name):
    """
    從模型紀錄中獲取訓練集統計值
    
    Args:
        model_name: 模型名稱
    
    Returns:
        train_stats: 統計值字典，如果找不到則返回 None
    """
    records = load_records()
    
    for record in records:
        if record.get("model_name") == model_name:
            stats = record.get("train_stats")
            if stats:
                print(f"✓ 找到模型 {model_name} 的統計值")
                return stats
            else:
                print(f"⚠️  模型 {model_name} 沒有記錄統計值")
                return None
    
    print(f"❌ 找不到模型 {model_name} 的紀錄")
    return None


def print_model_stats(model_name):
    """
    打印模型的統計值
    
    Args:
        model_name: 模型名稱
    """
    stats = get_model_stats(model_name)
    
    if not stats:
        print(f"❌ 無法獲取模型 {model_name} 的統計值")
        return
    
    print(f"\n{'='*60}")
    print(f"模型 {model_name} 的訓練集統計值:")
    print(f"{'='*60}")
    print(f"{'欄位':<15} | {'Mean':<10} | {'Std':<10}")
    print(f"{'-'*60}")
    
    for field, values in stats.items():
        print(f"{field:<15} | {values['mean']:<10.4f} | {values['std']:<10.4f}")
    
    print(f"{'='*60}\n")


# ====================== 修改後的刪除函數 ======================
def delete_selected(tree):
    """刪除選中的模型和紀錄（包含統計值）"""
    selected_items = tree.selection()
    if not selected_items:
        messagebox.showwarning("警告", "請先勾選要刪除的模型紀錄")
        return

    confirm = messagebox.askokcancel(
        "確認刪除", 
        f"確定要刪除 {len(selected_items)} 筆模型與紀錄嗎？\n統計值也會一併刪除。"
    )
    if not confirm:
        return

    records = load_records()
    deleted_count = 0

    for item in selected_items:
        values = tree.item(item, "values")
        model_name = values[0]
        model_type = values[1]

        # 刪除模型檔案
        model_file = os.path.join(
            model_dir, 
            f"{model_name}.pth" if model_type in ["ResNet", "MLP", "CoralResNet", "CoralMLP"] 
            else f"{model_name}.pkl"
        )
        if os.path.exists(model_file):
            os.remove(model_file)
            print(f"已刪除模型檔案: {model_file}")

        # 從 JSON 刪除紀錄（包含統計值）
        records = [r for r in records if r["model_name"] != model_name]

        # 從 Treeview 刪除項目
        tree.delete(item)
        deleted_count += 1

    save_records(records)
    messagebox.showinfo("提示", f"已刪除 {deleted_count} 筆模型與紀錄（包含統計值）")


# ====================== 模型管理視窗 ======================
class ModelManagerWindow:
    """模型管理視窗類（支援統計值顯示）"""
    
    def __init__(self, parent=None, select_callback=None, select_type_only=None):
        self.select_callback = select_callback
        self.select_type_only = select_type_only
        
        if parent:
            self.window = tk.Toplevel(parent)
        else:
            self.window = tk.Tk()
        
        self.window.title("模型紀錄管理")
        self.window.geometry("1400x650")  #  加寬以容納統計值
        
        self._create_gui()
        self.load_data()
    
    def _create_gui(self):
        """創建GUI"""
        # 主框架
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview容器
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        #  添加 has_stats 欄位
        columns = ("model_name", "model_type", "lr", "wd", "batch", 
                  "val_acc", "test_acc", "has_stats", "time", "note")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # 垂直滾動條
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        
        # 設定欄位標題
        headers = {
            "model_name": "模型名稱",
            "model_type": "模型類型",
            "lr": "lr",
            "wd": "wd",
            "batch": "批次大小",
            "val_acc": "Val Acc",
            "test_acc": "Test Acc",
            "has_stats": "統計值",
            "time": "訓練時間",
            "note": "備註"
        }
        
        for col, title in headers.items():
            self.tree.heading(col, text=title)
            if col == "model_name":
                self.tree.column(col, anchor="w", stretch=True, width=110)
            elif col == "lr" or col == "wd":
                self.tree.column(col, anchor="center", stretch=True, width=60)
            elif col == "batch":
                self.tree.column(col, anchor="center", stretch=True, width=30)
            elif col == "note":
                self.tree.column(col, anchor="w", stretch=True, width=220)
            elif col == "has_stats":
                self.tree.column(col, anchor="center", stretch=False, width=50)
            else:
                self.tree.column(col, anchor="center", stretch=True, width=100)
        
        # 雙擊顯示統計值
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        
        # 按鈕框架
        btn_frame = tk.Frame(self.window)
        btn_frame.pack(fill=tk.X, pady=10)
        
        # 刪除按鈕
        tk.Button(
            btn_frame, 
            text="刪除勾選模型", 
            command=self._delete_selected,
            bg="lightcoral",
            font=("Arial", 11)
        ).pack(side=tk.RIGHT, padx=10)
        
        #  查看統計值按鈕
        tk.Button(
            btn_frame,
            text="查看統計值",
            command=self._show_stats,
            bg="lightyellow",
            font=("Arial", 11)
        ).pack(side=tk.RIGHT, padx=10)
        
        # 選擇模型按鈕
        if self.select_callback:
            tk.Button(
                btn_frame,
                text="選擇此模型進行測試",
                command=self._select_model,
                bg="lightgreen",
                font=("Arial", 11)
            ).pack(side=tk.RIGHT, padx=10)
        
        # 刷新按鈕
        tk.Button(
            btn_frame,
            text="刷新列表",
            command=self.load_data,
            bg="lightblue",
            font=("Arial", 11)
        ).pack(side=tk.LEFT, padx=10)
    
    def load_data(self):
        """載入數據到Treeview"""
        # 清空現有項目
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 載入紀錄
        records = load_records()
        
        if not records:
            messagebox.showinfo("提示", "目前尚無模型訓練紀錄")
            return
        
        # 按時間倒序排列
        records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # 插入數據
        for r in records:
            # 檢查是否有統計值
            has_stats = "✓" if r.get("train_stats") else "✗"
            
            self.tree.insert("", tk.END, values=(
                r.get("model_name", ""),
                r.get("model_type", "Unknown"),
                r.get("lr", ""),
                r.get("weight_decay", ""),
                r.get("batch_size", ""),
                f"{r.get('val_acc', 0):.4f}",
                f"{r.get('test_acc', 0):.4f}",
                has_stats,  # 顯示是否有統計值
                r.get("timestamp", ""),
                r.get("note", "")
            ))
    
    def _on_double_click(self, event):
        """雙擊顯示統計值"""
        self._show_stats()
    
    def _show_stats(self):
        """顯示選中模型的統計值"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "請先選擇一個模型")
            return
        
        if len(selected_items) > 1:
            messagebox.showwarning("警告", "請只選擇一個模型")
            return
        
        values = self.tree.item(selected_items[0], "values")
        model_name = values[0]
        
        stats = get_model_stats(model_name)
        
        if not stats:
            messagebox.showinfo(
                "無統計值", 
                f"模型 {model_name} 沒有記錄統計值\n\n"
                "可能原因：\n"
                "1. 這是舊版本訓練的模型\n"
                "2. 模型不需要統計值（如ResNet）"
            )
            return
        
        # 創建統計值顯示視窗
        stats_window = tk.Toplevel(self.window)
        stats_window.title(f"統計值 - {model_name}")
        stats_window.geometry("500x350")
        
        # 標題
        title_label = tk.Label(
            stats_window, 
            text=f"模型 {model_name} 的訓練集統計值",
            font=("Arial", 14, "bold"),
            pady=10
        )
        title_label.pack()
        
        # 統計值表格
        frame = ttk.Frame(stats_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 表頭
        header_frame = ttk.Frame(frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header_frame, text="欄位", font=("Arial", 11, "bold"), width=15).pack(side=tk.LEFT)
        tk.Label(header_frame, text="Mean", font=("Arial", 11, "bold"), width=15).pack(side=tk.LEFT)
        tk.Label(header_frame, text="Std", font=("Arial", 11, "bold"), width=15).pack(side=tk.LEFT)
        
        # 統計值內容
        for field in ['age', 'gender', 'Length_px', 'Entropy', 'Contrast_Ratio']:
            if field in stats:
                row_frame = ttk.Frame(frame)
                row_frame.pack(fill=tk.X, pady=2)
                
                tk.Label(row_frame, text=field, width=15).pack(side=tk.LEFT)
                tk.Label(row_frame, text=f"{stats[field]['mean']:.4f}", width=15).pack(side=tk.LEFT)
                tk.Label(row_frame, text=f"{stats[field]['std']:.4f}", width=15).pack(side=tk.LEFT)
        
        # 關閉按鈕
        tk.Button(
            stats_window,
            text="關閉",
            command=stats_window.destroy,
            width=15,
            font=("Arial", 11)
        ).pack(pady=10)
    
    def _delete_selected(self):
        """刪除選中的模型"""
        delete_selected(self.tree)
    
    def _select_model(self):
        """選擇模型進行測試"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "請先選擇一個模型")
            return
        
        if len(selected_items) > 1:
            messagebox.showwarning("警告", "請只選擇一個模型")
            return
        
        values = self.tree.item(selected_items[0], "values")
        model_name = values[0]
        model_type = values[1]
        
        # 檢查模型檔案是否存在
        model_file = os.path.join(
            model_dir, 
            f"{model_name}.pth" if model_type in ["ResNet", "MLP", "CoralResNet", "CoralMLP","MNIST_ResNet"] 
            else f"{model_name}.pkl"
        )
        if not os.path.exists(model_file):
            messagebox.showerror("錯誤", f"模型檔案不存在: {model_file}")
            return
        
        # 調用回調函數
        if self.select_callback:
            self.select_callback(model_name, model_type)
            self.window.destroy()
    
    def run(self):
        """運行視窗"""
        self.window.mainloop()


# ====================== 其他輔助函數保持不變 ======================
def load_records():
    """載入所有訓練紀錄"""
    if not os.path.exists(record_path):
        return []
    with open(record_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_records(records):
    """儲存訓練紀錄"""
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)


def open_model_manager(parent=None, select_callback=None, select_type_only=None):
    """打開模型管理視窗"""
    manager = ModelManagerWindow(parent, select_callback, select_type_only)
    return manager


def evaluate_test_accuracy(model, test_loader, device, use_meta=True):
    """評估測試準確率（保持不變）"""
    model.eval()
    correct = 0
    total = 0
    
    num_classes = model.num_classes if hasattr(model, 'num_classes') else None
    is_binary = (num_classes == 2)
    
    with torch.no_grad():
        for images, meta, labels in test_loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            if use_meta:
                meta = meta.to(device, non_blocking=True).float()
                outputs = model(images, meta)
            else:
                outputs = model(images)
            
            if is_binary:
                predicted = (torch.sigmoid(outputs) > 0.5).long()
            else:
                _, predicted = torch.max(outputs, 1)
            
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

    test_acc = correct / total if total > 0 else 0.0
    print(f"\n{'='*60}")
    print(f"測試集準確率: {test_acc:.4f} ({correct}/{total})")
    print(f"{'='*60}\n")
    
    return test_acc


def evaluate_ml_test_accuracy(feature_extractor, classifier, test_loader, device):
    """評估ML分類器的測試準確率（保持不變）"""
    feature_extractor.eval()
    
    all_features = []
    all_metas = []
    all_labels = []
    
    with torch.no_grad():
        for images, meta, labels in test_loader:
            images = images.to(device, non_blocking=True)
            cnn_features = feature_extractor(images).cpu().numpy()
            meta_features = meta.numpy()
            
            all_features.append(cnn_features)
            all_metas.append(meta_features)
            all_labels.append(labels.numpy())
    
    cnn_features = np.vstack(all_features)
    meta_features = np.vstack(all_metas)
    features = np.hstack([cnn_features, meta_features])
    labels = np.concatenate(all_labels)
    
    predictions = classifier.predict(features)
    test_acc = accuracy_score(labels, predictions)
    
    print(f"\n{'='*60}")
    print(f"測試集準確率: {test_acc:.4f}")
    print(f"{'='*60}\n")
    
    return test_acc


def main():
    """獨立運行模型管理器"""
    manager = ModelManagerWindow()
    manager.run()


if __name__ == "__main__":
    main()