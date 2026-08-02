# ==================== CORAL 模式模型與工具 ====================
# 包含 CORAL 分類器、工具函數、Loss、HybridClassifier
import os
import json
import torch
import time
import copy
import numpy as np
from PIL import Image

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from torchvision.models import resnet18, ResNet18_Weights
from sklearn.metrics import f1_score, classification_report, confusion_matrix, accuracy_score

from trainer import Config
from loader_inference import create_inference_pipeline

class CoralClassifier(nn.Module):
    """
    CORAL (Consistent Rank Logits) 分類器
    輸出 N-1 個 logits，每個表示「≥該類別」的二元判斷
    """
    def __init__(self, in_features, num_classes):
        super().__init__()
        self.num_classes = num_classes
        # 輸出 N-1 個累積 logits
        self.fc = nn.Linear(in_features, num_classes - 1)
    
    def forward(self, x):
        """
        Returns:
            logits: (batch_size, num_classes-1)
        """
        return self.fc(x)


class CoralResNetClassifier(nn.Module):
    """CORAL ResNet分類器 (不使用metadata)"""
    
    def __init__(self, num_classes=5, weights=ResNet18_Weights.DEFAULT):
        super().__init__()
        self.num_classes = num_classes
        
        # ResNet Backbone
        backbone = resnet18(weights=weights)
        self.features = nn.Sequential(*list(backbone.children())[:-1])
        self.feature_dim = 512
        
        # Feature MLP
        self.feature_mlp = nn.Sequential(
            nn.Linear(self.feature_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.3)
        )
        
        # CORAL 分類層 (輸出 N-1 個 logits)
        self.coral_classifier = CoralClassifier(256, num_classes)
    
    def forward(self, x):
        """
        Returns:
            coral_logits: (batch_size, num_classes-1)
        """
        # Backbone 特徵
        feat = self.features(x)
        feat = feat.view(feat.size(0), -1)
        
        # Feature MLP
        feat = self.feature_mlp(feat)
        
        # CORAL 輸出
        return self.coral_classifier(feat)
    
    def predict_proba(self, x):
        """
        預測類別概率
        
        Returns:
            probs: (batch_size, num_classes)
        """
        logits = self.forward(x)
        return coral_logits_to_probs(logits, self.num_classes)
    
    def predict_class(self, x):
        """
        預測類別
        
        Returns:
            pred_class: (batch_size,)
        """
        probs = self.predict_proba(x)
        return torch.argmax(probs, dim=1)
    
    def freeze_backbone_partial(self):
        """凍結backbone前半部"""
        for name, param in self.features.named_parameters():
            if any(layer in name for layer in ['layer1', 'layer2']):
                param.requires_grad = False
        print("🔒 已凍結 layer1, layer2")
    
    def unfreeze_all(self):
        """解凍所有層"""
        for param in self.parameters():
            param.requires_grad = True
        print("🔓 已解凍所有層")


