"""UNet 訓練介面主程式"""
import sys
import os
import time
from UNet import UNet, SegmentationDataset, train_model, get_dataloader, save_model  # 改為 UNet
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import torch
import torch.nn as nn
import torch.optim as optim
from test_window import TestWindow
from torch.utils.data import get_worker_info
import threading

def thread_safe_update(*args, **kwargs):
    # 保證 GUI 更新只在 main thread
    root.after(0, lambda: update_training_progress(*args, **kwargs))

# 初始設定
sys.stdout.reconfigure(line_buffering=True)
torch.cuda.empty_cache()

# 將目前目錄加入系統路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

if __name__ == '__main__':
    # 設定路徑
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    dataset_root = os.path.join(PROJECT_ROOT, "IMG", "IMG_train")
    dataset_path = os.path.join(dataset_root, "method1")
    model_dir = os.path.join(PROJECT_ROOT, "model")
    os.makedirs(model_dir, exist_ok=True)
    model_save_path = os.path.join(model_dir, "unet_model.pth")  # 改為 unet_model.pth

    # 設定資料集路徑
    train_path = os.path.join(dataset_path, "train")
    val_path = os.path.join(dataset_path, "val")
    test_path = os.path.join(dataset_path, "test")
    IMAGE_DIR, MASK_DIR = "images", "masks"

    # 建立各部分路徑
    train_images = os.path.join(train_path, IMAGE_DIR)
    train_masks = os.path.join(train_path, MASK_DIR)
    val_images = os.path.join(val_path, IMAGE_DIR)
    val_masks = os.path.join(val_path, MASK_DIR)
    test_images = os.path.join(test_path, IMAGE_DIR)
    test_masks = os.path.join(test_path, MASK_DIR)

    # 設定超參數
    batch_size = 8
    learning_rate = 5e-4
    weight_decay = 5e-4
    num_epochs = 30
    patience_epochs = 10
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 初始化模型和優化器
    try:
        # 使用修改後的 UNet 參數名稱
        model = UNet(in_channels=3, num_classes=2, bilinear=True, base_c=32).to(device)
        weights = torch.tensor([1.0, 4.0]).to(device)
        criterion = nn.CrossEntropyLoss(weight=weights, reduction='mean')
        optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
        print("Model and optimizer initialized successfully.")
        print(f"模型類型: {type(model).__name__}")
        print(f"模型參數數量: {sum(p.numel() for p in model.parameters()):,}")
    except Exception as e:
        print(f"Error initializing model: {e}")

    # 初始化資料加載器
    try:
        data_loaders = get_dataloader(
            train_images=train_images, train_masks=train_masks,
            val_images=val_images, val_masks=val_masks,
            test_images=test_images, test_masks=test_masks,
            batch_size=batch_size
        )
        train_loader = data_loaders['train']
        test_loader = data_loaders['test']
        val_loader = data_loaders['val']
        print("Data loaders created successfully.")
    except Exception as e:
        print(f"Error creating data loaders: {e}")
        train_loader = test_loader = val_loader = None

    # GUI 相關變數
    last_message_timer = None
    loss_history = []  # 新增：用於記錄所有 loss

