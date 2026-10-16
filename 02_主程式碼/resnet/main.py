"""
main.py - 統一訓練介面
支援多種訓練模式: ResNet18, MLP, MobileNetV2, EfficientNet-B3, CORAL, XGBoost, Random Forest
"""
import sys
import os
import json
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import torch
import torch.nn as nn
import traceback
from datetime import datetime
from joblib import dump  # sklearn 模型存檔用

# 導入自定義模組
from base_models import BasicResNetClassifier, MLPClassifier, RewardPunishCrossEntropy, save_model_weights, load_model_weights, get_classifier
from loader_inference import get_dataloaders, get_class_weights, create_inference_pipeline
from trainer import MLPTrainer, MLClassifierTrainer, BasicResNetTrainer, BasicResNetTrainer, Config
from test_gui import launch_test_gui
from model_manager import open_model_manager, save_training_record, evaluate_test_accuracy, evaluate_ml_test_accuracy, load_records
from coral import create_coral_inference, create_ordinal_model, create_coral_trainer, evaluate_coral_model


# ==================== 主GUI類 ====================
class TrainingGUI:
    """統一訓練介面"""
    
    def __init__(self, root):
        self.root = root
        self.config = Config()
        self.config.setup()
        
        # 模型相關
        self.model = None
        self.optimizer = None
        self.criterion = None
        self.train_loader = None
        self.test_loader = None
        self.val_loader = None
        
        # 訓練歷史
        self.train_loss_history = []
        self.val_loss_history = []
        self.val_acc_history = []
        self.val_f1_history = []
        
        # 訓練模式
        self.training_mode = tk.StringVar(value="ResNet")
        
        # GUI元素
        self.last_message_timer = None
        
        # 初始化
        self._init_data()
        self._create_gui()
    
    def _init_data(self):
        """初始化數據載入器"""
        try:
            self.train_loader, self.test_loader, self.val_loader = get_dataloaders(
                self.config.dataset_path,
                self.config.metadata_path,
                self.config.batch_size,
                use_weighted_sampler=self.config.use_weighted_sampler
            )
            print(f"✓ 資料載入器初始化完成")
        except Exception as e:
            traceback.print_exc()
            print(f"⚠️  資料載入失敗: {e}")
    
    def _create_gui(self):
        """創建GUI"""
        self.root.title("統一訓練介面 - ResNet / MLP / XGBoost / Random Forest")
        self.root.geometry("1200x1200")
        self.root.configure(bg="#f0f0f0")
        
        # 左側控制面板
        self._create_left_panel()
        
        # 右側進度與圖表
        self._create_right_panel()
    
    def _create_left_panel(self):
        """左側控制面板"""
        left_frame = tk.Frame(self.root, bg="#e0e0e0", width=350)
        left_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        left_frame.pack_propagate(False)
        
        container = tk.Frame(left_frame, bg="#e0e0e0")
        container.place(relx=0.5, rely=0.5, anchor="center", width=300)
        
        # 訓練模式選擇
        self._create_mode_section(container)
        
        # 超參數設定
        self._create_hyperparameter_section(container)
        
        # 訓練策略
        self._create_strategy_section(container)
        
        # 功能按鈕
        self._create_action_buttons(container)
        
        # 結果顯示
        self.result_label = tk.Label(
            container, text="", bg="#e0e0e0",
            font=("Arial", 14), fg="black"
        )
        self.result_label.pack(pady=20)
    
    def _create_mode_section(self, parent):
        """訓練模式選擇"""
        frame = tk.LabelFrame(
            parent, text="訓練模式",
            bg="#e0e0e0", font=("Arial", 11, "bold")
        )
        frame.pack(pady=10, fill=tk.X)
        
        modes = [
            ("ResNet18 (Backbone+FC)", "ResNet"),
            ("MLP (含metadata)", "MLP"),
            ("MobileNetV2", "MobileNetV2"),
            ("MobileNetV2 + MLP", "MobileNetV2MLP"),
            ("EfficientNet-B3", "EfficientNetB3"),
            ("EfficientNet-B3 + MLP", "EfficientNetB3MLP"),
            ("CORAL ResNet", "CoralResNet"),
            ("CORAL MLP", "CoralMLP"),
            ("XGBoost", "XGBoost"),
            ("Random Forest", "RF")
        ]
        
        for text, value in modes:
            tk.Radiobutton(
                frame, text=text, variable=self.training_mode,
                value=value, bg="#e0e0e0", font=("Arial", 10)
            ).pack(anchor="w", padx=10, pady=2)
    
    def _create_hyperparameter_section(self, parent):
        """超參數設定"""
        frame = tk.LabelFrame(
            parent, text="超參數設定",
            bg="#e0e0e0", font=("Arial", 11, "bold")
        )
        frame.pack(pady=10, fill=tk.X)
        
        params = [
            ("學習率:", "lr_var", self.config.learning_rate),
            ("Weight Decay:", "wd_var", self.config.weight_decay),
            ("早停耐心:", "patience_var", self.config.patience_epochs),
            ("回合數:", "epochs_var", self.config.num_epochs)
        ]
        
        for label_text, var_name, default_value in params:
            row = tk.Frame(frame, bg="#e0e0e0")
            row.pack(anchor="w", padx=10, pady=3)
            
            tk.Label(
                row, text=label_text, bg="#e0e0e0",
                font=("Arial", 9), width=15, anchor="w"
            ).pack(side=tk.LEFT)
            
            var = tk.StringVar(value=str(default_value))
            setattr(self, var_name, var)
            
            tk.Entry(
                row, textvariable=var, width=10, font=("Arial", 9)
            ).pack(side=tk.LEFT, padx=5)
    
    def _create_strategy_section(self, parent):
        """訓練策略設定"""
        frame = tk.LabelFrame(
            parent, text="訓練策略",
            bg="#e0e0e0", font=("Arial", 11, "bold")
        )
        frame.pack(pady=10, fill=tk.X)
        
        # WeightedRandomSampler
        self.use_sampler_var = tk.BooleanVar(value=self.config.use_weighted_sampler)
        tk.Checkbutton(
            frame, text="使用 WeightedRandomSampler",
            variable=self.use_sampler_var,
            bg="#e0e0e0", font=("Arial", 10)
        ).pack(anchor="w", padx=10, pady=2)
        
        # 分階段訓練 (ResNet/MLP)
        self.use_staged_var = tk.BooleanVar(value=self.config.use_staged_training)
        tk.Checkbutton(
            frame, text="使用分階段訓練 (ResNet/MLP)",
            variable=self.use_staged_var,
            bg="#e0e0e0", font=("Arial", 10)
        ).pack(anchor="w", padx=10, pady=2)
        
        # 凍結epochs
        freeze_frame = tk.Frame(frame, bg="#e0e0e0")
        freeze_frame.pack(anchor="w", padx=20, pady=2)
        tk.Label(
            freeze_frame, text="凍結epochs:",
            bg="#e0e0e0", font=("Arial", 9)
        ).pack(side=tk.LEFT)
        
        self.freeze_epochs_var = tk.StringVar(value=str(self.config.freeze_epochs))
        tk.Entry(
            freeze_frame, textvariable=self.freeze_epochs_var,
            width=5, font=("Arial", 9)
        ).pack(side=tk.LEFT, padx=5)
    
    def _create_action_buttons(self, parent):
        """功能按鈕"""
        button_style = {
            "width": 20, "height": 2,
            "font": ("Arial", 14),
            "relief": tk.RAISED, "bd": 3
        }
        
        buttons = [
            ("目前資料集", self.show_dataset_info, "lightsteelblue"),
            ("開始訓練", self.start_training, "lightblue"),
            ("測試模型", self.test_model, "lightgreen"),
            ("模型管理", self.open_model_manager, "lightyellow"),
            None,
            ("離開", self.root.quit, "lightcoral")
        ]
        
        for item in buttons:
            if item is None:
                tk.Frame(parent, height=20).pack()
                continue
            
            text, command, color = item
            btn = tk.Button(
                parent, text=text, command=command,
                bg=color, **button_style
            )
            btn.pack(pady=12)
    
    def _create_right_panel(self):
        """右側進度與圖表"""
        right_frame = tk.Frame(self.root, bg="#f0f0f0")
        right_frame.pack(side=tk.RIGHT, padx=20, fill=tk.BOTH, expand=True)
        
        # 進度標籤
        self.progress_label = tk.Label(
            right_frame, text="", bg="#f0f0f0", font=("Arial", 12)
        )
        self.progress_label.pack(pady=10)
        
        # 進度條
        progress_container = tk.Frame(right_frame, bg="#f0f0f0")
        progress_container.pack(fill=tk.X, pady=10, padx=20)
        self.progress_bar = ttk.Progressbar(
            progress_container, orient="horizontal", mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X)
        
        # 圖表容器
        chart_frame = tk.Frame(right_frame, bg="#f0f0f0")
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 10))
        chart_frame.grid_rowconfigure(0, weight=1)
        chart_frame.grid_rowconfigure(1, weight=1)
        chart_frame.grid_columnconfigure(0, weight=1)
        
        # Loss曲線
        self._create_loss_chart(chart_frame)
        
        # Metric曲線
        self._create_metric_chart(chart_frame)
    
    def _create_loss_chart(self, parent):
        """Loss曲線圖"""
        self.fig_loss = Figure(figsize=(6, 3))
        self.ax_loss = self.fig_loss.add_subplot(111)
        self.ax_loss.set_title('Train & Val Loss')
        self.ax_loss.set_xlabel('Epoch')
        self.ax_loss.set_ylabel('Loss')
        self.ax_loss.set_xlim(0, self.config.num_epochs + 1)
        
        self.line_train_loss, = self.ax_loss.plot([], [], 'b-', label='Train Loss')
        self.line_val_loss, = self.ax_loss.plot([], [], 'r--', label='Val Loss')
        self.ax_loss.legend()
        
        self.canvas_loss = FigureCanvasTkAgg(self.fig_loss, master=parent)
        self.canvas_loss.get_tk_widget().grid(
            row=0, column=0, padx=5, pady=5, sticky="nsew"
        )
    
    def _create_metric_chart(self, parent):
        """Metric曲線圖"""
        self.fig_metric = Figure(figsize=(6, 3))
        self.ax_metric = self.fig_metric.add_subplot(111)
        self.ax_metric.set_title('Val Acc & F1')
        self.ax_metric.set_xlabel('Epoch')
        self.ax_metric.set_ylabel('Score')
        self.ax_metric.set_ylim(0, 1)
        self.ax_metric.set_xlim(0, self.config.num_epochs + 1)
        
        self.line_val_acc, = self.ax_metric.plot([], [], 'g-', label='Val Acc')
        self.line_val_f1, = self.ax_metric.plot([], [], 'm--', label='Val F1')
        self.ax_metric.legend()
        
        self.canvas_metric = FigureCanvasTkAgg(self.fig_metric, master=parent)
        self.canvas_metric.get_tk_widget().grid(
            row=1, column=0, padx=5, pady=5, sticky="nsew"
        )
    
    # ==================== 工具方法 ====================
    def show_temp_message(self, message, color="black"):
        """顯示臨時訊息"""
        if self.last_message_timer:
            self.root.after_cancel(self.last_message_timer)
        
        self.result_label.config(text=message, fg=color)
        self.last_message_timer = self.root.after(
            3000, lambda: self.result_label.config(text="")
        )
    
    def update_training_progress(self, epoch, total_epochs, batch, total_batches,
                                train_loss=None, val_loss=None, val_acc=None, val_f1=None,
                                update_history=True):
        """更新訓練進度"""
        progress_text = f"Epoch {epoch}/{total_epochs}, Batch {batch}/{total_batches}"
        if train_loss:
            progress_text += f", Train Loss: {train_loss:.4f}"
        if val_loss:
            progress_text += f", Val Loss: {val_loss:.4f}"
        if val_acc:
            progress_text += f", Val Acc: {val_acc:.4f}"
        
        self.progress_label.config(text=progress_text)
        self.progress_bar["value"] = (epoch - 1 + batch / total_batches) / total_epochs * 100
        
        # 更新歷史記錄
        if batch == total_batches and update_history:
            if train_loss:
                self.train_loss_history.append(train_loss)
            if val_loss:
                self.val_loss_history.append(val_loss)
            if val_acc:
                self.val_acc_history.append(val_acc)
            if val_f1:
                self.val_f1_history.append(val_f1)
            
            self._update_charts()
        
        self.root.update()
    
    def _update_charts(self):
        """更新圖表"""
        if self.train_loss_history:
            x = list(range(1, len(self.train_loss_history) + 1))
            self.line_train_loss.set_data(x, self.train_loss_history)
        
        if self.val_loss_history:
            x = list(range(1, len(self.val_loss_history) + 1))
            self.line_val_loss.set_data(x, self.val_loss_history)

        # 取 GUI 輸入的回合數
        try:
            num_epochs = int(self.epochs_var.get())
        except ValueError:
            num_epochs = self.config.num_epochs  # fallback

        self.ax_loss.set_xlim(0, num_epochs + 1)
        self.ax_loss.relim()
        self.ax_loss.autoscale(axis='y')
        self.canvas_loss.draw()
        
        if self.val_acc_history:
            x = list(range(1, len(self.val_acc_history) + 1))
            self.line_val_acc.set_data(x, self.val_acc_history)
        
        if self.val_f1_history:
            x = list(range(1, len(self.val_f1_history) + 1))
            self.line_val_f1.set_data(x, self.val_f1_history)
        
        self.ax_metric.set_xlim(0, num_epochs + 1)
        self.ax_metric.set_ylim(0, 1)
        self.canvas_metric.draw()
    
    def _reset_charts(self):
        """重置圖表"""
        self.train_loss_history = []
        self.val_loss_history = []
        self.val_acc_history = []
        self.val_f1_history = []
        
        self.ax_loss.clear()
        self.ax_loss.set_title('Train & Val Loss')
        self.ax_loss.set_xlabel('Epoch')
        self.ax_loss.set_ylabel('Loss')
        self.line_train_loss, = self.ax_loss.plot([], [], 'b-', label='Train Loss')
        self.line_val_loss, = self.ax_loss.plot([], [], 'r--', label='Val Loss')
        self.ax_loss.legend()
        
        self.ax_metric.clear()
        self.ax_metric.set_title('Val Acc & F1')
        self.ax_metric.set_xlabel('Epoch')
        self.ax_metric.set_ylabel('Score')
        self.ax_metric.set_ylim(0, 1)
        self.line_val_acc, = self.ax_metric.plot([], [], 'g-', label='Val Acc')
        self.line_val_f1, = self.ax_metric.plot([], [], 'm--', label='Val F1')
        self.ax_metric.legend()
        
        self.canvas_loss.draw()
        self.canvas_metric.draw()
    
    # ==================== 按鈕功能 ====================
    def show_dataset_info(self):
        """顯示資料集資訊"""
        try:
            # 獲取資料集大小
            total_train = len(self.train_loader.dataset)
            total_test = len(self.test_loader.dataset)
            total_val = len(self.val_loader.dataset)
            
            #  使用實際的類別名稱和數量
            actual_classes = list(self.config.CLASS_NAMES.values())
            class_counts = {cls: 0 for cls in actual_classes}
            
            #  統計每個類別的數量 (使用 label index)
            for _, _, label in self.train_loader.dataset:
                class_name = self.config.CLASS_NAMES[label]
                class_counts[class_name] += 1
            
            # 組裝訊息
            info = f"資料集分布:\n"
            info += f"類別數: {self.config.class_num}\n"
            info += f"總圖片數: {total_train + total_test + total_val}\n"
            info += f"訓練集: {total_train}張\n"
            info += f"驗證集: {total_val}張\n"
            info += f"測試集: {total_test}張\n\n"
            info += "訓練集各類別圖片數:\n"
            
            for cls in actual_classes:
                count = class_counts[cls]
                percentage = (count / total_train * 100) if total_train > 0 else 0
                info += f"{cls}: {count}張 ({percentage:.1f}%)\n"
            
            messagebox.showinfo("資料集資訊", info)
            
        except Exception as e:
            traceback.print_exc()
            self.show_temp_message(f"無法獲取資料集資訊: {e}", "red")
    
    def start_training(self):
        """開始訓練 - 統一入口"""
        mode = self.training_mode.get()
        training_methods = {
            "ResNet": self.train_resnet,
            "MLP": self.train_mlp,
            "MobileNetV2": lambda: self.train_small_model("mobilenetv2", False),
            "MobileNetV2MLP": lambda: self.train_small_model("mobilenetv2", True),
            "EfficientNetB3": lambda: self.train_small_model("efficientnet_B3", False),
            "EfficientNetB3MLP": lambda: self.train_small_model("efficientnet_B3", True),
            "CoralResNet": self.train_coral_resnet,
            "CoralMLP": self.train_coral_mlp,
            "XGBoost": lambda: self.train_ml_classifier("xgboost"),
            "RF": lambda: self.train_ml_classifier("rf")
        }
        
        if mode in training_methods:
            training_methods[mode]()
        else:
            self.show_temp_message(f"未知的訓練模式: {mode}", "red")


    def _train_neural_network(self, config):
        """訓練神經網路的統一流程
        
        Args:
            config: {
                'prefix': 模型名稱前綴,
                'model_type': 模型類型名稱,
                'model_class': 模型類 (可選，標準模型用),
                'trainer_class': 訓練器類 (可選，標準模型用),
                'model_kwargs': 模型初始化參數,
                'use_meta': 是否使用元數據,
                'is_coral': 是否為CORAL模型,
                'coral_type': CORAL模型類型 ('resnet' 或 'mlp')
            }
        """
        # ========== 前置檢查 ==========
        model_name = simpledialog.askstring(
            "模型名稱", 
            "請輸入模型名稱 (留空則自動生成):",
            parent=self.root
        )
        
        if model_name is None:
            return
        
        if not model_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_name = f"{config['prefix']}_{timestamp}"
        
        model_path = os.path.join(self.config.model_dir, f"{model_name}.pth")
        
        if os.path.exists(model_path):
            self.show_temp_message(f"模型 {model_name} 已存在!", "red")
            return
        
        # ========== 讀取超參數 ==========
        try:
            num_epochs = int(self.epochs_var.get())
            lr = float(self.lr_var.get())
            wd = float(self.wd_var.get())
            patience = int(self.patience_var.get())
            freeze_ep = int(self.freeze_epochs_var.get())
            
            if num_epochs <= 0 or lr <= 0 or wd < 0 or patience <= 0:
                raise ValueError("參數必須為正數")
                
            hyperparams = {
                'num_epochs': num_epochs, 'lr': lr, 'wd': wd,
                'patience': patience, 'freeze_epochs': freeze_ep
            }
        except ValueError as e:
            traceback.print_exc()
            self.show_temp_message(f"參數錯誤: {e}", "red")
            return
        
        use_sampler = self.use_sampler_var.get()
        
        # ========== 準備資料 ==========
        try:
            self.train_loader, self.test_loader, self.val_loader = get_dataloaders(
                self.config.dataset_path,
                self.config.metadata_path,
                self.config.batch_size,
                use_weighted_sampler=use_sampler
            )
        except Exception as e:
            traceback.print_exc()
            self.show_temp_message(f"載入資料失敗: {e}", "red")
            return
        
        #  保存訓練集統計值（從 train_loader 獲取）
        train_stats = self.train_loader.dataset.stats
        print("\n✓ 獲取訓練集統計值:")
        #for field, values in train_stats.items():
        #    print(f"  {field}: mean={values['mean']:.4f}, std={values['std']:.4f}")
        
        # ========== 初始化模型和訓練器 ==========
        try:
            if config.get('is_coral', False):
                # CORAL 模型 (不支援二元分類)
                if self.config.class_num == 2:
                    self.show_temp_message("CORAL 不支援二元分類!", "red")
                    return
                self.model = create_ordinal_model(
                    model_type=config['coral_type'],
                    num_classes=self.config.class_num,
                    **config.get('model_kwargs', {})
                ).to(self.config.device)
                
                class_weights = None
                if self.config.use_class_weights and not use_sampler:
                    class_weights = get_class_weights(
                        self.train_loader, self.config.class_num, self.config.device
                    )
                
                trainer = create_coral_trainer(
                    model_type=config['coral_type'],
                    model=self.model,
                    train_loader=self.train_loader,
                    val_loader=self.val_loader,
                    class_weights=class_weights,
                    device=self.config.device,
                    learning_rate=lr,
                    weight_decay=wd
                )
            else:
                # 標準模型
                self.model = config['model_class'](
                    num_classes=self.config.class_num,
                    **config.get('model_kwargs', {})
                ).to(self.config.device)
                
                self.optimizer = torch.optim.AdamW(
                    self.model.parameters(), lr=lr, weight_decay=wd
                )
                
                #  根據類別數選擇損失函數
                if self.config.class_num == 2:
                    # 二元分類: 使用 BCEWithLogitsLoss
                    if self.config.use_class_weights and not use_sampler:
                        class_weights = get_class_weights(
                            self.train_loader, self.config.class_num, self.config.device
                        )
                        # BCEWithLogitsLoss 的 pos_weight 參數
                        pos_weight = class_weights[1] / class_weights[0]
                        self.criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
                        print(f"✓ 使用 BCEWithLogitsLoss (pos_weight={pos_weight:.4f})")
                    else:
                        self.criterion = nn.BCEWithLogitsLoss()
                        print("✓ 使用 BCEWithLogitsLoss")
                else:
                    # 多類別分類: 使用自訂損失函數
                    class_weights = None
                    if self.config.use_class_weights and not use_sampler:
                        class_weights = get_class_weights(
                            self.train_loader, self.config.class_num, self.config.device
                        )
                    
                    if class_weights is not None:
                        #self.criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.1)
                        self.criterion = RewardPunishCrossEntropy(weight=class_weights, dist_penalty=0.7, label_smoothing=0.1)
                    else:
                        #self.criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
                        self.criterion = RewardPunishCrossEntropy(dist_penalty=0.7, label_smoothing=0.1)

                trainer = config['trainer_class'](
                    self.model, self.train_loader, self.val_loader,
                    self.criterion, self.optimizer, self.config.device
                )
            
            print(f"✓ 開始訓練{config['model_type']}: lr={lr}, wd={wd}, epochs={num_epochs}")
            
        except Exception as e:
            traceback.print_exc()
            self.show_temp_message(f"初始化失敗: {e}", "red")
            return
        
        # ========== 訓練 ==========
        self._reset_charts()
        
        try:
            model, best_val_acc, minutes, seconds, history = trainer.train(
                num_epochs=num_epochs,
                patience=patience,
                progress_callback=self.update_training_progress,
                use_staged_training=self.use_staged_var.get(),
                freeze_epochs=freeze_ep
            )
            
            # 儲存模型
            save_model_weights(model, model_path)
            
            # 計算測試準確率
            if config.get('is_coral', False):
                test_metrics = evaluate_coral_model(
                    trainer, self.test_loader, self.config.CLASS_NAMES, 
                    device=self.config.device
                )
                test_acc = test_metrics['accuracy']
            else:
                test_acc = evaluate_test_accuracy(
                    model, self.test_loader, self.config.device, 
                    use_meta=config.get('use_meta', False)
                )
            
            # 儲存訓練紀錄
            save_training_record(
                model_name=model_name,
                model_type=config['model_type'],
                lr=lr, wd=wd,
                batch_size=self.config.batch_size,
                val_acc=best_val_acc,
                test_acc=test_acc,
                note=f"Epochs:{num_epochs}, Patience:{patience}",
                train_stats=train_stats  #  傳入統計值
            )
            
            # 顯示完成訊息
            completion_text = (
                f"訓練完成！時間: {minutes}分{seconds}秒, "
                f"Val Acc: {best_val_acc:.4f}, Test Acc: {test_acc:.4f}"
            )
            self.progress_label.config(text=completion_text, fg="green")
            self.show_temp_message(f"{config['model_type']}模型 {model_name} 訓練完成!", "green")
            
        except Exception as e:
            traceback.print_exc()
            self.show_temp_message(f"訓練失敗: {e}", "red")
        finally:
            self.progress_bar["value"] = 100


    def train_resnet(self):
        """訓練基礎ResNet模型"""
        self._train_neural_network({
            'prefix': 'ResNet',
            'model_type': 'ResNet',
            'model_class': BasicResNetClassifier,
            'trainer_class': BasicResNetTrainer,
            'model_kwargs': {},
            'use_meta': False,
            'is_coral': False
        })


    def train_mlp(self):
        """訓練MLP模型"""
        self._train_neural_network({
            'prefix': 'MLP',
            'model_type': 'MLP',
            'model_class': MLPClassifier,
            'trainer_class': MLPTrainer,
            'model_kwargs': {'meta_dim': Config.meta_dim},
            'use_meta': True,
            'is_coral': False
        })

    def train_small_model(self, backbone_type, use_meta):
        """訓練小模型 (MobileNetV2 或 EfficientNet-B3)
        
        Args:
            backbone_type: 'mobilenetv2' 或 'efficientnet_B3'
            use_meta: 是否使用 metadata (True=MLP, False=純CNN)
        """
        # 確定模型名稱前綴和類型
        if backbone_type == 'mobilenetv2':
            prefix = 'MobileNetV2_MLP' if use_meta else 'MobileNetV2'
            model_type = 'MobileNetV2_MLP' if use_meta else 'MobileNetV2'
        else:  # efficientnet_B3
            prefix = 'EfficientNetB3_MLP' if use_meta else 'EfficientNetB3'
            model_type = 'EfficientNetB3_MLP' if use_meta else 'EfficientNetB3'
        
        # 選擇模型類和訓練器
        if use_meta:
            model_class = MLPClassifier
            trainer_class = MLPTrainer
            model_kwargs = {'meta_dim': Config.meta_dim, 'backbone_type': backbone_type}
        else:
            model_class = BasicResNetClassifier
            trainer_class = BasicResNetTrainer
            model_kwargs = {'backbone_type': backbone_type}
        
        # 調用統一訓練流程
        self._train_neural_network({
            'prefix': prefix,
            'model_type': model_type,
            'model_class': model_class,
            'trainer_class': trainer_class,
            'model_kwargs': model_kwargs,
            'use_meta': use_meta,
            'is_coral': False
        })

    def train_coral_resnet(self):
        """訓練 CORAL ResNet 模型"""
        self._train_neural_network({
            'prefix': 'CoralResNet',
            'model_type': 'CoralResNet',
            'coral_type': 'resnet',
            'model_kwargs': {},
            'is_coral': True
        })


    def train_coral_mlp(self):
        """訓練 CORAL MLP 模型"""
        self._train_neural_network({
            'prefix': 'CoralMLP',
            'model_type': 'CoralMLP',
            'coral_type': 'mlp',
            'model_kwargs': {'meta_dim': Config.meta_dim},
            'is_coral': True
        })


    def train_ml_classifier(self, classifier_type):
        """訓練XGBoost/RF分類器"""
        from model_manager import load_records, open_model_manager, save_training_record
        
        # ========== 檢查並選擇 ResNet 模型 ==========
        records = load_records()
        resnet_records = [r for r in records if r.get('model_type') == 'ResNet']
        
        if not resnet_records:
            self.show_temp_message("請先訓練至少一個ResNet模型!", "red")
            return
        
        self.selected_resnet_model = None
        
        def select_resnet_callback(model_name, model_type):
            if model_type != "ResNet":
                messagebox.showerror("錯誤", "請選擇ResNet模型作為特徵萃取器")
                return
            self.selected_resnet_model = model_name
        
        messagebox.showinfo(
            "選擇基礎模型",
            f"請選擇一個ResNet模型作為{classifier_type.upper()}的特徵萃取器"
        )
        manager = open_model_manager(self.root, select_resnet_callback, select_type_only="ResNet")
        manager.window.wait_window()
        
        if not self.selected_resnet_model:
            self.show_temp_message("未選擇基礎ResNet模型", "red")
            return
        
        resnet_path = os.path.join(self.config.model_dir, f"{self.selected_resnet_model}.pth")
        if not os.path.exists(resnet_path):
            self.show_temp_message("ResNet模型檔案不存在!", "red")
            return
        
        # ========== 獲取模型名稱 ==========
        model_name = simpledialog.askstring(
            "模型名稱", 
            f"請輸入{classifier_type.upper()}模型名稱 (留空則自動生成):",
            parent=self.root
        )
        
        if model_name is None:
            return
        
        if not model_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_name = f"{classifier_type.upper()}_{timestamp}"
        
        model_path = os.path.join(self.config.model_dir, f"{model_name}.pkl")
        
        if os.path.exists(model_path):
            self.show_temp_message(f"模型 {model_name} 已存在!", "red")
            return
        
        # ========== 訓練 ==========
        self.progress_label.config(text=f"開始訓練 {classifier_type.upper()}...", fg="black")
        
        #  保存訓練集統計值
        train_stats = self.train_loader.dataset.stats
        
        try:
            from base_models import FeatureExtractor
            
            # 載入特徵萃取器
            feature_extractor = FeatureExtractor(
                pretrained_model_path=resnet_path,
                num_classes=self.config.class_num,
                device=self.config.device
            ).to(self.config.device)
            
            # 創建分類器
            if classifier_type == "xgboost":
                learning_rate = 0.1
                classifier = get_classifier(
                    'xgboost', n_estimators=200, max_depth=6, learning_rate=learning_rate
                )
            else:
                learning_rate = None
                classifier = get_classifier('rf', n_estimators=300, max_depth=12)
            
            # 訓練
            trainer = MLClassifierTrainer(feature_extractor, classifier, self.config.device)
            train_acc, val_acc = trainer.train(self.train_loader, self.val_loader)
            
            # 儲存模型
            dump(classifier, model_path)
            
            # 計算測試準確率
            test_acc = evaluate_ml_test_accuracy(
                feature_extractor, classifier, self.test_loader, self.config.device
            )
            
            #  儲存訓練紀錄（包含統計值）
            save_training_record(
                model_name=model_name,
                model_type=classifier_type.upper(),
                lr=0 if learning_rate is None else learning_rate,
                wd=0,
                batch_size=self.config.batch_size,
                val_acc=val_acc,
                test_acc=test_acc,
                note=f"基於ResNet:{self.selected_resnet_model}",
                train_stats=train_stats  #  傳入統計值
            )
            
            completion_text = (
                f"{classifier_type.upper()}模型 {model_name} 訓練完成！"
                f"驗證準確率: {val_acc:.4f}, 測試準確率: {test_acc:.4f}"
            )
            self.show_temp_message(completion_text, "green")
            self.progress_label.config(text=completion_text, fg="green")
            self.progress_bar["value"] = 100
            self.root.update()
            
        except Exception as e:
            traceback.print_exc()
            self.show_temp_message(f"{classifier_type.upper()}訓練失敗: {e}", "red")

    def test_model(self):
        """測試模型 - 開啟模型選擇視窗"""
        def select_model_callback(model_name, model_type):
            self.selected_test_model = (model_name, model_type)
            self._launch_test_gui(model_name, model_type)
        
        self.selected_test_model = None
        messagebox.showinfo("選擇模型", "請選擇要測試的模型")
        open_model_manager(self.root, select_model_callback)
    
    def _launch_test_gui(self, model_name, model_type):
        """啟動測試GUI"""
        
        # 模型路徑
        is_neural_net = model_type.upper() in [
            "RESNET", "MLP", 
            "MOBILENETV2", "MOBILENETV2_MLP",           
            "EFFICIENTNETB3", "EFFICIENTNETB3_MLP",     
            "CORALRESNET", "CORALMLP"
        ]
        
        model_path = os.path.join(
            self.config.model_dir,
            f"{model_name}.pth" if is_neural_net else f"{model_name}.pkl"
        )
        
        # 檢查模型是否存在
        if not os.path.exists(model_path):
            self.show_temp_message(f"找不到模型檔案: {model_path}", "red")
            return
        
        try:
            # 從模型紀錄中獲取統計值
            from model_manager import get_model_stats
            train_stats = get_model_stats(model_name)
            
            if train_stats:
                print(f"✓ 從模型紀錄中載入統計值")
            else:
                print(f"⚠️  模型 {model_name} 沒有統計值記錄")
                if model_type not in ['ResNet', 'CoralResNet', 'MobileNetV2', 'EfficientNetB3']:
                    self.show_temp_message(
                        f"警告: 模型 {model_name} 缺少統計值，推論結果可能不準確", 
                        "orange"
                    )
            
            # 創建推論 pipeline
            if model_type == "ResNet":
                inference = self._create_resnet_inference(model_path, train_stats)
            
            elif model_type == "MobileNetV2":  
                inference = self._create_mobilenetv2_inference(model_path, train_stats)
            
            elif model_type == "EfficientNetB3":  
                inference = self._create_efficientnetB3_inference(model_path, train_stats)
            
            elif model_type == "MLP":
                inference = self._create_mlp_inference(model_path, train_stats)
            
            elif model_type == "MobileNetV2_MLP":  
                inference = self._create_mobilenetv2_mlp_inference(model_path, train_stats)
            
            elif model_type == "EfficientNetB3_MLP":  
                inference = self._create_efficientnetB3_mlp_inference(model_path, train_stats)
            
            elif model_type == "CoralResNet":
                inference = self._create_coral_resnet_inference(model_path, train_stats)
            
            elif model_type == "CoralMLP":
                inference = self._create_coral_mlp_inference(model_path, train_stats)
            
            elif model_type.upper() == "XGBOOST":
                inference = self._create_xgboost_inference(model_name, model_path, train_stats)
            
            elif model_type.upper() == "RF":
                inference = self._create_rf_inference(model_name, model_path, train_stats)
            
            else:
                self.show_temp_message(f"不支援的模型類型: {model_type}", "red")
                return
            
            # 啟動測試GUI
            test_gui = launch_test_gui(
                inference_pipeline=inference,
                test_dir=self.config.test_images_path,
                metadata_path=self.config.metadata_path,
                model_type=model_type
            )
            self.show_temp_message(f"已開啟 {model_name} ({model_type}) 測試視窗", "green")
            
        except Exception as e:
            traceback.print_exc()
            self.show_temp_message(f"開啟測試視窗失敗: {e}", "red")
    
    def open_model_manager(self):
        """打開模型管理視窗"""
        open_model_manager(self.root)

    # ==================== 輔助方法：創建推論器 ====================
    def _load_default_train_stats(self):
        """載入預設統計值（若無則回傳 None）"""
        try:
            if os.path.exists(Config.train_stats_path):
                with open(Config.train_stats_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ 載入預設統計值失敗: {e}")
        return None
    
    def _create_resnet_inference(self, model_path, train_stats):
        """創建 ResNet 推論器"""
        from loader_inference import create_inference_pipeline
        
        # ResNet 不需要統計值，但為了統一接口還是傳入
        inference = create_inference_pipeline(
            model_type='resnet',
            model_path=model_path,
            device=self.config.device,
            train_stats=train_stats  #  傳入統計值字典
        )
        return inference


    def _create_mlp_inference(self, model_path, train_stats):
        """創建 MLP 推論器"""
        from loader_inference import create_inference_pipeline
        
        if not train_stats:
            train_stats = self._load_default_train_stats()
            if not train_stats:
                raise ValueError("MLP 模型需要統計值，但模型紀錄和預設路徑都沒有統計值")
        
        inference = create_inference_pipeline(
            model_type='mlp',
            model_path=model_path,
            device=self.config.device,
            train_stats=train_stats  #  傳入統計值字典
        )
        return inference


    def _create_coral_mlp_inference(self, model_path, train_stats):
        """創建 CORAL MLP 推論器"""
        from coral import create_coral_inference
        
        if not train_stats:
            train_stats = self._load_default_train_stats()
            if not train_stats:
                raise ValueError("MLP 模型需要統計值，但模型紀錄和預設路徑都沒有統計值")
        
        inference = create_coral_inference(
            model_type='mlp',
            model_path=model_path,
            num_classes=self.config.class_num,
            device=self.config.device,
            train_stats=train_stats  #  傳入統計值字典
        )
        return inference


    def _create_xgboost_inference(self, model_name, model_path, train_stats):
        """創建 XGBoost 推論器"""
        from model_manager import load_records
        from loader_inference import create_inference_pipeline
        
        if not train_stats:
            train_stats = self._load_default_train_stats()
            if not train_stats:
                raise ValueError("MLP 模型需要統計值，但模型紀錄和預設路徑都沒有統計值")

        
        # 獲取 backbone 資訊
        records = load_records()
        xgb_record = next((r for r in records if r['model_name'] == model_name), None)
        
        if not xgb_record or 'note' not in xgb_record:
            raise ValueError("無法找到 XGBoost 對應的 ResNet 模型")
        
        note = xgb_record['note']
        if '基於ResNet:' not in note:
            raise ValueError("無法解析 ResNet 模型名稱")
        
        backbone_name = note.split('基於ResNet:')[-1].strip()
        backbone_path = os.path.join(self.config.model_dir, f"{backbone_name}.pth")
        
        inference = create_inference_pipeline(
            model_type='xgboost',
            model_path=model_path,
            device=self.config.device,
            resnet_path=backbone_path,
            train_stats=train_stats  #  傳入統計值字典
        )
        return inference

    def _create_mobilenetv2_inference(self, model_path, train_stats):
        """創建 MobileNetV2 推論器"""
        from loader_inference import create_inference_pipeline
        
        inference = create_inference_pipeline(
            model_type='mobilenetv2',
            model_path=model_path,
            device=self.config.device,
            train_stats=train_stats
        )
        return inference


    # EfficientNet-B3 推論器
    def _create_efficientnetB3_inference(self, model_path, train_stats):
        """創建 EfficientNet-B3 推論器"""
        from loader_inference import create_inference_pipeline
        
        inference = create_inference_pipeline(
            model_type='efficientnetB3',
            model_path=model_path,
            device=self.config.device,
            train_stats=train_stats
        )
        return inference


    # MobileNetV2 + MLP 推論器
    def _create_mobilenetv2_mlp_inference(self, model_path, train_stats):
        """創建 MobileNetV2 + MLP 推論器"""
        from loader_inference import create_inference_pipeline
        
        if not train_stats:
            train_stats = self._load_default_train_stats()
            if not train_stats:
                raise ValueError("MLP 模型需要統計值，但模型紀錄和預設路徑都沒有統計值")
        
        inference = create_inference_pipeline(
            model_type='mobilenetv2_mlp',
            model_path=model_path,
            device=self.config.device,
            train_stats=train_stats
        )
        return inference


    # EfficientNet-B3 + MLP 推論器
    def _create_efficientnetB3_mlp_inference(self, model_path, train_stats):
        """創建 EfficientNet-B3 + MLP 推論器"""
        from loader_inference import create_inference_pipeline
        
        if not train_stats:
            train_stats = self._load_default_train_stats()
            if not train_stats:
                raise ValueError("MLP 模型需要統計值，但模型紀錄和預設路徑都沒有統計值")
        
        inference = create_inference_pipeline(
            model_type='efficientnetB3_mlp',
            model_path=model_path,
            device=self.config.device,
            train_stats=train_stats
        )
        return inference

# ==================== 主程式 ====================
def main():
    """主程式入口"""
    root = tk.Tk()
    app = TrainingGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()