class CoralMLPClassifier(nn.Module):
    """CORAL MLP分類器 (支援metadata)"""
    
    def __init__(self, num_classes=5, meta_dim=5, weights=ResNet18_Weights.DEFAULT):
        super().__init__()
        self.num_classes = num_classes
        self.meta_dim = meta_dim
        
        # ResNet Backbone
        backbone = resnet18(weights=weights)
        self.features = nn.Sequential(*list(backbone.children())[:-1])
        self.feature_dim = 512
        
        # Image feature MLP
        self.feature_mlp = nn.Sequential(
            nn.Linear(self.feature_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.3)
        )
        
        # Metadata MLP
        self.meta_mlp = nn.Sequential(
            nn.Linear(meta_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.05)
        )
        
        # CORAL 分類層 (輸出 N-1 個 logits)
        self.coral_classifier = CoralClassifier(128 + 64, num_classes)
    
    def forward(self, x, meta):
        """
        Args:
            x: 圖片 (batch_size, 3, H, W)
            meta: metadata (batch_size, meta_dim)
        
        Returns:
            coral_logits: (batch_size, num_classes-1)
        """
        # Backbone 特徵
        feat = self.features(x)
        feat = feat.view(feat.size(0), -1)
        feat = self.feature_mlp(feat)
        
        # Metadata 特徵
        meta_feat = self.meta_mlp(meta)
        
        # 合併特徵
        combined = torch.cat([feat, meta_feat], dim=1)
        
        # CORAL 輸出
        return self.coral_classifier(combined)
    
    def predict_proba(self, x, meta):
        """
        預測類別概率
        
        Returns:
            probs: (batch_size, num_classes)
        """
        logits = self.forward(x, meta)
        return coral_logits_to_probs(logits, self.num_classes)
    
    def predict_class(self, x, meta):
        """
        預測類別
        
        Returns:
            pred_class: (batch_size,)
        """
        probs = self.predict_proba(x, meta)
        return torch.argmax(probs, dim=1)
    
    def freeze_backbone_partial(self):
        """凍結backbone前半部"""
        for name, param in self.features.named_parameters():
            if any(layer in name for layer in ['layer1', 'layer2']):
                param.requires_grad = False
        print("🔒 已凍結 layer1, layer2")
    
    def unfreeze_all(self):
        """解凍所有層"""
        for param in self.parameters():
            param.requires_grad = True
        print("🔓 已解凍所有層")


def label_to_cumulative(labels, num_classes):
    """
    將單一類別標籤轉換為累積標籤
    
    Args:
        labels: (batch_size,) 原始類別標籤 [0, 1, 2, 3, 4]
        num_classes: 類別總數
    
    Returns:
        cumulative_labels: (batch_size, num_classes-1) 累積標籤
    
    Example:
        label=2 (第3類) -> [1, 1, 0, 0]
        表示: ≥類別0: Yes, ≥類別1: Yes, ≥類別2: No, ≥類別3: No
    """
    batch_size = labels.size(0)
    cumulative = torch.zeros(batch_size, num_classes - 1, device=labels.device)
    
    for i in range(num_classes - 1):
        cumulative[:, i] = (labels > i).float()
    
    return cumulative

def smooth_coral_labels(cumulative_labels, smoothing=0.1):
    """
    cumulative_labels: [batch, num_classes-1] float tensor (0/1)
    smoothing: float
    """
    n_classes = cumulative_labels.size(1) + 1
    return cumulative_labels * (1 - smoothing) + smoothing / n_classes

def coral_logits_to_probs(logits, num_classes):
    """
    將 CORAL logits 轉換為類別概率
    
    Args:
        logits: (batch_size, num_classes-1) CORAL logits
        num_classes: 類別總數
    
    Returns:
        probs: (batch_size, num_classes) 類別概率
    
    Example:
        logits = [2.0, 1.0, -1.0, -2.0] (5類問題)
        sigmoid後 ≈ [0.88, 0.73, 0.27, 0.12]
        表示: P(≥0)=0.88, P(≥1)=0.73, P(≥2)=0.27, P(≥3)=0.12
        
        類別概率:
        P(class=0) = 1 - P(≥1) = 1 - 0.73 = 0.27
        P(class=1) = P(≥1) - P(≥2) = 0.73 - 0.27 = 0.46
        P(class=2) = P(≥2) - P(≥3) = 0.27 - 0.12 = 0.15
        P(class=3) = P(≥3) - 0 = 0.12
        P(class=4) = 1 - Σ前面 = 0.00
    """
    # 將 logits 轉為累積概率
    cumulative_probs = torch.sigmoid(logits)  # (batch_size, num_classes-1)
    
    # 補上邊界: P(≥-1)=1, P(≥num_classes)=0
    batch_size = logits.size(0)
    ones = torch.ones(batch_size, 1, device=logits.device)
    zeros = torch.zeros(batch_size, 1, device=logits.device)
    
    # [1, P(≥0), P(≥1), ..., P(≥N-2), 0]
    cumulative_probs = torch.cat([ones, cumulative_probs, zeros], dim=1)
    
    # 計算每個類別的概率: P(class=k) = P(≥k) - P(≥k+1)
    probs = cumulative_probs[:, :-1] - cumulative_probs[:, 1:]
    
    return probs


