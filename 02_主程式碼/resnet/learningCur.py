"""learningCur_Cur.py - 學習曲線分析器 (SCI 期刊等級圖表 + MLP 支援)"""
import sys
import os
import torch
import torch.nn as nn
import numpy as np
import random

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import ttk, messagebox
from torch.utils.data import DataLoader, Subset
from sklearn.model_selection import train_test_split
import json
from datetime import datetime

# 導入模型和資料載入函數
from base_models import BasicResNetClassifier, MLPClassifier, RewardPunishCrossEntropy
from loader_inference import get_dataloaders, get_class_weights
from trainer import Config, BasicResNetTrainer, MLPTrainer
from torchvision.datasets import ImageFolder
from torchvision import transforms

# ==================== SCI 期刊等級圖表設定 ====================
# 使用無襯線字體
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# 圖表樣式設定
JOURNAL_STYLE = {
    'figure.dpi': 300,
    'figure.figsize': (7.0, 5.0),
    'font.size': 13,
    'axes.labelsize': 14,
    'axes.titlesize': 15,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 12,
    'lines.linewidth': 1.7,
    'lines.markersize': 6,
    'axes.linewidth': 0.8,
    'grid.linewidth': 0.5,
    'grid.alpha': 0.5,
    'axes.grid': True,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'DejaVu Sans'],
}

# 黑白友善的樣式（不同線型和標記）
LINE_STYLES = [
    {'linestyle': '-', 'marker': 'o', 'color': 'black', 'label': 'Train'},
    {'linestyle': '--', 'marker': 's', 'color': 'dimgray', 'label': 'Val'},
    {'linestyle': '-.', 'marker': '^', 'color': 'gray', 'label': 'Test'},
]

METRIC_STYLES = [
    {'linestyle': '-', 'marker': 'o', 'color': 'black', 'label': 'Accuracy'},
    {'linestyle': '--', 'marker': 's', 'color': 'dimgray', 'label': 'F1-Score'},
]