def create_gui_elements():
    """創建GUI元素"""
    global progress_label, progress_bar, fig_loss, ax_loss, canvas_loss
    global line_train_loss, line_val_loss, line_val_acc, line_val_dice
    global fig_metric, ax_metric, canvas_metric
    global num_epochs_var

    # 創建左側按鈕區域
    left_frame = tk.Frame(root, bg="#e0e0e0", width=350)
    left_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)
    left_frame.pack_propagate(False)

    # 創建按鈕容器
    button_container = tk.Frame(left_frame, bg="#e0e0e0")
    button_container.place(relx=0.5, rely=0.5, anchor="center", width=300)

    # 按鈕區域分為上半部分（一般按鈕）和下半部分（離開按鈕）
    top_buttons_frame = tk.Frame(left_frame, bg="#e0e0e0")
    top_buttons_frame.place(relx=0.5, rely=0.5, anchor="s", width=300)

    bottom_button_frame = tk.Frame(left_frame, bg="#e0e0e0")
    bottom_button_frame.place(relx=0.5, rely=0.95, anchor="s", width=300)

    # 新增回合數設定區域
    epoch_frame = tk.Frame(top_buttons_frame, bg="#e0e0e0")
    epoch_frame.pack(pady=5)
    
    tk.Label(epoch_frame, text="訓練回合數:", bg="#e0e0e0", font=("Arial", 12)).pack(side=tk.LEFT)
    num_epochs_var = tk.StringVar(value=str(num_epochs))
    epoch_entry = tk.Entry(epoch_frame, textvariable=num_epochs_var, width=5, font=("Arial", 12))
    epoch_entry.pack(side=tk.LEFT, padx=5)

    # 統一按鈕樣式
    button_width = 300
    button_style = {
        "width": 20,
        "height": 2,
        "font": ("Arial", 14),
        "relief": tk.RAISED,
        "bd": 3,
        "padx": 10
    }

    # 資料集資訊按鈕
    dataset_button = tk.Button(top_buttons_frame, text="目前資料集", command=show_dataset_info,
                             bg="lightsteelblue", **button_style)
    dataset_button.pack(pady=15, ipadx=(button_width - button_style["width"]*10)//2)

    # 訓練按鈕
    global train_button
    train_button = tk.Button(top_buttons_frame, text="訓練模型", command=train, 
                           bg="lightblue", **button_style)
    train_button.pack(pady=15, ipadx=(button_width - button_style["width"]*10)//2)

    # 測試按鈕
    test_button = tk.Button(top_buttons_frame, text="測試模型", command=test, 
                          bg="lightgreen", **button_style)
    test_button.pack(pady=15, ipadx=(button_width - button_style["width"]*10)//2)

    # 刪除舊模型按鈕
    retrain_button = tk.Button(top_buttons_frame, text="刪除舊模型", command=reset_model, 
                             bg="lightyellow", **button_style)
    retrain_button.pack(pady=15, ipadx=(button_width - button_style["width"]*10)//2)

    # 結果顯示標籤
    global result_label
    result_label = tk.Label(bottom_button_frame, text="", bg="#e0e0e0",
                           font=("Arial", 14), fg="black")
    result_label.pack(pady=20)

    # 離開按鈕
    exit_button = tk.Button(bottom_button_frame, text="離開", command=root.quit, 
                          bg="lightcoral", **button_style)
    exit_button.pack(pady=15, ipadx=(button_width - button_style["width"]*10)//2)

    # 創建右側進度顯示區域
    right_frame = tk.Frame(root, bg="#f0f0f0")
    right_frame.pack(side=tk.RIGHT, padx=20, fill=tk.BOTH, expand=True)

    # 訓練進度標籤
    progress_label = tk.Label(right_frame, text="", bg="#f0f0f0", font=("Arial", 12))
    progress_label.pack(pady=10)

    # 進度條容器
    progress_container = tk.Frame(right_frame, bg="#f0f0f0")
    progress_container.pack(fill=tk.X, pady=10, padx=20)

    # 訓練進度條
    progress_bar = ttk.Progressbar(progress_container, orient="horizontal", mode="determinate")
    progress_bar.pack(fill=tk.X)

    # 圖表區域
    chart_frame = tk.Frame(right_frame, bg="#f0f0f0")
    chart_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 10))

    # Loss 曲線圖 (train loss: 藍實線, val loss: 紅虛線)
    fig_loss = Figure(figsize=(8, 4))
    ax_loss = fig_loss.add_subplot(111)
    ax_loss.set_title('Train & Val Loss')
    ax_loss.set_xlabel('Epoch')
    ax_loss.set_ylabel('Loss')
    ax_loss.set_xlim(0, num_epochs+1)
    line_train_loss, = ax_loss.plot([], [], 'b-', label='Train Loss')
    line_val_loss, = ax_loss.plot([], [], 'r--', label='Val Loss')
    ax_loss.legend()
    canvas_loss = FigureCanvasTkAgg(fig_loss, master=chart_frame)
    canvas_loss.get_tk_widget().grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

    # Metric 曲線圖 (val acc: 綠線, val dice: 紫線)
    fig_metric = Figure(figsize=(8, 4))
    ax_metric = fig_metric.add_subplot(111)
    ax_metric.set_title('Val Acc & Dice')
    ax_metric.set_xlabel('Epoch')
    ax_metric.set_ylabel('Score (%)')
    ax_metric.set_ylim(0, 100)
    ax_metric.set_xlim(0, num_epochs+1)
    line_val_acc, = ax_metric.plot([], [], 'g-', label='Val Acc')
    line_val_dice, = ax_metric.plot([], [], 'm--', label='Val Dice')
    ax_metric.legend()
    canvas_metric = FigureCanvasTkAgg(fig_metric, master=chart_frame)
    canvas_metric.get_tk_widget().grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

    chart_frame.grid_rowconfigure(0, weight=1)
    chart_frame.grid_rowconfigure(1, weight=1)
    chart_frame.grid_columnconfigure(0, weight=1)


# 其他必要的函數
def show_dataset_info():
    """顯示目前資料集的相關資訊"""
    try:
        # 直接從目錄計算圖片數量
        def count_images(path):
            if not os.path.exists(path):
                return 0
            return len([f for f in os.listdir(path) if f.endswith(('.png', '.jpg', '.jpeg'))])
        
        # 獲取各目錄中的圖片數量
        train_count = count_images(train_images)
        val_count = count_images(val_images)
        test_count = count_images(test_images)
        
        # 驗證遮罩數量是否匹配
        train_mask_count = count_images(train_masks)
        val_mask_count = count_images(val_masks)
        test_mask_count = count_images(test_masks)
        
        # 準備顯示訊息
        info = (
            f"資料集分布 (method1):\n\n"
            f"訓練集：\n  -圖片：{train_count} 張\n  -遮罩：{train_mask_count} 張\n\n"
            f"驗證集：\n  -圖片：{val_count} 張\n  -遮罩：{val_mask_count} 張\n\n"
            f"測試集：\n  -圖片：{test_count} 張\n  -遮罩：{test_mask_count} 張\n\n"
            f"總圖片數量：{train_count + val_count + test_count} 張"
        )

        # 檢查圖片和遮罩數量是否匹配
        if (train_count != train_mask_count or 
            val_count != val_mask_count or 
            test_count != test_mask_count):
            info += "\n\n警告：部分圖片和遮罩數量不匹配！"
        
        messagebox.showinfo("資料集資訊", info)
    except Exception as e:
        show_temp_message(f"無法獲取資料集資訊: {e}", "red")
        print(f"Error getting dataset info: {e}")

val_loss_history = []
val_acc_history = []
val_dice_history = []
train_loss_history = []

def update_training_progress(epoch, total_epochs, batch, total_batches,
                              train_loss=None, val_loss=None, val_acc=None, val_dice=None):
    """更新訓練進度,只更新線條數據,不清除 axes"""
    global train_loss_history, val_loss_history, val_acc_history, val_dice_history
    global line_train_loss, line_val_loss, line_val_acc, line_val_dice
    global canvas_loss, canvas_metric
    
    # 只在主線程更新 GUI
    if get_worker_info() is not None:
        return
    
    # 計算 ETA 只在 epoch 結束時
    if not hasattr(update_training_progress, 'start_time'):
        update_training_progress.start_time = time.time()
    elapsed_time = time.time() - update_training_progress.start_time
    completed_epochs = epoch
    avg_epoch_time = elapsed_time / completed_epochs if completed_epochs > 0 else 0
    remaining_time = avg_epoch_time * (total_epochs - completed_epochs)
    minutes = int(remaining_time // 60)
    seconds = int(remaining_time % 60)
    eta_text = f", ETA: {minutes}m {seconds}s"
    
    # 更新進度文字
    progress_text = f"Epoch {epoch}/{total_epochs}, Batch {batch}/{total_batches}{eta_text}"
    if train_loss is not None:
        progress_text += f", Train Loss: {train_loss:.4f}"
    if val_loss is not None:
        progress_text += f", Val Loss: {val_loss:.4f}"
    if val_acc is not None:
        progress_text += f", Val Acc: {val_acc:.4f}"

    # 當一個 epoch 完成時,更新歷史數據和圖表
    if batch == total_batches:
        # 將當前 epoch 的數據添加到歷史記錄中
        if train_loss is not None:
            train_loss_history.append(train_loss)
        if val_loss is not None:
            val_loss_history.append(val_loss)
        if val_acc is not None:
            val_acc_history.append(val_acc)
        if val_dice is not None:
            val_dice_history.append(val_dice)
        
        # 更新 Loss 曲線
        if train_loss_history:
            x_train = list(range(1, len(train_loss_history)+1))
            line_train_loss.set_data(x_train, train_loss_history)
        if val_loss_history:
            x_val = list(range(1, len(val_loss_history)+1))
            line_val_loss.set_data(x_val, val_loss_history)
        
        # 更新 Metric 曲線 - 轉換成百分比
        if val_acc_history:
            x_acc = list(range(1, len(val_acc_history)+1))
            val_acc_percent = [acc * 100 for acc in val_acc_history]
            line_val_acc.set_data(x_acc, val_acc_percent)
        if val_dice_history:
            x_dice = list(range(1, len(val_dice_history)+1))
            val_dice_percent = [dice * 100 for dice in val_dice_history]
            line_val_dice.set_data(x_dice, val_dice_percent)
        
        # 固定 y 軸 0~100 for percentage
        ax_metric.set_ylim(0, 100)
        ax_metric.set_xlim(0, total_epochs+1)

    def safe_gui_update():
        progress_label.config(text=progress_text)
        progress_bar["value"] = (epoch - 1 + batch / total_batches) / total_epochs * 100
        # 自動調整 y 軸範圍
        ax_loss.relim()
        ax_loss.autoscale_view()
        ax_loss.set_xlim(0, total_epochs+1)
        canvas_loss.draw_idle()
        canvas_metric.draw_idle()

    # 使用 thread-safe 方法更新 GUI
    root.after(0, safe_gui_update)


def clear_result_message():
    result_label.config(text="")

def show_temp_message(message, color="black"):
    global last_message_timer
    if last_message_timer is not None:
        root.after_cancel(last_message_timer)
    result_label.config(text=message, fg=color)
    last_message_timer = root.after(3000, clear_result_message)

def reset_model():
    # 顯示確認對話框
    confirm = messagebox.askokcancel("確認刪除", "確定要刪除舊模型嗎？")
    if not confirm:  # 按 X 或取消
        show_temp_message("已取消刪除", "blue")
        return

    if os.path.exists(model_save_path):
        os.remove(model_save_path)
        show_temp_message("舊模型已刪除", "blue")
    else:
        show_temp_message("沒有舊模型可刪除", "red")

def train():
    print("Training the model...")
    global num_epochs

    if os.path.exists(model_save_path):
        show_temp_message("已有 UNet 模型存在！", "red")
        return

    try:
        num_epochs = int(num_epochs_var.get())
        if num_epochs <= 0:
            raise ValueError("回合數必須大於 0")
    except ValueError as e:
        show_temp_message(f"回合數設定錯誤: {e}", "red")
        return

    try:
        for dir_path in [
            train_images, train_masks,
            val_images, val_masks,
            test_images, test_masks
        ]:
            if not os.path.exists(dir_path):
                raise FileNotFoundError(f"找不到資料夾：{dir_path}")
            if not any(f.endswith(('.png', '.jpg', '.jpeg')) for f in os.listdir(dir_path)):
                raise ValueError(f"資料夾內沒有圖片：{dir_path}")
    except Exception as e:
        show_temp_message(str(e), "red")
        return
    
    train_button.config(state=tk.DISABLED)
    threading.Thread(target=train_worker, daemon=True).start()

def train_worker():
    global model, optimizer, train_loader, val_loader, test_loader

    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        model = UNet(
            in_channels=3,
            num_classes=2,
            bilinear=True,
            base_c=32
        ).to(device)

        optimizer = optim.Adam(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay
        )

        data_loaders = get_dataloader(
            train_images=train_images,
            train_masks=train_masks,
            val_images=val_images,
            val_masks=val_masks,
            test_images=test_images,
            test_masks=test_masks,
            batch_size=batch_size
        )

        train_loader = data_loaders['train']
        val_loader = data_loaders['val']
        test_loader = data_loaders['test']

        root.after(0, reset_charts)

        model, best_iou, minutes, seconds = train_model(
            model,
            train_loader,
            criterion,
            optimizer,
            num_epochs,
            thread_safe_update,
            val_loader=val_loader,
            patience=patience_epochs,
            device=device
        )

        root.after(0, lambda: on_train_finished(best_iou, minutes, seconds))

    except Exception as e:
        root.after(0, lambda: show_temp_message(f"訓練失敗: {e}", "red"))
        root.after(0, lambda: train_button.config(state=tk.NORMAL))

def on_train_finished(best_iou, minutes, seconds):
    save_model(model, model_save_path)
    progress_label.config(
        text=f"訓練完成！花費時間: {minutes}分{seconds}秒，最佳 IoU: {best_iou:.4f}",
        fg="green"
    )
    progress_bar["value"] = 100
    train_button.config(state=tk.NORMAL)

def reset_charts():
    """重置圖表與歷史紀錄"""
    global train_loss_history, val_loss_history, val_acc_history, val_dice_history
    global line_train_loss, line_val_loss, line_val_acc, line_val_dice

    train_loss_history.clear()
    val_loss_history.clear()
    val_acc_history.clear()
    val_dice_history.clear()

    # 重新創建線條對象
    ax_loss.clear()
    ax_loss.set_title('Train & Val Loss')
    ax_loss.set_xlabel('Epoch')
    ax_loss.set_ylabel('Loss')
    ax_loss.set_xlim(0, num_epochs+1)
    line_train_loss, = ax_loss.plot([], [], 'b-', label='Train Loss')
    line_val_loss, = ax_loss.plot([], [], 'r--', label='Val Loss')
    ax_loss.legend()
    canvas_loss.draw()

    ax_metric.clear()
    ax_metric.set_title('Val Acc & Dice')
    ax_metric.set_xlabel('Epoch')
    ax_metric.set_ylabel('Score (%)')
    ax_metric.set_ylim(0, 100)
    ax_metric.set_xlim(0, num_epochs+1)
    line_val_acc, = ax_metric.plot([], [], 'g-', label='Val Acc')
    line_val_dice, = ax_metric.plot([], [], 'm--', label='Val Dice')
    ax_metric.legend()
    canvas_metric.draw()
    
    # Reset start time for ETA calculation
    if hasattr(update_training_progress, 'start_time'):
        delattr(update_training_progress, 'start_time')

def test():
    print("Testing the model...")
    try:
        model = UNet(in_channels=3, num_classes=2, bilinear=True, base_c=32).to(device)
        state_dict = torch.load(model_save_path, map_location=device, weights_only=True)
        model.load_state_dict(state_dict)
        model.eval()
        with torch.no_grad():
            test_window = TestWindow(model, device, test_images)
    except Exception as e:
        show_temp_message(f"測試失敗: {e}", "red")
        print(f"Testing error: {e}")

def save_model(model, path):
    torch.save(model.state_dict(), path)
    print(f"Model saved to {path}")

def main():
    global root
    root = tk.Tk()
    root.title("UNet 訓練介面")
    root.geometry("1000x1000")
    root.configure(bg="#f0f0f0")

    create_gui_elements()
    root.mainloop()

if __name__ == "__main__":
    main()