def coral_predict_class(logits, num_classes, threshold=0.5):
    """
    從 CORAL logits 預測類別（另一種方法：累積 sigmoid > threshold 的個數）
    
    Args:
        logits: (batch_size, num_classes-1)
        num_classes: 類別總數
        threshold: 閾值，預設 0.5
    
    Returns:
        pred_class: (batch_size,)
    """
    # 轉為概率
    cumulative_probs = torch.sigmoid(logits)  # (batch_size, num_classes-1)
    
    # 累積大於閾值的個數作為類別
    pred_class = (cumulative_probs > threshold).long().sum(dim=1)
    
    return pred_class


class CoralLoss(nn.Module):
    def __init__(self, weight=None, smoothing=0.0):
        super().__init__()
        self.weight = weight
        self.smoothing = smoothing
    
    def forward(self, logits, labels, num_classes):
        cumulative_labels = label_to_cumulative(labels, num_classes).float()
        if self.smoothing > 0:
            cumulative_labels = cumulative_labels * (1 - self.smoothing) + self.smoothing / num_classes
        
        if self.weight is not None:
            sample_weights = self.weight[labels].unsqueeze(1).expand_as(cumulative_labels)
            loss = F.binary_cross_entropy_with_logits(logits, cumulative_labels, reduction='none')
            loss = (loss * sample_weights).mean()
        else:
            loss = F.binary_cross_entropy_with_logits(logits, cumulative_labels, reduction='mean')
        
        return loss


def create_ordinal_model(model_type, num_classes=5, meta_dim=5, weights=ResNet18_Weights.DEFAULT):
    """
    創建 CORAL 序數分類模型
    
    Args:
        model_type: 'resnet' 或 'mlp'
        num_classes: 類別數量
        meta_dim: metadata 維度
        weights: ResNet 預訓練權重
    
    Returns:
        model: CORAL 模型實例
    """
    if model_type.lower() == 'resnet':
        return CoralResNetClassifier(num_classes=num_classes, weights=weights)
    elif model_type.lower() == 'mlp':
        return CoralMLPClassifier(num_classes=num_classes, meta_dim=meta_dim, weights=weights)
    else:
        raise ValueError(f"不支援的模型類型: {model_type}")


class HybridClassifier(nn.Module):
    """
    混合分類器：支援切換 CORAL 和標準分類模式
    """
    def __init__(self, base_model, num_classes=5, mode='coral'):
        """
        Args:
            base_model: 基礎模型 (CoralResNetClassifier 或 CoralMLPClassifier)
            num_classes: 類別數量
            mode: 'coral' 或 'standard'
        """
        super().__init__()
        self.base_model = base_model
        self.num_classes = num_classes
        self.mode = mode
        
        # 如果使用標準模式，額外添加一個標準分類層
        if mode == 'standard':
            if hasattr(base_model, 'meta_mlp'):
                # MLP 模型
                in_features = 128 + 64
            else:
                # ResNet 模型
                in_features = 256
            
            self.standard_classifier = nn.Linear(in_features, num_classes)
    
    def set_mode(self, mode):
        """切換模式"""
        assert mode in ['coral', 'standard'], "mode 必須是 'coral' 或 'standard'"
        self.mode = mode
        print(f"✓ 已切換至 {mode.upper()} 模式")
    
    def forward(self, x, meta=None):
        """
        前向傳播
        
        Returns:
            如果是 coral 模式: 返回 (batch_size, num_classes-1) logits
            如果是 standard 模式: 返回 (batch_size, num_classes) logits
        """
        if self.mode == 'coral':
            if meta is not None:
                return self.base_model(x, meta)
            else:
                return self.base_model(x)
        else:  # standard mode
            # 提取特徵
            if hasattr(self.base_model, 'features'):
                feat = self.base_model.features(x)
                feat = feat.view(feat.size(0), -1)
                feat = self.base_model.feature_mlp(feat)
                
                if meta is not None and hasattr(self.base_model, 'meta_mlp'):
                    meta_feat = self.base_model.meta_mlp(meta)
                    feat = torch.cat([feat, meta_feat], dim=1)
            
            return self.standard_classifier(feat)
    
    def predict_proba(self, x, meta=None):
        """預測概率"""
        if self.mode == 'coral':
            logits = self.forward(x, meta)
            return coral_logits_to_probs(logits, self.num_classes)
        else:
            logits = self.forward(x, meta)
            return F.softmax(logits, dim=1)
    
    def predict_class(self, x, meta=None):
        """預測類別"""
        probs = self.predict_proba(x, meta)
        return torch.argmax(probs, dim=1)
    

