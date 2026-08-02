"""
trainer.py - 統一訓練器
支援四種訓練模式: ResNet, MLP, XGBoost, RandomForest
"""
import os
import torch
import torch.nn as nn
import time
import copy
import random
import numpy as np
from sklearn.metrics import f1_score
from tqdm import tqdm

def seed_worker(worker_id):
    """DataLoader worker 的種子初始化函數"""
    worker_seed = Config.SEED + worker_id
    np.random.seed(worker_seed)
    random.seed(worker_seed)

# ==================== 統一配置管理 ====================
class Config:
    """統一配置管理"""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    _printed = False  # 用於避免重複打印初始化訊息
    
    # ==================== 隨機種子設置 ====================
    #random_number = random.SystemRandom().randint(0, 100000)
    #print(f"✓ 生成隨機種子: {random_number}")
    SEED = 32008  # 統一的隨機種子
    #8892
    #32008
    #8423<32008

    @classmethod
    def set_seed(cls, seed=None):
        """設置所有隨機種子以確保可重現性"""
        if seed is None:
            seed = cls.SEED
        
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        
        # CuDNN
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

        if not Config._printed:
            print(f"✓ 隨機種子已設置: {seed}")
            Config._printed = True

    # 路徑配置
    dataset_path = os.path.join(PROJECT_ROOT, "IMG", "IMG_train", "method2")
    test_images_path = os.path.join(dataset_path, "test")
    model_dir = os.path.join(PROJECT_ROOT, "model")
    features_dir = os.path.join(model_dir, "features")
    
    # 模型路徑
    resnet_model_path = os.path.join(model_dir, "Resnet_model.pth")
    mlp_model_path = os.path.join(model_dir, "MLP_model.pth")
    xgb_model_path = os.path.join(model_dir, "XGBoost_model.pkl")
    rf_model_path = os.path.join(model_dir, "RandomForest_model.pkl")
    
    # 數據路徑
    metadata_path = os.path.join(features_dir, "metadata.csv")
    train_stats_path = os.path.join(features_dir, "train_stats.json")
    record_path = os.path.join(model_dir, "model_records.json")
    
    # 訓練超參數
    meta_cols = ['age', 'Length_px', 'Contrast_Ratio', 'has_diabetes']
    meta_dim = len(meta_cols)
    class_num = 2 # 可選: 2, 3, 5
    batch_size = 8
    learning_rate = 2e-4
    weight_decay = 1e-4
    num_epochs = 100
    patience_epochs = 30
    freeze_epochs = 10
    
    # 訓練策略
    use_weighted_sampler = False
    use_class_weights = True
    use_staged_training = False
    
    # 設備配置
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # 類別名稱
    if class_num == 5:
        CLASS_NAMES = {
            0: "eGFR -15",
            1: "eGFR 15-29",
            2: "eGFR 30-59",
            3: "eGFR 60-89",
            4: "eGFR 90-"
        }
        CLASS_SHORT = ["-15", "15-29", "30-59", "60-89", "90-"]
        DIR_TO_CLASS = {
            "eGFR -15": 0,
            "eGFR 15-29": 1,
            "eGFR 30-59": 2,
            "eGFR 60-89": 3,
            "eGFR 90-": 4
        }

    elif class_num == 3:
        CLASS_NAMES = {
            0: "eGFR -29",
            1: "eGFR 30-59",
            2: "eGFR 60-"
        }
        CLASS_SHORT = ["-29", "30-59", "60-"]
        DIR_TO_CLASS = {
            "eGFR -15": 0,
            "eGFR 15-29": 0,
            "eGFR 30-59": 1,
            "eGFR 60-89": 2,
            "eGFR 90-": 2
        }

    else:
        CLASS_NAMES = {
            0: "eGFR -59",
            1: "eGFR 60-"
        }
        CLASS_SHORT = ["-59", "60-"]
        DIR_TO_CLASS = {
            "eGFR -15": 0,
            "eGFR 15-29": 0,
            "eGFR 30-59": 0,
            "eGFR 60-89": 1,
            "eGFR 90-": 1
        }

    unified_mode = "standard"  # 可選: "standard" 或 "coral"，統一選擇訓練/推論模式
    
    @classmethod
    def setup(cls):
        """初始化目錄"""
        os.makedirs(cls.model_dir, exist_ok=True)
        os.makedirs(cls.features_dir, exist_ok=True)
        cls.set_seed()  # 自動設置種子
    
    @classmethod
    def get_model_path(cls, model_type):
        """根據模型類型獲取路徑"""
        paths = {
            'mlp': cls.mlp_model_path,
            'xgboost': cls.xgb_model_path,
            'rf': cls.rf_model_path,
            'resnet': cls.resnet_model_path
        }
        return paths.get(model_type.lower())

    @classmethod
    def get_metadata_config(cls):
        """獲取 MetadataConfig 實例"""
        from metadata_manager import MetadataConfig
        
        # 定義哪些欄位是二元的（不需要標準化）
        binary_cols = ['gender', 'has_diabetes', 'diabetes', '有無糖尿病']
        
        return MetadataConfig(
            cls.meta_cols, 
            cls.metadata_path,
            binary_cols=binary_cols
        )
    
    @classmethod
    def setup(cls):
        """初始化目錄並驗證配置"""
        os.makedirs(cls.model_dir, exist_ok=True)
        os.makedirs(cls.features_dir, exist_ok=True)
        cls.set_seed()
        
        # 驗證 metadata 配置
        if not os.path.exists(cls.metadata_path):
            print(f"⚠️  警告: 找不到 {cls.metadata_path}")
        else:
            cls.validate_metadata_config()
    
    @classmethod
    def validate_metadata_config(cls):
        """驗證 metadata 配置"""
        import pandas as pd
        
        if not cls.meta_cols:
            raise ValueError("❌ meta_cols 不能為空！")
        
        meta_df = pd.read_csv(cls.metadata_path)
        missing_cols = set(cls.meta_cols) - set(meta_df.columns)
        
        if missing_cols:
            available = list(meta_df.columns)
            raise ValueError(
                f"❌ metadata.csv 缺少必需欄位: {missing_cols}\n"
                f"   可用欄位: {available}\n"
                f"   請在 Config.meta_cols 中只使用可用欄位"
            )