def set_all_seeds(seed=42):
    """設置所有隨機種子"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    print(f"✓ All random seeds set to: {seed}")


def seed_worker(worker_id):
    """DataLoader worker 的種子初始化"""
    worker_seed = 42 + worker_id
    np.random.seed(worker_seed)
    random.seed(worker_seed)


class LearningCurveAnalyzer:
    """學習曲線分析器 - 支援 ResNet 和 MLP"""
    
    def __init__(self, dataset_path, model_dir, class_num=None, device='cuda', 
                 seed=42, model_type='resnet', metadata_path=None):
        self.dataset_path = dataset_path
        self.model_dir = model_dir
        self.class_num = Config.class_num if class_num is None else class_num
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.model_type = model_type.lower()  # 'resnet' or 'mlp'
        self.metadata_path = metadata_path
        
        # 驗證 MLP 必要參數
        if self.model_type == 'mlp' and metadata_path is None:
            raise ValueError("MLP model requires metadata_path parameter")
        
        # 超參數設定
        self.batch_size = Config.batch_size
        self.learning_rate = Config.learning_rate
        self.weight_decay = Config.weight_decay
        self.num_epochs = Config.num_epochs
        self.patience = Config.patience_epochs
        self.use_weighted_sampler = Config.use_weighted_sampler
        self.use_class_weights = Config.use_class_weights
        self.use_staged_training = Config.use_staged_training
        self.freeze_epochs = Config.freeze_epochs
        self.seed = seed
        set_all_seeds(self.seed)
        
        # 資料比例設定
        self.data_fractions = [0.2, 0.4, 0.6, 0.8, 1.0]
        
        # 建立學習曲線專用目錄
        self.lc_model_dir = os.path.join(self.model_dir, f"learning_curve_{self.model_type}")
        os.makedirs(self.lc_model_dir, exist_ok=True)
        
        # 結果儲存
        self.results = {
            'fractions': [],
            'train_sizes': [],
            'train_acc': [],
            'train_loss': [],
            'val_acc': [],
            'val_loss': [],
            'test_acc': [],
            'test_loss': [],
            'model_paths': []
        }
        
        print(f"✓ Initialized Learning Curve Analyzer")
        print(f"  Model type: {self.model_type.upper()}")
        print(f"  Classes: {self.class_num}")
        print(f"  Device: {self.device}")
    
    @staticmethod
    def load_checkpoint(model_path, model_type='resnet', device='cuda'):
        """載入已儲存的模型檢查點
        
        Args:
            model_path: 模型檔案路徑
            model_type: 'resnet' or 'mlp'
            device: 運算設備
            
        Returns:
            model: 載入權重的模型
            checkpoint: 包含訓練資訊的字典
        """
        checkpoint = torch.load(model_path, map_location=device)
        
        # 重建模型
        class_num = checkpoint['hyperparameters']['class_num']
        
        if model_type.lower() == 'resnet':
            model = BasicResNetClassifier(num_classes=class_num)
        elif model_type.lower() == 'mlp':
            meta_dim = checkpoint['hyperparameters'].get('meta_dim', Config.meta_dim)
            model = MLPClassifier(num_classes=class_num, meta_dim=meta_dim)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        model.load_state_dict(checkpoint['model_state_dict'])
        model.to(device)
        model.eval()
        
        print(f"Model loaded from: {model_path}")
        print(f"  Model type: {model_type.upper()}")
        print(f"  Data fraction: {checkpoint['fraction']*100:.0f}%")
        print(f"  Train size: {checkpoint['train_size']}")
        print(f"  Test Acc: {checkpoint['test_acc']:.4f}")
        print(f"  Trained at: {checkpoint['timestamp']}")
        
        return model, checkpoint
    
    def create_subset_loaders(self, fraction):
        """根據指定比例創建資料子集"""
        set_all_seeds(self.seed)
        g = torch.Generator()
        g.manual_seed(self.seed)
        
        def _build_loader(dataset, is_train):
            """Create DataLoader aligned with main.py sampler behavior."""
            num_workers = 0
            if self.use_weighted_sampler and is_train:
                # Build WeightedRandomSampler for the (possibly subset) dataset
                if isinstance(dataset, Subset):
                    labels = [dataset.dataset.samples[i][1] for i in dataset.indices]
                else:
                    labels = [label for _, label in dataset.samples]
                
                class_counts = np.bincount(labels, minlength=self.class_num)
                class_counts = np.maximum(class_counts, 1)
                class_weights = 1.0 / class_counts
                sample_weights = [class_weights[label] for label in labels]
                sample_weights = torch.DoubleTensor(sample_weights)
                
                sampler = torch.utils.data.WeightedRandomSampler(
                    weights=sample_weights,
                    num_samples=len(sample_weights),
                    replacement=True
                )
                
                return DataLoader(
                    dataset, batch_size=self.batch_size,
                    sampler=sampler, shuffle=False,
                    num_workers=num_workers, pin_memory=True, drop_last=True,
                    worker_init_fn=seed_worker if num_workers > 0 else None, generator=g
                )
            
            return DataLoader(
                dataset, batch_size=self.batch_size,
                shuffle=is_train, num_workers=num_workers, pin_memory=True,
                drop_last=is_train,
                worker_init_fn=seed_worker if num_workers > 0 else None, generator=g
            )
        
        # 資料增強
        train_transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ColorJitter(brightness=0.2, contrast=0.2),
            transforms.RandomRotation(degrees=20),
            transforms.RandomAffine(degrees=0, translate=(0.05,0.05), scale=(0.9,1.1), shear=5),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            transforms.RandomErasing(p=0.3, scale=(0.02, 0.15), ratio=(0.3, 3.3))
        ])
        
        eval_transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        # 根據模型類型載入資料
        if self.model_type == 'mlp':
            # 使用 get_dataloaders (支援 metadata)
            train_loader, test_loader, val_loader = get_dataloaders(
                self.dataset_path,
                self.metadata_path,
                self.batch_size,
                use_weighted_sampler=self.use_weighted_sampler,
                save_stats=False
            )
            
            # 創建訓練資料子集 (保持類別平衡)
            if fraction < 1.0:
                np.random.seed(self.seed)
                train_dataset = train_loader.dataset
                
                # 按類別分層抽樣
                # ImageFolderWithMeta.samples 格式: [(path, label), ...]
                indices_by_class = {}
                for idx in range(len(train_dataset)):
                    # 使用 __getitem__ 來獲取 label
                    _, _, label = train_dataset[idx]
                    label = label.item() if isinstance(label, torch.Tensor) else label
                    
                    if label not in indices_by_class:
                        indices_by_class[label] = []
                    indices_by_class[label].append(idx)
                
                subset_indices = []
                for label, indices in indices_by_class.items():
                    n_samples = int(len(indices) * fraction)
                    selected = np.random.choice(indices, size=n_samples, replace=False)
                    subset_indices.extend(selected)
                
                train_dataset = Subset(train_dataset, subset_indices)
                
                # 重建 train_loader
                train_loader = _build_loader(train_dataset, is_train=True)
        
        else:  # resnet
            train_dataset = ImageFolder(root=f"{self.dataset_path}/train", transform=train_transform)
            val_dataset = ImageFolder(root=f"{self.dataset_path}/val", transform=eval_transform)
            test_dataset = ImageFolder(root=f"{self.dataset_path}/test", transform=eval_transform)
            
            # 創建訓練資料子集
            if fraction < 1.0:
                np.random.seed(self.seed)
                indices_by_class = {}
                for idx, (_, label) in enumerate(train_dataset.samples):
                    if label not in indices_by_class:
                        indices_by_class[label] = []
                    indices_by_class[label].append(idx)
                
                subset_indices = []
                for label, indices in indices_by_class.items():
                    n_samples = int(len(indices) * fraction)
                    selected = np.random.choice(indices, size=n_samples, replace=False)
                    subset_indices.extend(selected)
                
                train_dataset = Subset(train_dataset, subset_indices)
            
            train_loader = _build_loader(train_dataset, is_train=True)
            val_loader = _build_loader(val_dataset, is_train=False)
            test_loader = _build_loader(test_dataset, is_train=False)
        
        return train_loader, val_loader, test_loader
    
    def train_and_evaluate(self, fraction, progress_callback=None):
        """訓練並評估模型"""
        set_all_seeds(self.seed)
        
        print(f"\n{'='*70}")
        print(f"Training {self.model_type.upper()} with {fraction*100:.0f}% of training data")
        print(f"{'='*70}")
        
        # 創建資料載入器
        train_loader, val_loader, test_loader = self.create_subset_loaders(fraction)
        train_size = len(train_loader.dataset)
        
        print(f"Training samples: {train_size}")
        
        # 初始化模型
        if self.model_type == 'mlp':
            model = MLPClassifier(num_classes=self.class_num, meta_dim=Config.meta_dim).to(self.device)
        else:
            model = BasicResNetClassifier(num_classes=self.class_num).to(self.device)
        
        optimizer = torch.optim.AdamW(model.parameters(),
                                     lr=self.learning_rate,
                                     weight_decay=self.weight_decay)
        
        # Align loss/weights behavior with main.py
        if self.class_num == 2:
            if self.use_class_weights and not self.use_weighted_sampler:
                class_weights = get_class_weights(train_loader, num_classes=self.class_num, device=self.device)
                pos_weight = class_weights[1] / class_weights[0]
                criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
            else:
                criterion = nn.BCEWithLogitsLoss()
        else:
            class_weights = None
            if self.use_class_weights and not self.use_weighted_sampler:
                class_weights = get_class_weights(train_loader, num_classes=self.class_num, device=self.device)
            
            if class_weights is not None:
                criterion = RewardPunishCrossEntropy(weight=class_weights, dist_penalty=0.7, label_smoothing=0.1)
            else:
                criterion = RewardPunishCrossEntropy(dist_penalty=0.7, label_smoothing=0.1)
        
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.8, patience=7, min_lr=1e-6
        )
        
        # 選擇訓練器
        if self.model_type == 'mlp':
            trainer = MLPTrainer(model, train_loader, val_loader, criterion, optimizer, self.device)
        else:
            trainer = BasicResNetTrainer(model, train_loader, val_loader, criterion, optimizer, self.device)
        
        # 訓練循環
        best_val_acc = 0.0
        best_val_f1 = 0.0
        best_model_state = None
        patience_counter = 0
        
        epoch_train_losses = []
        epoch_val_losses = []
        epoch_val_accs = []
        epoch_val_f1s = []
        
        def _batch_progress_callback(epoch, num_epochs, batch_idx, total_batches, *args):
            if progress_callback:
                progress_callback(fraction, epoch, num_epochs)

        for epoch in range(1, self.num_epochs + 1):
            # Training
            train_loss, train_acc = trainer.train_epoch(
                epoch,
                self.num_epochs,
                _batch_progress_callback if progress_callback else None
            )
            
            # Validation
            val_loss, val_acc, val_f1 = trainer.validate()
            
            # 記錄歷史
            epoch_train_losses.append(train_loss)
            epoch_val_losses.append(val_loss)
            epoch_val_accs.append(val_acc)
            epoch_val_f1s.append(val_f1)
            
            scheduler.step(val_loss)
            
            if epoch % 5 == 0:
                print(f"Epoch {epoch:>2}/{self.num_epochs} | "
                      f"Train Loss: {train_loss:.4f}, Acc: {train_acc:.4f} | "
                      f"Val Loss: {val_loss:.4f}, Acc: {val_acc:.4f}, F1: {val_f1:.4f}")
            
            # 儲存最佳模型
            best_val_acc = max(best_val_acc, val_acc)
            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_model_state = model.state_dict().copy()
                patience_counter = 0
            else:
                patience_counter += 1
            
            if patience_counter >= self.patience:
                print(f"Early stopping at epoch {epoch}")
                break
            
            if progress_callback:
                progress_callback(fraction, epoch, self.num_epochs)
        
        # 載入最佳模型進行測試
        if best_model_state is not None:
            model.load_state_dict(best_model_state)
        
        # Test phase
        model.eval()
        test_loss = 0.0
        test_correct = 0
        test_total = 0
        
        with torch.no_grad():
            for batch in test_loader:
                if self.model_type == 'mlp':
                    inputs, meta, labels = batch
                    inputs = inputs.to(self.device, non_blocking=True)
                    meta = meta.to(self.device, non_blocking=True)
                    labels = labels.to(self.device, non_blocking=True).long()
                    outputs = model(inputs, meta)
                else:
                    inputs, labels = batch
                    inputs = inputs.to(self.device, non_blocking=True)
                    labels = labels.to(self.device, non_blocking=True).long()
                    outputs = model(inputs)
                
                loss = criterion(outputs, labels)
                _, preds = torch.max(outputs, 1)
                test_loss += loss.item() * inputs.size(0)
                test_correct += (preds == labels).sum().item()
                test_total += labels.size(0)
        
        test_loss = test_loss / test_total
        test_acc = test_correct / test_total
        
        # 繪製並儲存此次訓練的曲線圖
        self.save_training_curves(fraction, epoch_train_losses, epoch_val_losses, 
                                 epoch_val_accs, epoch_val_f1s)
        
        # 儲存模型
        model_filename = f"{self.model_type}_data_{int(fraction*100)}percent.pth"
        model_path = os.path.join(self.lc_model_dir, model_filename)
        
        save_dict = {
            'model_state_dict': best_model_state,
            'fraction': fraction,
            'train_size': train_size,
            'train_acc': train_acc,
            'val_acc': best_val_acc,
            'test_acc': test_acc,
            'training_history': {
                'train_losses': epoch_train_losses,
                'val_losses': epoch_val_losses,
                'val_accs': epoch_val_accs,
                'val_f1s': epoch_val_f1s
            },
            'seed': self.seed,
            'hyperparameters': {
                'class_num': self.class_num,
                'batch_size': self.batch_size,
                'learning_rate': self.learning_rate,
                'weight_decay': self.weight_decay,
                'num_epochs': self.num_epochs,
                'seed': self.seed,
                'model_type': self.model_type
            },
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if self.model_type == 'mlp':
            save_dict['hyperparameters']['meta_dim'] = Config.meta_dim
        
        # 只存模型權重
        torch.save(model.state_dict(), model_path)
        
        print(f"\nResults for {fraction*100:.0f}% data:")
        print(f"  Train Acc: {train_acc:.4f}")
        print(f"  Val Acc:   {best_val_acc:.4f}")
        print(f"  Test Acc:  {test_acc:.4f}")
        print(f"  Model saved to: {model_path}")
        
        return {
            'train_size': train_size,
            'train_acc': train_acc,
            'train_loss': train_loss,
            'val_acc': best_val_acc,
            'val_loss': val_loss,
            'test_acc': test_acc,
            'test_loss': test_loss,
            'model_path': model_path
        }
    
    def save_training_curves(self, fraction, train_losses, val_losses, val_accs, val_f1s):
        """儲存單次訓練的曲線圖 (SCI 期刊等級)"""
        # 應用期刊樣式
        plt.style.use('default')
        for key, value in JOURNAL_STYLE.items():
            plt.rcParams[key] = value
        
        fig, axes = plt.subplots(1, 2, figsize=(7, 3))
        
        epochs = np.arange(1, len(train_losses) + 1)
        
        # 左圖: Loss curves
        ax1 = axes[0]
        ax1.plot(epochs, train_losses, '-', color='black', linewidth=1.5, 
                marker='o', markersize=4, markevery=max(1, len(epochs)//10),
                label='Train set')
        ax1.plot(epochs, val_losses, '--', color='dimgray', linewidth=1.5,
                marker='s', markersize=4, markevery=max(1, len(epochs)//10),
                label='Validation set')
        ax1.set_xlabel('Epoch', fontsize=11)
        ax1.set_ylabel('Cross-Entropy Loss', fontsize=11)
        ax1.set_title(f'({fraction*100:.0f}% Training Data)', fontsize=11, pad=10)
        ax1.legend(loc='upper right', frameon=True, fontsize=9)
        ax1.grid(True, alpha=0.3, linestyle=':')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        
        # 右圖: Accuracy & F1
        ax2 = axes[1]
        ax2.plot(epochs, val_accs, '-', color='black', linewidth=1.5,
                marker='o', markersize=4, markevery=max(1, len(epochs)//10),
                label='Accuracy')
        ax2.plot(epochs, val_f1s, '--', color='dimgray', linewidth=1.5,
                marker='s', markersize=4, markevery=max(1, len(epochs)//10),
                label='Macro F1-Score')
        ax2.set_xlabel('Epoch', fontsize=11)
        ax2.set_ylabel('Performance Metric', fontsize=11)
        ax2.set_title('Validation Metrics', fontsize=11, pad=10)
        ax2.set_ylim([0, 1.05])
        ax2.legend(loc='lower right', frameon=True, fontsize=9)
        ax2.grid(True, alpha=0.3, linestyle=':')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        # 儲存高解析度圖表
        curve_filename = f"training_curve_{int(fraction*100)}percent.png"
        curve_path = os.path.join(self.lc_model_dir, curve_filename)
        plt.savefig(curve_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        print(f"  Training curves saved to: {curve_path}")
    
    def run_analysis(self, progress_callback=None):
        """執行完整的學習曲線分析"""
        for fraction in self.data_fractions:
            result = self.train_and_evaluate(fraction, progress_callback)
            
            self.results['fractions'].append(fraction)
            self.results['train_sizes'].append(result['train_size'])
            self.results['train_acc'].append(result['train_acc'])
            self.results['train_loss'].append(result['train_loss'])
            self.results['val_acc'].append(result['val_acc'])
            self.results['val_loss'].append(result['val_loss'])
            self.results['test_acc'].append(result['test_acc'])
            self.results['test_loss'].append(result['test_loss'])
            self.results['model_paths'].append(result['model_path'])
            
            torch.cuda.empty_cache()
        
        print(f"\n{'='*70}")
        print("All models and training curves saved in:")
        print(f"  {self.lc_model_dir}")
        print(f"\nTotal models: {len(self.results['model_paths'])}")
        for i, path in enumerate(self.results['model_paths']):
            print(f"  [{i+1}] {os.path.basename(path)}")
        print(f"{'='*70}")
        
        return self.results
    
    def save_results(self, save_path=None):
        """儲存分析結果"""
        if save_path is None:
            save_path = os.path.join(self.model_dir, f"learning_curve_{self.model_type}_results.json")
        
        results_with_metadata = {
            'metadata': {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'model_type': self.model_type,
                'class_num': self.class_num,
                'batch_size': self.batch_size,
                'learning_rate': self.learning_rate,
                'weight_decay': self.weight_decay,
                'num_epochs': self.num_epochs,
                'device': str(self.device),
                'seed': self.seed
            },
            'results': self.results
        }
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(results_with_metadata, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to: {save_path}")
    
    def plot_learning_curves(self, save_path=None):
        """繪製學習曲線 (SCI 期刊等級) - 四個獨立圖表"""
        # 應用期刊樣式
        plt.style.use('default')
        for key, value in JOURNAL_STYLE.items():
            plt.rcParams[key] = value
        
        train_sizes = np.array(self.results['train_sizes'])
        fractions = np.array(self.results['fractions'])
        
        # 確定儲存目錄
        if save_path is None:
            save_dir = self.lc_model_dir
        else:
            save_dir = os.path.dirname(save_path)
        
        # ==================== 圖表 1: Accuracy ====================
        fig1, ax1 = plt.subplots(figsize=(7, 5))
        ax1.plot(train_sizes, self.results['train_acc'], '-o', color='black', 
                linewidth=1.5, markersize=5, label='Train set')
        ax1.plot(train_sizes, self.results['val_acc'], '--s', color='dimgray',
                linewidth=1.5, markersize=5, label='Validation set')
        ax1.plot(train_sizes, self.results['test_acc'], '-.^', color='gray',
                linewidth=1.5, markersize=5, label='Test set')
        ax1.set_xlabel('Training Set Size (samples)', fontsize=11)
        ax1.set_ylabel('Classification Accuracy', fontsize=11)
        ax1.set_title('Model Accuracy vs Training Data Size', fontsize=12, fontweight='bold', pad=10)
        ax1.legend(loc='lower right', frameon=True, fontsize=9)
        ax1.grid(True, alpha=0.3, linestyle=':')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        plt.tight_layout()
        
        acc_png = os.path.join(save_dir, f"{self.model_type}_accuracy.png")
        acc_pdf = os.path.join(save_dir, f"{self.model_type}_accuracy.pdf")
        fig1.savefig(acc_png, dpi=300, bbox_inches='tight', facecolor='white')
        fig1.savefig(acc_pdf, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig1)
        print(f"✅ Accuracy plot saved: {acc_png} & {acc_pdf}")
        
        # ==================== 圖表 2: Loss ====================
        fig2, ax2 = plt.subplots(figsize=(7, 5))
        ax2.plot(train_sizes, self.results['train_loss'], '-o', color='black',
                linewidth=1.5, markersize=5, label='Training')
        ax2.plot(train_sizes, self.results['val_loss'], '--s', color='dimgray',
                linewidth=1.5, markersize=5, label='Validation')
        ax2.plot(train_sizes, self.results['test_loss'], '-.^', color='gray',
                linewidth=1.5, markersize=5, label='Test')
        ax2.set_xlabel('Training Set Size (samples)', fontsize=11)
        ax2.set_ylabel('Cross-Entropy Loss', fontsize=11)
        ax2.set_title('Model Loss vs Training Data Size', fontsize=12, fontweight='bold', pad=10)
        ax2.legend(loc='upper right', frameon=True, fontsize=9)
        ax2.grid(True, alpha=0.3, linestyle=':')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        plt.tight_layout()
        
        loss_png = os.path.join(save_dir, f"{self.model_type}_loss.png")
        loss_pdf = os.path.join(save_dir, f"{self.model_type}_loss.pdf")
        fig2.savefig(loss_png, dpi=300, bbox_inches='tight', facecolor='white')
        fig2.savefig(loss_pdf, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig2)
        print(f"✅ Loss plot saved: {loss_png} & {loss_pdf}")
        
        # ==================== 圖表 3: Generalization Gap ====================
        fig3, ax3 = plt.subplots(figsize=(7, 5))
        gap = np.array(self.results['train_acc']) - np.array(self.results['val_acc'])
        ax3.plot(train_sizes, gap, '-o', linewidth=1.5, markersize=5, color='black')
        ax3.axhline(y=0, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax3.set_xlabel('Training Set Size (samples)', fontsize=11)
        ax3.set_ylabel('Generalization Gap (Training - Validation Acc.)', fontsize=11)
        ax3.set_title('Overfitting Analysis', fontsize=12, fontweight='bold', pad=10)
        ax3.grid(True, alpha=0.3, linestyle=':')
        ax3.spines['top'].set_visible(False)
        ax3.spines['right'].set_visible(False)
        plt.tight_layout()
        
        gap_png = os.path.join(save_dir, f"{self.model_type}_generalization_gap.png")
        gap_pdf = os.path.join(save_dir, f"{self.model_type}_generalization_gap.pdf")
        fig3.savefig(gap_png, dpi=300, bbox_inches='tight', facecolor='white')
        fig3.savefig(gap_pdf, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig3)
        print(f"✅ Generalization gap plot saved: {gap_png} & {gap_pdf}")
        
        # ==================== 圖表 4: Marginal Improvement ====================
        fig4, ax4 = plt.subplots(figsize=(7, 5))
        test_acc = np.array(self.results['test_acc'])
        marginal = np.diff(test_acc, prepend=test_acc[0])
        colors = ['black' if m > 0 else 'gray' for m in marginal]
        bars = ax4.bar(range(len(train_sizes)), marginal, color=colors, 
                      alpha=0.7, edgecolor='black', linewidth=0.8)
        ax4.axhline(y=0, color='black', linestyle='-', alpha=0.8, linewidth=0.8)
        ax4.set_xlabel('Training Data Fraction', fontsize=11)
        ax4.set_ylabel('Marginal Accuracy Gain', fontsize=11)
        ax4.set_title('Diminishing Returns Analysis', fontsize=12, fontweight='bold', pad=10)
        ax4.set_xticks(range(len(fractions)))
        ax4.set_xticklabels([f"{int(f*100)}%" for f in fractions])
        ax4.grid(True, alpha=0.3, linestyle=':', axis='y')
        ax4.spines['top'].set_visible(False)
        ax4.spines['right'].set_visible(False)
        plt.tight_layout()
        
        marginal_png = os.path.join(save_dir, f"{self.model_type}_marginal_improvement.png")
        marginal_pdf = os.path.join(save_dir, f"{self.model_type}_marginal_improvement.pdf")
        fig4.savefig(marginal_png, dpi=300, bbox_inches='tight', facecolor='white')
        fig4.savefig(marginal_pdf, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig4)
        print(f"✅ Marginal improvement plot saved: {marginal_png} & {marginal_pdf}")
        
        print(f"\n✅ All 4 learning curve plots saved to: {save_dir}/")
        print(f"   Files: {self.model_type}_accuracy, {self.model_type}_loss,")
        print(f"          {self.model_type}_generalization_gap, {self.model_type}_marginal_improvement")
        print(f"   Formats: PNG + PDF for each")
        
        return None  # 不返回 figure (已關閉所有圖形)
    
    def analyze_results(self):
        """分析結果並給出建議"""
        test_acc = np.array(self.results['test_acc'])
        train_sizes = np.array(self.results['train_sizes'])
        
        last_3_improvements = np.diff(test_acc[-3:])
        avg_improvement = np.mean(last_3_improvements)
        
        current_acc = test_acc[-1]
        final_gap = self.results['train_acc'][-1] - self.results['val_acc'][-1]
        
        print("\n" + "="*70)
        print(f"LEARNING CURVE ANALYSIS - {self.model_type.upper()} MODEL")
        print("="*70)
        
        print(f"\n📊 Current Performance (100% data):")
        print(f"   - Test Accuracy: {current_acc:.4f}")
        print(f"   - Generalization Gap: {final_gap:.4f}")
        
        print(f"\n📈 Data Efficiency:")
        total_improvement = test_acc[-1] - test_acc[0]
        print(f"   - Total improvement (20% → 100%): {total_improvement:.4f}")
        print(f"   - Average recent improvement: {avg_improvement:.4f}")
        
        print(f"\n💡 Recommendations:")
        
        if avg_improvement > 0.02:
            print("   ✅ COLLECT MORE DATA")
            print("      Model still benefits significantly from additional data")
            print(f"      Expected gain if doubling data: ~{avg_improvement*3:.4f}")
        elif avg_improvement > 0.01:
            print("   ⚠️  CONSIDER MORE DATA")
            print("      Model shows diminishing returns")
            print("      Suggest: Improve data quality or model architecture")
        else:
            print("   ⛔ REACHED DATA SATURATION")
            print("      Additional data provides minimal improvement")
            print("      Recommended actions:")
            print("      - Enhance data quality")
            print("      - Use larger model architecture")
            print("      - Apply advanced training strategies")
        
        if final_gap > 0.1:
            print(f"\n   ⚠️  High generalization gap detected ({final_gap:.4f})")
            print("      Overfitting concerns - consider:")
            print("      - Stronger regularization")
            print("      - More aggressive data augmentation")
            print("      - Collect more validation data")
        
        print("\n" + "="*70)


class LearningCurveGUI:
    """學習曲線分析 GUI (支援 ResNet 和 MLP)"""
    
    def __init__(self, dataset_path, model_dir, metadata_path=None, 
                 class_num=None, seed=42):
        self.dataset_path = dataset_path
        self.model_dir = model_dir
        self.metadata_path = metadata_path
        self.class_num = Config.class_num if class_num is None else class_num
        self.seed = seed
        set_all_seeds(self.seed)
        
        self.root = tk.Tk()
        self.root.title("Learning Curve Analysis - ResNet & MLP")
        self.root.geometry("1200x800")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.model_type = tk.StringVar(value="ResNet")
        self.analyzer = None
        
        self.setup_gui()
    
    def on_close(self):
        """安全退出"""
        if messagebox.askokcancel("Exit", "Are you sure you want to exit?"):
            if self.root.winfo_exists():
                self.root.destroy()
            print("Exiting safely...")
            sys.exit(0)
    
    def setup_gui(self):
        # 左側控制面板
        left_frame = tk.Frame(self.root, bg="#e0e0e0", width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        left_frame.pack_propagate(False)
        
        # 標題
        title = tk.Label(left_frame, text="Learning Curve\nAnalysis", 
                        font=("Arial", 16, "bold"), bg="#e0e0e0")
        title.pack(pady=20)
        
        # 模型選擇
        model_frame = tk.LabelFrame(left_frame, text="Model Type", 
                                   font=("Arial", 12, "bold"), bg="#e0e0e0")
        model_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Radiobutton(model_frame, text="ResNet (Image only)", 
                      variable=self.model_type, value="ResNet",
                      bg="#e0e0e0", font=("Arial", 10)).pack(anchor="w", padx=10, pady=2)
        tk.Radiobutton(model_frame, text="MLP (Image + Metadata)", 
                      variable=self.model_type, value="MLP",
                      bg="#e0e0e0", font=("Arial", 10)).pack(anchor="w", padx=10, pady=2)
        
        # 設定區域
        settings_frame = tk.LabelFrame(left_frame, text="Settings", 
                                      font=("Arial", 12, "bold"), bg="#e0e0e0")
        settings_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Epochs
        tk.Label(settings_frame, text="Epochs per run:", bg="#e0e0e0").pack(
            anchor="w", padx=10, pady=5)
        self.epochs_var = tk.StringVar(value="20")
        tk.Entry(settings_frame, textvariable=self.epochs_var, width=10).pack(
            padx=10, pady=5)
        
        # Seed
        tk.Label(settings_frame, text="Random Seed:", bg="#e0e0e0").pack(
            anchor="w", padx=10, pady=5)
        self.seed_var = tk.StringVar(value=str(self.seed))
        tk.Entry(settings_frame, textvariable=self.seed_var, width=10).pack(
            padx=10, pady=5)
        
        # 預覽範例按鈕
        self.preview_btn = tk.Button(left_frame, text="Preview Sample Chart", 
                                     command=self.show_sample_chart,
                                     bg="lightyellow", font=("Arial", 12, "bold"),
                                     width=20, height=2)
        self.preview_btn.pack(pady=10)
        
        # 開始分析按鈕
        self.start_btn = tk.Button(left_frame, text="Start Analysis", 
                                   command=self.start_analysis,
                                   bg="lightblue", font=("Arial", 14, "bold"),
                                   width=20, height=2)
        self.start_btn.pack(pady=10)
        
        # 進度顯示
        self.progress_label = tk.Label(left_frame, text="Ready", 
                                      font=("Arial", 11), bg="#e0e0e0")
        self.progress_label.pack(pady=10)
        
        self.progress_bar = ttk.Progressbar(left_frame, mode='determinate', length=250)
        self.progress_bar.pack(pady=10)
        
        # 結果顯示
        result_frame = tk.LabelFrame(left_frame, text="Quick Results", 
                                    font=("Arial", 11, "bold"), bg="#e0e0e0")
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.result_text = tk.Text(result_frame, height=15, width=30, 
                                   font=("Courier", 9), bg="white")
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 右側圖表區域
        right_frame = tk.Frame(self.root, bg="white")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.fig, self.axes = plt.subplots(2, 2, figsize=(10, 8))
        self.fig.suptitle('Learning Curve Analysis', fontsize=14, fontweight='bold')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def show_sample_chart(self):
        """顯示範例圖表，讓使用者預覽最終結果樣式"""
        # 應用期刊樣式
        plt.style.use('default')
        for key, value in JOURNAL_STYLE.items():
            plt.rcParams[key] = value
        
        # 生成模擬資料
        np.random.seed(42)
        train_sizes = np.array([200, 400, 600, 800, 1000])
        fractions = np.array([0.2, 0.4, 0.6, 0.8, 1.0])
        
        # 模擬準確率曲線 (漸進收斂)
        train_acc = 0.95 - 0.15 * np.exp(-fractions * 2.5) + np.random.normal(0, 0.01, 5)
        val_acc = 0.85 - 0.18 * np.exp(-fractions * 2.2) + np.random.normal(0, 0.015, 5)
        test_acc = 0.83 - 0.17 * np.exp(-fractions * 2.0) + np.random.normal(0, 0.015, 5)
        
        # 模擬損失曲線 (遞減)
        train_loss = 0.5 * np.exp(-fractions * 1.8) + 0.05 + np.random.normal(0, 0.01, 5)
        val_loss = 0.6 * np.exp(-fractions * 1.5) + 0.08 + np.random.normal(0, 0.015, 5)
        test_loss = 0.62 * np.exp(-fractions * 1.4) + 0.09 + np.random.normal(0, 0.015, 5)
        
        # 清除現有圖表
        for ax in self.axes.flat:
            ax.clear()
        
        # (a) Accuracy
        ax1 = self.axes[0, 0]
        ax1.plot(train_sizes, train_acc, '-o', color='black', linewidth=1.5, 
                markersize=5, label='Train set')
        ax1.plot(train_sizes, val_acc, '--s', color='dimgray', linewidth=1.5,
                markersize=5, label='Validation set')
        ax1.plot(train_sizes, test_acc, '-.^', color='gray', linewidth=1.5,
                markersize=5, label='Test set')
        ax1.set_xlabel('Training Set Size (samples)', fontsize=10)
        ax1.set_ylabel('Classification Accuracy', fontsize=10)
        ax1.set_title('(a) Model Accuracy', fontsize=11, fontweight='bold', pad=8)
        ax1.legend(loc='lower right', frameon=True, fontsize=8)
        ax1.grid(True, alpha=0.3, linestyle=':')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.set_ylim([0.6, 1.0])
        
        # (b) Loss
        ax2 = self.axes[0, 1]
        ax2.plot(train_sizes, train_loss, '-o', color='black', linewidth=1.5,
                markersize=5, label='Training')
        ax2.plot(train_sizes, val_loss, '--s', color='dimgray', linewidth=1.5,
                markersize=5, label='Validation')
        ax2.plot(train_sizes, test_loss, '-.^', color='gray', linewidth=1.5,
                markersize=5, label='Test')
        ax2.set_xlabel('Training Set Size (samples)', fontsize=10)
        ax2.set_ylabel('Cross-Entropy Loss', fontsize=10)
        ax2.set_title('(b) Model Loss', fontsize=11, fontweight='bold', pad=8)
        ax2.legend(loc='upper right', frameon=True, fontsize=8)
        ax2.grid(True, alpha=0.3, linestyle=':')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        
        # (c) Generalization Gap
        ax3 = self.axes[1, 0]
        gap = train_acc - val_acc
        ax3.plot(train_sizes, gap, '-o', linewidth=1.5, markersize=5, color='black')
        ax3.axhline(y=0, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax3.set_xlabel('Training Set Size (samples)', fontsize=10)
        ax3.set_ylabel('Generalization Gap\n(Train - Val Acc.)', fontsize=10)
        ax3.set_title('(c) Overfitting Analysis', fontsize=11, fontweight='bold', pad=8)
        ax3.grid(True, alpha=0.3, linestyle=':')
        ax3.spines['top'].set_visible(False)
        ax3.spines['right'].set_visible(False)
        
        # (d) Marginal Improvement
        ax4 = self.axes[1, 1]
        marginal = np.diff(test_acc, prepend=test_acc[0])
        colors = ['black' if m > 0 else 'gray' for m in marginal]
        ax4.bar(range(len(train_sizes)), marginal, color=colors, 
               alpha=0.7, edgecolor='black', linewidth=0.8)
        ax4.axhline(y=0, color='black', linestyle='-', alpha=0.8, linewidth=0.8)
        ax4.set_xlabel('Training Data Fraction', fontsize=10)
        ax4.set_ylabel('Marginal Accuracy Gain', fontsize=10)
        ax4.set_title('(d) Diminishing Returns', fontsize=11, fontweight='bold', pad=8)
        ax4.set_xticks(range(len(fractions)))
        ax4.set_xticklabels([f"{int(f*100)}%" for f in fractions])
        ax4.grid(True, alpha=0.3, linestyle=':', axis='y')
        ax4.spines['top'].set_visible(False)
        ax4.spines['right'].set_visible(False)
        
        self.fig.suptitle('Sample Learning Curve (Journal-Ready Style)', 
                         fontsize=13, fontweight='bold', y=0.98)
        plt.tight_layout()
        self.canvas.draw()
        
        # 更新結果文字
        self.result_text.delete(1.0, tk.END)
        sample_text = (
            "SAMPLE PREVIEW\n"
            "="*35 + "\n\n"
            "This is how your final\n"
            "charts will look:\n\n"
            "✓ Black & white scheme\n"
            "✓ Different line styles\n"
            "✓ Clear markers\n"
            "✓ Professional labels\n"
            "✓ Journal-ready format\n\n"
            "Features:\n"
            "• 300 DPI resolution\n"
            "• PNG + PDF outputs\n"
            "• English labels\n"
            "• Clean design\n"
            "• 4 separate plots\n\n"
            "Ready to start training?\n"
        )
        self.result_text.insert(tk.END, sample_text)
        
        # 顯示提示訊息
        messagebox.showinfo(
            "Sample Preview", 
            "This is a sample chart showing the journal-ready style.\n\n"
            "Your actual results will:\n"
            "• Use your real training data\n"
            "• Include 5 data points (20%, 40%, 60%, 80%, 100%)\n"
            "• Save each plot as separate PNG and PDF files\n"
            "• Include detailed analysis reports\n\n"
            "Output: 4 individual plots for flexible use in papers.\n"
            "Click 'Start Analysis' when ready to begin training."
        )
    
    def update_progress(self, fraction, epoch, total_epochs):
        """更新進度"""
        # 假設有 5 個 fraction
        fraction_idx = [0.2, 0.4, 0.6, 0.8, 1.0].index(fraction)
        total_fractions = 5
        progress = (fraction_idx + epoch/total_epochs) / total_fractions * 100
        
        self.progress_bar['value'] = progress
        self.progress_label.config(
            text=f"Training {self.model_type.get()} with {fraction*100:.0f}% data\n"
                 f"Epoch {epoch}/{total_epochs}"
        )
        self.root.update()
    
    def start_analysis(self):
        """開始分析"""
        self.start_btn.config(state=tk.DISABLED)
        self.result_text.delete(1.0, tk.END)
        
        try:
            seed = int(self.seed_var.get())
            epochs = int(self.epochs_var.get())
            model_type = self.model_type.get().lower()
            
            # 驗證 MLP 所需參數
            if model_type == 'mlp' and self.metadata_path is None:
                messagebox.showerror("Error", 
                    "MLP model requires metadata_path!\n"
                    "Please provide metadata CSV file path when initializing GUI.")
                return
            
            # 創建分析器
            self.analyzer = LearningCurveAnalyzer(
                dataset_path=self.dataset_path,
                model_dir=self.model_dir,
                class_num=self.class_num,
                seed=seed,
                model_type=model_type,
                metadata_path=self.metadata_path
            )
            self.analyzer.num_epochs = epochs
            
            # 執行分析
            self.analyzer.run_analysis(progress_callback=self.update_progress)
            
            # 繪製即時圖表
            self.plot_results()
            
            # 儲存結果
            self.analyzer.save_results()
            
            # 儲存 Learning Curve 總覽圖
            self.analyzer.plot_learning_curves()
            
            # 顯示分析結果
            self.show_analysis()
            
            messagebox.showinfo("Complete", 
                "Learning curve analysis completed!\n\n"
                "Saved:\n"
                "• Model checkpoints\n"
                "• Training curves (PNG + PDF)\n"
                "• Summary plots (PNG + PDF)\n"
                "• Analysis results (JSON)")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Analysis failed: {e}")
        finally:
            self.start_btn.config(state=tk.NORMAL)
            self.progress_label.config(text="Analysis Complete")
    
    def plot_results(self):
        """即時繪製結果"""
        if self.analyzer is None:
            return
        
        results = self.analyzer.results
        
        for ax in self.axes.flat:
            ax.clear()
        
        # Accuracy
        ax1 = self.axes[0, 0]
        if results['train_sizes']:
            ax1.plot(results['train_sizes'], results['train_acc'], 'o-', label='Train')
            ax1.plot(results['train_sizes'], results['val_acc'], 's-', label='Val')
            ax1.plot(results['train_sizes'], results['test_acc'], '^-', label='Test')
        ax1.set_xlabel('Training Size')
        ax1.set_ylabel('Accuracy')
        ax1.set_title('Accuracy vs Data Size')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Loss
        ax2 = self.axes[0, 1]
        if results['train_sizes']:
            ax2.plot(results['train_sizes'], results['train_loss'], 'o-', label='Train')
            ax2.plot(results['train_sizes'], results['val_loss'], 's-', label='Val')
            ax2.plot(results['train_sizes'], results['test_loss'], '^-', label='Test')
        ax2.set_xlabel('Training Size')
        ax2.set_ylabel('Loss')
        ax2.set_title('Loss vs Data Size')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Gap
        ax3 = self.axes[1, 0]
        if results['train_sizes']:
            gap = np.array(results['train_acc']) - np.array(results['val_acc'])
            ax3.plot(results['train_sizes'], gap, 'o-', color='orangered')
        ax3.axhline(y=0, color='black', linestyle='--', alpha=0.3)
        ax3.set_xlabel('Training Size')
        ax3.set_ylabel('Train - Val Acc')
        ax3.set_title('Generalization Gap')
        ax3.grid(True, alpha=0.3)
        
        # Marginal
        ax4 = self.axes[1, 1]
        if results['test_acc']:
            test_acc = np.array(results['test_acc'])
            marginal = np.diff(test_acc, prepend=test_acc[0])
            colors = ['green' if m > 0 else 'red' for m in marginal]
            ax4.bar(range(len(results['train_sizes'])), marginal, 
                   color=colors, alpha=0.7)
            ax4.set_xticks(range(len(results['fractions'])))
            ax4.set_xticklabels([f"{int(f*100)}%" for f in results['fractions']])
        ax4.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax4.set_xlabel('Data Fraction')
        ax4.set_ylabel('Marginal Gain')
        ax4.set_title('Diminishing Returns')
        ax4.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        self.canvas.draw()
    
    def show_analysis(self):
        """顯示分析結果"""
        if self.analyzer is None:
            return
        
        results = self.analyzer.results
        test_acc = np.array(results['test_acc'])
        
        text = f"ANALYSIS - {self.model_type.get()}\n"
        text += "="*35 + "\n\n"
        text += f"Final Test Acc: {test_acc[-1]:.4f}\n"
        text += f"Total Gain: {test_acc[-1] - test_acc[0]:.4f}\n\n"
        
        last_3 = np.diff(test_acc[-3:])
        avg_gain = np.mean(last_3)
        
        text += f"Recent Trend: {avg_gain:.4f}\n\n"
        
        if avg_gain > 0.02:
            text += "✅ COLLECT MORE DATA\n"
        elif avg_gain > 0.01:
            text += "⚠️  CONSIDER MORE DATA\n"
        else:
            text += "⛔ DATA SATURATED\n"
        
        self.result_text.insert(tk.END, text)
    
    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    SEED = 32008
    set_all_seeds(SEED)
    
    # 設定路徑
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    dataset_path = os.path.join(PROJECT_ROOT, "IMG", "IMG_train", "method2")
    model_dir = os.path.join(PROJECT_ROOT, "model")
    metadata_path = os.path.join(model_dir, "features", "metadata.csv")
    
    # 啟動 GUI
    gui = LearningCurveGUI(
        dataset_path=dataset_path,
        model_dir=model_dir,
        metadata_path=metadata_path,  # MLP 需要
        class_num=Config.class_num,
        seed=SEED
    )
    gui.run()