# ==================== CORAL 模式推論與工具 ====================
class CoralBaseInference:
    """CORAL 基礎推論器"""
    
    def __init__(self, device='cuda', stats_path=None, train_stats=None):
        """
        Args:
            device: 設備
            stats_path: 統計值 JSON 檔案路徑（向後兼容）
            train_stats: 統計值字典（新方法，優先使用）✅
        """
        self.device = device
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])
        
        # 預設統計值
        self.stats = {
            'age': {'mean': 50.0, 'std': 15.0},
            'gender': {'mean': 0.5, 'std': 0.5},
            'Length_px': {'mean': 200.0, 'std': 50.0},
            'Entropy': {'mean': 0.5, 'std': 0.1},
            'Contrast_Ratio': {'mean': 1.0, 'std': 0.2}
        }
        
        # ✅ 優先使用字典格式的統計值
        if train_stats is not None:
            self.stats = train_stats
            print("✓ CORAL 使用字典格式的統計值")
            for c in self.stats:
                print(f"  {c}_mean={self.stats[c]['mean']:.2f}, {c}_std={self.stats[c]['std']:.2f}")
        
        # ✅ 向後兼容：從檔案載入
        elif stats_path is not None and os.path.exists(stats_path):
            with open(stats_path, 'r') as f:
                self.stats = json.load(f)
            print(f"✓ CORAL 從檔案載入統計值: {stats_path}")
            for c in self.stats:
                print(f"  {c}_mean={self.stats[c]['mean']:.2f}, {c}_std={self.stats[c]['std']:.2f}")
    
    def load_train_stats(self, stats_path=None, train_stats=None):
        """載入訓練集統計值"""
        # ✅ 優先使用字典
        if train_stats is not None:
            self.stats = train_stats
            print("✓ CORAL 載入統計值（字典）:")
            for c in self.stats:
                print(f"  {c}_mean={self.stats[c]['mean']:.2f}, {c}_std={self.stats[c]['std']:.2f}")
        
        # ✅ 向後兼容：從檔案載入
        elif stats_path is not None and os.path.exists(stats_path):
            with open(stats_path, 'r') as f:
                self.stats = json.load(f)
            print(f"✓ CORAL 載入統計值（檔案）: {stats_path}")
            for c in self.stats:
                print(f"  {c}_mean={self.stats[c]['mean']:.2f}, {c}_std={self.stats[c]['std']:.2f}")
    
    def preprocess_metadata(self, age, gender, Length_px=None, Entropy=None, Contrast_Ratio=None):
        """✅ 預處理完整的 5 個 metadata 特徵"""
        # 標準化年齡
        age_norm = (age - self.stats['age']['mean']) / (self.stats['age']['std'] + 1e-10)
        
        # 編碼性別
        gender_encoded = 1.0 if gender in ['男', 'male', 'M', 1] else 0.0
        
        # 補齊缺失值
        Length_px = self.stats['Length_px']['mean'] if Length_px is None else Length_px
        Entropy = self.stats['Entropy']['mean'] if Entropy is None else Entropy
        Contrast_Ratio = self.stats['Contrast_Ratio']['mean'] if Contrast_Ratio is None else Contrast_Ratio
        
        # 標準化
        length_norm = (Length_px - self.stats['Length_px']['mean']) / (self.stats['Length_px']['std'] + 1e-10)
        entropy_norm = (Entropy - self.stats['Entropy']['mean']) / (self.stats['Entropy']['std'] + 1e-10)
        contrast_norm = (Contrast_Ratio - self.stats['Contrast_Ratio']['mean']) / (self.stats['Contrast_Ratio']['std'] + 1e-10)
        
        return torch.tensor([age_norm, gender_encoded, length_norm, entropy_norm, contrast_norm], dtype=torch.float32)
    
    def predict(self, image_path, age=None, gender=None):
        """預測單張圖片（需子類實現）"""
        raise NotImplementedError