# ==================== 基礎ResNet訓練器 ====================
class BasicResNetTrainer:
    """基礎ResNet訓練器 (不使用metadata)"""
    
    def __init__(self, model, train_loader, val_loader, criterion, optimizer, device='cuda'):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.criterion = criterion
        self.optimizer = optimizer
        self.device = device
        self.num_classes = model.num_classes  #  記錄類別數
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.8, patience=7, min_lr=1e-6
        )
    
    def train_epoch(self, epoch, num_epochs, progress_callback=None):
        """訓練一個epoch"""
        self.model.train()
        running_loss = 0.0
        running_corrects = 0
        total_batches = len(self.train_loader)
        
        for batch_idx, (images, meta, labels) in enumerate(self.train_loader, 1):
            images = images.to(self.device, non_blocking=True)
            labels = labels.to(self.device, non_blocking=True)
            
            #  二元分類: labels 轉為 float
            if self.num_classes == 2:
                labels = labels.float()
            else:
                labels = labels.long()
            
            self.optimizer.zero_grad()
            outputs = self.model(images)
            loss = self.criterion(outputs, labels)
            loss.backward()
            
            # 梯度裁剪
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()
            
            #  根據類別數計算預測
            if self.num_classes == 2:
                preds = (torch.sigmoid(outputs) > 0.5).long()
                labels = labels.long()
            else:
                _, preds = torch.max(outputs, 1)
            
            running_loss += loss.item() * images.size(0)
            running_corrects += (preds == labels).sum().item()
            
            if progress_callback and batch_idx % 2 == 0:
                progress_callback(epoch, num_epochs, batch_idx, total_batches, None, None, None, None, False)
        
        epoch_loss = running_loss / len(self.train_loader.dataset)
        epoch_acc = running_corrects / len(self.train_loader.dataset)
        
        return epoch_loss, epoch_acc
    
    def validate(self):
        """驗證"""
        self.model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for images, meta, labels in self.val_loader:
                images = images.to(self.device, non_blocking=True)
                labels = labels.to(self.device, non_blocking=True)
                
                #  二元分類: labels 轉為 float
                if self.num_classes == 2:
                    labels_for_loss = labels.float()
                else:
                    labels_for_loss = labels.long()
                
                outputs = self.model(images)
                loss = self.criterion(outputs, labels_for_loss)
                
                val_loss += loss.item()
                
                #  根據類別數計算預測
                if self.num_classes == 2:
                    predicted = (torch.sigmoid(outputs) > 0.5).long()
                    # 用於 F1 計算，轉為 one-hot 格式
                    outputs_for_f1 = torch.stack([1 - torch.sigmoid(outputs), torch.sigmoid(outputs)], dim=1)
                else:
                    _, predicted = torch.max(outputs, 1)
                    outputs_for_f1 = outputs
                
                correct += (predicted == labels).sum().item()
                total += labels.size(0)
                
                all_preds.append(outputs_for_f1)
                all_labels.append(labels)
        
        val_loss = val_loss / len(self.val_loader)
        val_acc = correct / total if total > 0 else 0
        
        all_preds = torch.cat(all_preds, dim=0)
        all_labels = torch.cat(all_labels, dim=0)
        val_f1 = self._f1_score(all_preds, all_labels)
        
        return val_loss, val_acc, val_f1
    
    def _f1_score(self, preds, targets):
        """計算F1 score"""
        if self.num_classes == 2:
            # 二元分類: preds 是 [batch, 2] 的機率
            preds = torch.argmax(preds, dim=1).detach().cpu().numpy()
        else:
            preds = torch.argmax(preds, dim=1).detach().cpu().numpy()
        
        targets = targets.detach().cpu().numpy()
        return f1_score(targets, preds, average='macro', zero_division=0)
    
    def train(self, num_epochs, patience=20, progress_callback=None,
              use_staged_training=False, freeze_epochs=10):
        """完整訓練流程"""
        best_model_wts = copy.deepcopy(self.model.state_dict())
        best_val_acc = 0.0
        best_val_loss = float('inf')
        best_val_f1 = 0.0
        patience_counter = 0
        
        history = {
            'train_loss': [],
            'val_loss': [],
            'val_acc': [],
            'val_f1': []
        }
        
        start_time = time.time()
        
        # 分階段訓練
        if use_staged_training:
            print(f"\n{'='*60}")
            print(f"階段1: 凍結backbone前半部 ({freeze_epochs} epochs)")
            print(f"{'='*60}\n")
            self.model.freeze_backbone_partial()
        
        for epoch in range(1, num_epochs + 1):
            # 解凍
            if use_staged_training and epoch == freeze_epochs + 1:
                print(f"\n{'='*60}")
                print(f"階段2: 解凍所有層 + 降低學習率")
                print(f"{'='*60}\n")
                self.model.unfreeze_all()
                
                for param_group in self.optimizer.param_groups:
                    param_group['lr'] = param_group['lr'] * 0.1
                print(f"學習率降低至: {self.optimizer.param_groups[0]['lr']:.6f}")
            
            # 訓練
            train_loss, train_acc = self.train_epoch(epoch, num_epochs, progress_callback)
            
            # 驗證
            val_loss, val_acc, val_f1 = self.validate()
            
            # 記錄
            history['train_loss'].append(train_loss)
            history['val_loss'].append(val_loss)
            history['val_acc'].append(val_acc)
            history['val_f1'].append(val_f1)
            
            # 回調
            if progress_callback:
                progress_callback(
                    epoch, num_epochs, len(self.train_loader), len(self.train_loader),
                    train_loss, val_loss, val_acc, val_f1, True
                )
            
            # 學習率調整
            if not use_staged_training or epoch > freeze_epochs:
                self.scheduler.step(val_loss)
            
            current_lr = self.optimizer.param_groups[0]['lr']
            
            stage_info = ""
            if use_staged_training:
                stage_info = f"[階段 {'1-部分凍結' if epoch <= freeze_epochs else '2-全解凍'}] "
            
            print(f'{stage_info}\033[96mEpoch\033[0m {epoch:>2}/{num_epochs}, '
                  f'\033[96mLR:\033[0m {current_lr:.6f}, '
                  f'\033[38;5;180mTrain Loss\033[0m={train_loss:.4f}, '
                  f'\033[38;5;180mAcc\033[0m={train_acc:.4f}, '
                  f'\033[38;5;180mVal Loss\033[0m={val_loss:.4f}, '
                  f'\033[38;5;180mVal Acc\033[0m={val_acc:.4f}, '
                  f'\033[38;5;180mVal F1\033[0m={val_f1:.4f}')

            best_val_acc = max(val_acc, best_val_acc)
            # Early stopping
            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_model_wts = copy.deepcopy(self.model.state_dict())
                patience_counter = 0
            else:
                patience_counter += 1
            
            if patience_counter >= patience:
                print(f'\nEarly stopping at epoch {epoch} (patience={patience})')
                break
            
            torch.cuda.empty_cache()
        
        # 恢復最佳模型
        self.model.load_state_dict(best_model_wts)
        
        time_elapsed = time.time() - start_time
        minutes = int(time_elapsed // 60)
        seconds = int(time_elapsed % 60)
        
        print(f'\n訓練完成！時間: {minutes}分{seconds}秒')
        print(f'最佳驗證準確率: {best_val_acc:.4f}')
        
        return self.model, best_val_acc, minutes, seconds, history


# ==================== MLP訓練器 ====================
class MLPTrainer:
    """MLP端到端訓練器"""
    
    def __init__(self, model, train_loader, val_loader, criterion, optimizer, device='cuda'):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.criterion = criterion
        self.optimizer = optimizer
        self.device = device
        self.num_classes = model.num_classes  #  記錄類別數
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.8, patience=7, min_lr=1e-6
        )
    
    def train_epoch(self, epoch, num_epochs, progress_callback=None):
        """訓練一個epoch"""
        self.model.train()
        running_loss = 0.0
        running_corrects = 0
        total_batches = len(self.train_loader)
        
        for batch_idx, (images, meta, labels) in enumerate(self.train_loader, 1):
            images = images.to(self.device, non_blocking=True)
            meta = meta.to(self.device, non_blocking=True).float()
            labels = labels.to(self.device, non_blocking=True)

            #  二元分類: labels 轉為 float
            if self.num_classes == 2:
                labels = labels.float()
            else:
                labels = labels.long()
            
            self.optimizer.zero_grad()
            outputs = self.model(images, meta)
            loss = self.criterion(outputs, labels)
            loss.backward()
            
            # 梯度裁剪
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            #  根據類別數計算預測
            if self.num_classes == 2:
                preds = (torch.sigmoid(outputs) > 0.5).long()
                labels_int = labels.long()  #  轉為整數用於比較
            else:
                _, preds = torch.max(outputs, 1)
                labels_int = labels
            
            running_loss += loss.item() * images.size(0)
            running_corrects += (preds == labels_int).sum().item()  #  使用 labels_int
            
            if progress_callback and batch_idx % 2 == 0:
                progress_callback(epoch, num_epochs, batch_idx, total_batches, None, None, None, None, False)
        
        epoch_loss = running_loss / len(self.train_loader.dataset)
        epoch_acc = running_corrects / len(self.train_loader.dataset)
        
        return epoch_loss, epoch_acc
    
    def validate(self):
        """驗證"""
        self.model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for images, meta, labels in self.val_loader:
                images = images.to(self.device, non_blocking=True)
                meta = meta.to(self.device, non_blocking=True).float()
                labels = labels.to(self.device, non_blocking=True)

                #  二元分類: labels 轉為 float (用於損失函數)
                if self.num_classes == 2:
                    labels_for_loss = labels.float()
                else:
                    labels_for_loss = labels.long()
                
                outputs = self.model(images, meta)
                loss = self.criterion(outputs, labels_for_loss)
                
                val_loss += loss.item()
                
                #  根據類別數計算預測
                if self.num_classes == 2:
                    predicted = (torch.sigmoid(outputs) > 0.5).long()
                    # 用於 F1 計算，轉為 one-hot 格式
                    outputs_for_f1 = torch.stack([1 - torch.sigmoid(outputs), torch.sigmoid(outputs)], dim=1)
                else:
                    _, predicted = torch.max(outputs, 1)
                    outputs_for_f1 = outputs

                correct += (predicted == labels).sum().item()
                total += labels.size(0)
                
                all_preds.append(outputs_for_f1)
                all_labels.append(labels)
        
        val_loss = val_loss / len(self.val_loader)
        val_acc = correct / total if total > 0 else 0
        
        all_preds = torch.cat(all_preds, dim=0)
        all_labels = torch.cat(all_labels, dim=0)
        val_f1 = self._f1_score(all_preds, all_labels)
        
        return val_loss, val_acc, val_f1
    
    def _f1_score(self, preds, targets):
        """計算F1 score"""
        if self.num_classes == 2:
            # 二元分類: preds 是 [batch, 2] 的機率
            preds = torch.argmax(preds, dim=1).detach().cpu().numpy()
        else:
            preds = torch.argmax(preds, dim=1).detach().cpu().numpy()
        
        targets = targets.detach().cpu().numpy()
        return f1_score(targets, preds, average='macro', zero_division=0)
    
    def train(self, num_epochs, patience=20, progress_callback=None,
              use_staged_training=False, freeze_epochs=10):
        """完整訓練流程"""
        best_model_wts = copy.deepcopy(self.model.state_dict())
        best_val_acc = 0.0
        best_val_loss = float('inf')
        best_val_f1 = 0.0
        patience_counter = 0
        
        history = {
            'train_loss': [],
            'val_loss': [],
            'val_acc': [],
            'val_f1': []
        }
        
        start_time = time.time()
        
        # 分階段訓練
        if use_staged_training:
            print(f"\n{'='*60}")
            print(f"階段1: 凍結backbone前半部 ({freeze_epochs} epochs)")
            print(f"{'='*60}\n")
            self.model.freeze_backbone_partial()
        
        for epoch in range(1, num_epochs + 1):
            # 解凍
            if use_staged_training and epoch == freeze_epochs + 1:
                print(f"\n{'='*60}")
                print(f"階段2: 解凍所有層 + 降低學習率")
                print(f"{'='*60}\n")
                self.model.unfreeze_all()
                
                for param_group in self.optimizer.param_groups:
                    param_group['lr'] = param_group['lr'] * 0.1
                print(f"學習率降低至: {self.optimizer.param_groups[0]['lr']:.6f}")
            
            # 訓練
            train_loss, train_acc = self.train_epoch(epoch, num_epochs, progress_callback)
            
            # 驗證
            val_loss, val_acc, val_f1 = self.validate()
            
            # 記錄
            history['train_loss'].append(train_loss)
            history['val_loss'].append(val_loss)
            history['val_acc'].append(val_acc)
            history['val_f1'].append(val_f1)
            
            # 回調
            if progress_callback:
                progress_callback(
                    epoch, num_epochs, len(self.train_loader), len(self.train_loader),
                    train_loss, val_loss, val_acc, val_f1, True
                )
            
            # 學習率調整
            if not use_staged_training or epoch > freeze_epochs:
                self.scheduler.step(val_loss)
            
            current_lr = self.optimizer.param_groups[0]['lr']
            
            stage_info = ""
            if use_staged_training:
                stage_info = f"[階段 {'1-部分凍結' if epoch <= freeze_epochs else '2-全解凍'}] "
            
            print(f'{stage_info}\033[96mEpoch\033[0m {epoch:>2}/{num_epochs}, '
                  f'\033[96mLR:\033[0m {current_lr:.6f}, '
                  f'\033[38;5;180mTrain Loss\033[0m={train_loss:.4f}, '
                  f'\033[38;5;180mAcc\033[0m={train_acc:.4f}, '
                  f'\033[38;5;180mVal Loss\033[0m={val_loss:.4f}, '
                  f'\033[38;5;180mVal Acc\033[0m={val_acc:.4f}, '
                  f'\033[38;5;180mVal F1\033[0m={val_f1:.4f}')
            
            best_val_acc = max(val_acc, best_val_acc)
            # Early stopping
            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_model_wts = copy.deepcopy(self.model.state_dict())
                patience_counter = 0
            else:
                patience_counter += 1
            
            if patience_counter >= patience:
                print(f'\nEarly stopping at epoch {epoch} (patience={patience})')
                break
            
            torch.cuda.empty_cache()
        
        # 恢復最佳模型
        self.model.load_state_dict(best_model_wts)
        
        time_elapsed = time.time() - start_time
        minutes = int(time_elapsed // 60)
        seconds = int(time_elapsed % 60)
        
        print(f'\n訓練完成！時間: {minutes}分{seconds}秒')
        print(f'最佳驗證準確率: {best_val_acc:.4f}')
        
        return self.model, best_val_acc, minutes, seconds, history


# ==================== ML訓練器 (XGBoost/RF) ====================
class MLClassifierTrainer:
    """機器學習分類器訓練器（需要先萃取特徵）"""
    
    def __init__(self, feature_extractor, classifier, device='cuda'):
        self.feature_extractor = feature_extractor.to(device)
        self.classifier = classifier
        self.device = device
        self.feature_extractor.eval()
    
    def extract_features(self, data_loader, verbose=True):
        """從DataLoader萃取特徵"""
        all_features = []
        all_metas = []
        all_labels = []
        
        iterator = tqdm(data_loader, desc="萃取特徵") if verbose else data_loader
        
        with torch.no_grad():
            for images, meta, labels in iterator:
                images = images.to(self.device)
                meta = meta.to(self.device)
                
                # CNN特徵
                cnn_features = self.feature_extractor(images).cpu().numpy()
                
                # Metadata特徵
                meta_features = meta.cpu().numpy()
                
                all_features.append(cnn_features)
                all_metas.append(meta_features)
                all_labels.append(labels.numpy())
        
        # 合併特徵
        cnn_features = np.vstack(all_features)
        meta_features = np.vstack(all_metas)
        labels = np.concatenate(all_labels)
        
        # 拼接 CNN + Metadata
        features = np.hstack([cnn_features, meta_features])
        
        return features, labels
    
    def train(self, train_loader, val_loader):
        """訓練分類器"""
        print("\n萃取訓練集特徵...")
        X_train, y_train = self.extract_features(train_loader)
        
        print("\n萃取驗證集特徵...")
        X_val, y_val = self.extract_features(val_loader)
        
        print(f"\n特徵維度: train {X_train.shape}, val {X_val.shape}")
        
        # 訓練
        train_acc, val_acc = self.classifier.train(X_train, y_train, X_val, y_val)
        
        return train_acc, val_acc
    
    def evaluate(self, test_loader, class_names=None):
        """評估模型"""
        print("\n萃取測試集特徵...")
        X_test, y_test = self.extract_features(test_loader)
        
        return self.classifier.evaluate(X_test, y_test, class_names)