class CoralResNetInference(CoralBaseInference):
    """CORAL ResNet 推論 (不使用metadata)"""
    
    def __init__(self, model, device='cuda', stats_path=None, train_stats=None):
        super().__init__(
            device=device,
            stats_path=stats_path,
            train_stats=train_stats  # ✅ 傳入字典
        )
        self.model = model.to(device)
        self.model.eval()
        self.num_classes = model.num_classes
    
    def predict(self, image_path, age=None, gender=None):
        """
        預測單張圖片 (忽略metadata參數)
        
        Returns:
            pred_class: int
            proba: numpy array (num_classes,)
        """
        # 預處理圖片
        image_tensor, _ = self.preprocess_image(image_path)
        image_tensor = image_tensor.to(self.device)
        
        # 推論
        with torch.no_grad():
            # CORAL logits
            logits = self.model(image_tensor)  # (1, num_classes-1)
            
            # 轉換為類別概率
            proba = coral_logits_to_probs(logits, self.num_classes)  # (1, num_classes)
            pred_class = torch.argmax(proba, dim=1).item()
            proba = proba.cpu().numpy()[0]
        
        return pred_class, proba


class CoralMLPInference(CoralBaseInference):
    """CORAL MLP 推論 (支援metadata)"""
    
    def __init__(self, model, device='cuda', stats_path=None, train_stats=None):
        super().__init__(
            device=device,
            stats_path=stats_path,
            train_stats=train_stats  # ✅ 傳入字典
        )
        self.model = model.to(device)
        self.model.eval()
        self.num_classes = model.num_classes
    
    def predict(self, image_path, age=None, gender=None, Length_px=None, Entropy=None, Contrast_Ratio=None):
        """
        ✅ 預測單張圖片 (完整的 5 個 metadata 參數)
        
        Returns:
            pred_class: int
            proba: numpy array (num_classes,)
        """
        # 預處理圖片
        image_tensor, _ = self.preprocess_image(image_path)
        image_tensor = image_tensor.to(self.device)
        
        # 預處理metadata (5個特徵)
        if age is None or gender is None:
            meta_tensor = torch.zeros(5)  # ✅ 改為 5 個特徵
        else:
            meta_tensor = self.preprocess_metadata(age, gender, Length_px, Entropy, Contrast_Ratio)
        
        meta_tensor = meta_tensor.unsqueeze(0).to(self.device)
        
        # 推論
        with torch.no_grad():
            logits = self.model(image_tensor, meta_tensor)
            proba = coral_logits_to_probs(logits, self.num_classes)
            pred_class = torch.argmax(proba, dim=1).item()
            proba = proba.cpu().numpy()[0]
        
        return pred_class, proba


def create_coral_inference(model_type, model_path, num_classes=5, device='cuda', 
                          stats_path=None, train_stats=None):
    """
    創建 CORAL 推論 Pipeline
    
    Args:
        model_type: 'resnet' 或 'mlp'
        model_path: 模型路徑
        num_classes: 類別數量
        device: 設備
        stats_path: 統計值檔案路徑（向後兼容）
        train_stats: 統計值字典（新方法，優先使用）✅
    
    Returns:
        推論器實例
    """
    if model_type.lower() == 'resnet':
        # 載入 CORAL ResNet 模型
        model = CoralResNetClassifier(num_classes=num_classes)
        model.load_state_dict(
            torch.load(model_path, map_location=device, weights_only=True)
        )
        inference = CoralResNetInference(
            model, device,
            stats_path=stats_path,
            train_stats=train_stats  # ✅ 傳入字典
        )
    
    elif model_type.lower() == 'mlp':
        # 載入 CORAL MLP 模型
        model = CoralMLPClassifier(num_classes=num_classes, meta_dim=5)
        model.load_state_dict(
            torch.load(model_path, map_location=device, weights_only=True)
        )
        inference = CoralMLPInference(
            model, device,
            stats_path=stats_path,
            train_stats=train_stats  # ✅ 傳入字典
        )
    
    else:
        raise ValueError(f"不支援的模型類型: {model_type}")
    
    print(f"✓ CORAL {model_type.upper()} 推論器已載入")
    
    return inference


def create_unified_inference(model_type, model_path, num_classes=5, device='cuda', 
                            is_coral=False, **kwargs):
    """
    統一推論接口：支援標準和 CORAL 模型
    
    Args:
        model_type: 'resnet' 或 'mlp'
        model_path: 模型路徑
        num_classes: 類別數量
        device: 設備
        is_coral: 是否為 CORAL 模型
        **kwargs: 其他參數
    
    Returns:
        推論器實例
    """
    if is_coral:
        # 使用 CORAL 推論器
        return create_coral_inference(
            model_type=model_type,
            model_path=model_path,
            num_classes=num_classes,
            device=device,
            stats_path=kwargs.get('stats_path')
        )
    else:
        # 使用標準推論器
        return create_inference_pipeline(
            model_type=model_type,
            model_path=model_path,
            device=device,
            **kwargs
        )

# ==================== 批量評估工具 ====================
def evaluate_coral_model(inference, test_loader, class_names, device='cuda'):
    """
    評估 CORAL 模型在測試集上的表現
    
    Args:
        inference: CORAL 推論器
        test_loader: 測試 DataLoader
        class_names: 類別名稱字典
        device: 設備
    
    Returns:
        metrics: 評估指標字典
    """

    all_preds = []
    all_labels = []
    all_probs = []
    
    print("\n開始評估 CORAL 模型...")
    
    for images, meta, labels in test_loader:
        images = images.to(device)
        if isinstance(inference, CoralMLPInference):
            meta = meta.to(device)
        labels = labels.numpy()
        
        # 批量推論
        with torch.no_grad():
            if isinstance(inference, CoralMLPInference):
                logits = inference.model(images, meta)
            else:
                logits = inference.model(images)
            
            probs = coral_logits_to_probs(logits, inference.num_classes)
            preds = torch.argmax(probs, dim=1).cpu().numpy()
        
        all_preds.extend(preds)
        all_labels.extend(labels)
        all_probs.append(probs.cpu().numpy())
    
    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    all_probs = np.vstack(all_probs)
    
    # 計算指標
    acc = accuracy_score(all_labels, all_preds)
    cm = confusion_matrix(all_labels, all_preds)
    
    print(f"\n{'='*60}")
    print(f"CORAL 模型測試準確率: {acc:.4f}")
    print(f"{'='*60}")
    print(classification_report(
        all_labels, 
        all_preds, 
        target_names=[class_names[i] for i in sorted(class_names.keys())]
    ))
    print("\n混淆矩陣:")
    print(cm)
    
    return {
        'accuracy': acc,
        'predictions': all_preds,
        'probabilities': all_probs,
        'confusion_matrix': cm
    }

# ==================== CORAL 模式訓練器與接口 ====================
# 包含 CORAL ResNet/MLP 訓練器與統一訓練接口

class CoralResNetTrainer:
    """CORAL ResNet訓練器 (不使用metadata)"""
    
    def __init__(self, model, train_loader, val_loader, criterion, optimizer, smoothing, device='cuda'):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.criterion = criterion
        self.optimizer = optimizer
        self.device = device
        self.num_classes = model.num_classes
        self.label_smoothing = smoothing
        
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=50)  # T_max = 總 epoch
    
    def train_epoch(self, epoch, num_epochs, progress_callback=None):
        self.model.train()
        running_loss = 0.0
        running_corrects = 0
        total_batches = len(self.train_loader)
        
        for batch_idx, (images, meta, labels) in enumerate(self.train_loader, 1):
            images = images.to(self.device, non_blocking=True)
            labels = labels.to(self.device, non_blocking=True).long()

            self.optimizer.zero_grad()
            
            # CORAL 前向傳播
            logits = self.model(images)
            
            # 直接傳原始 labels
            loss = self.criterion(logits, labels, self.num_classes)
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=0.5)
            self.optimizer.step()
            
            # 預測類別
            with torch.no_grad():
                probs = coral_logits_to_probs(logits, self.num_classes)
                preds = torch.argmax(probs, dim=1)
            
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
                labels = labels.to(self.device, non_blocking=True).long()
                
                # CORAL 前向傳播
                logits = self.model(images)
                loss = self.criterion(logits, labels, self.num_classes)
                
                # 預測
                probs = coral_logits_to_probs(logits, self.num_classes)
                predicted = torch.argmax(probs, dim=1)
                
                val_loss += loss.item()
                correct += (predicted == labels).sum().item()
                total += labels.size(0)
                
                all_preds.append(predicted)
                all_labels.append(labels)
        
        val_loss = val_loss / len(self.val_loader)
        val_acc = correct / total if total > 0 else 0
        
        all_preds = torch.cat(all_preds, dim=0).cpu().numpy()
        all_labels = torch.cat(all_labels, dim=0).cpu().numpy()
        val_f1 = f1_score(all_labels, all_preds, average='macro', zero_division=0)
        
        return val_loss, val_acc, val_f1
    
    def train(self, num_epochs, patience=20, progress_callback=None,
              use_staged_training=False, freeze_epochs=10):
        """完整訓練流程"""
        best_model_wts = copy.deepcopy(self.model.state_dict())
        best_val_acc = 0.0
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
            
            self.scheduler.step()
            current_lr = self.optimizer.param_groups[0]['lr']
            
            stage_info = ""
            if use_staged_training:
                stage_info = f"[階段 {'1-部分凍結' if epoch <= freeze_epochs else '2-全解凍'}] "
            
            print(f'{stage_info}\033[96m[CORAL]\033[0m \033[96mEpoch\033[0m {epoch:>2}/{num_epochs}, '
                  f'\033[96mLR:\033[0m {current_lr:.6f}, '
                  f'\033[38;5;180mTrain Loss\033[0m={train_loss:.4f}, '
                  f'\033[38;5;180mAcc\033[0m={train_acc:.4f}, '
                  f'\033[38;5;180mVal Loss\033[0m={val_loss:.4f}, '
                  f'\033[38;5;180mVal Acc\033[0m={val_acc:.4f}, '
                  f'\033[38;5;180mVal F1\033[0m={val_f1:.4f}')
            
            # Early stopping
            if val_acc > best_val_acc:
                best_val_acc = val_acc
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
        
        print(f'\n[CORAL] 訓練完成！時間: {minutes}分{seconds}秒')
        print(f'最佳驗證準確率: {best_val_acc:.4f}')
        
        return self.model, best_val_acc, minutes, seconds, history


class CoralMLPTrainer:
    """CORAL MLP訓練器 (支援metadata)"""
    
    def __init__(self, model, train_loader, val_loader, criterion, optimizer, smoothing, device='cuda'):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.criterion = criterion
        self.optimizer = optimizer
        self.device = device
        self.num_classes = model.num_classes
        self.label_smoothing = smoothing
        
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=50)  # T_max = 總 epoch
    
    def train_epoch(self, epoch, num_epochs, progress_callback=None):
        """訓練一個epoch"""
        self.model.train()
        running_loss = 0.0
        running_corrects = 0
        total_batches = len(self.train_loader)
        
        smoothing = self.label_smoothing
        
        for batch_idx, (images, meta, labels) in enumerate(self.train_loader, 1):
            images = images.to(self.device, non_blocking=True)
            meta = meta.to(self.device, non_blocking=True).float()
            labels = labels.to(self.device, non_blocking=True).long()
            
            self.optimizer.zero_grad()
            
            # CORAL 前向傳播
            logits = self.model(images, meta)  # (batch_size, num_classes-1)
            
            # CORAL Loss
            loss = self.criterion(logits, labels, self.num_classes)  # float tensor
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=0.5)
            self.optimizer.step()
            
            # 預測類別
            with torch.no_grad():
                probs = coral_logits_to_probs(logits, self.num_classes)
                preds = torch.argmax(probs, dim=1)
            
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
                meta = meta.to(self.device, non_blocking=True).float()
                labels = labels.to(self.device, non_blocking=True).long()
                
                # CORAL 前向傳播
                logits = self.model(images, meta)
                loss = self.criterion(logits, labels, self.num_classes)
                
                # 預測
                probs = coral_logits_to_probs(logits, self.num_classes)
                predicted = torch.argmax(probs, dim=1)
                
                val_loss += loss.item()
                correct += (predicted == labels).sum().item()
                total += labels.size(0)
                
                all_preds.append(predicted)
                all_labels.append(labels)
        
        val_loss = val_loss / len(self.val_loader)
        val_acc = correct / total if total > 0 else 0
        
        all_preds = torch.cat(all_preds, dim=0).cpu().numpy()
        all_labels = torch.cat(all_labels, dim=0).cpu().numpy()
        val_f1 = f1_score(all_labels, all_preds, average='macro', zero_division=0)
        
        return val_loss, val_acc, val_f1
    
    def train(self, num_epochs, patience=20, progress_callback=None,
              use_staged_training=False, freeze_epochs=10):
        """完整訓練流程"""
        best_model_wts = copy.deepcopy(self.model.state_dict())
        best_val_acc = 0.0
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
            
            self.scheduler.step()
            current_lr = self.optimizer.param_groups[0]['lr']
            
            stage_info = ""
            if use_staged_training:
                stage_info = f"[階段 {'1-部分凍結' if epoch <= freeze_epochs else '2-全解凍'}] "
            
            print(f'{stage_info}\033[96m[CORAL]\033[0m \033[96mEpoch\033[0m {epoch:>2}/{num_epochs}, '
                  f'\033[96mLR:\033[0m {current_lr:.6f}, '
                  f'\033[38;5;180mTrain Loss\033[0m={train_loss:.4f}, '
                  f'\033[38;5;180mAcc\033[0m={train_acc:.4f}, '
                  f'\033[38;5;180mVal Loss\033[0m={val_loss:.4f}, '
                  f'\033[38;5;180mVal Acc\033[0m={val_acc:.4f}, '
                  f'\033[38;5;180mVal F1\033[0m={val_f1:.4f}')
            
            # Early stopping
            if val_acc > best_val_acc:
                best_val_acc = val_acc
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
        
        print(f'\n[CORAL] 訓練完成！時間: {minutes}分{seconds}秒')
        print(f'最佳驗證準確率: {best_val_acc:.4f}')
        
        return self.model, best_val_acc, minutes, seconds, history


def create_coral_trainer(model_type, model, train_loader, val_loader, 
                        class_weights=None, device='cuda', learning_rate=1e-4, weight_decay=1e-4, smoothing=0.1):
    """
    創建 CORAL 訓練器
    
    Args:
        model_type: 'resnet' 或 'mlp'
        model: CORAL 模型實例
        train_loader: 訓練 DataLoader
        val_loader: 驗證 DataLoader
        class_weights: 類別權重
        device: 設備
        learning_rate: 學習率
        weight_decay: 權重衰減
    
    Returns:
        trainer: 訓練器實例
    """
    # 創建 CORAL Loss
    criterion = CoralLoss(weight=class_weights, smoothing=smoothing)
    
    # 創建優化器
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay
    )
    
    # 創建訓練器
    if model_type.lower() == 'resnet':
        trainer = CoralResNetTrainer(model, train_loader, val_loader, criterion, optimizer, smoothing, device)
    elif model_type.lower() == 'mlp':
        trainer = CoralMLPTrainer(model, train_loader, val_loader, criterion, optimizer, smoothing, device)
    else:
        raise ValueError(f"不支援的模型類型: {model_type}")
    
    return trainer