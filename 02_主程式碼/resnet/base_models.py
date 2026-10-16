"""
base_models.py - 基礎模型定義
包含: ResNet Backbone, MobileNetV2 Backbone, EfficientNet Backbone, MLP分類器等
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import (
    resnet18, ResNet18_Weights,
    mobilenet_v2, MobileNet_V2_Weights,
    efficientnet_b3, EfficientNet_B3_Weights
)
from trainer import Config

class RewardPunishCrossEntropy(nn.Module):
    """
    改進版自訂損失函數 - 結合 Reward/Punish 機制與距離懲罰
    
    Args:
        weight: 類別權重 (可選)
        reward: 預測正確時的折扣 (0.2 = 折扣20%)
        punish: 預測錯誤時的懲罰 (0.2 = 增加20%)
        dist_penalty: 距離懲罰權重
        use_distance: 是否使用距離懲罰
        label_smoothing: 標籤平滑係數
        normalize_dist: 是否歸一化距離懲罰
        symmetric_reward_punish: 是否使用對稱的 reward/punish (對數空間)
        min_loss: 最小損失閾值（防止梯度消失）
    """
    def __init__(
        self,
        weight=None,
        reward=0.2,
        punish=0.2,
        dist_penalty=0.5,
        use_distance=True,
        label_smoothing=0.1,
        normalize_dist=True,           # 新增
        symmetric_reward_punish=False, # 新增
        min_loss=0.0,                  # 新增
    ):
        super().__init__()
        self.register_buffer("weight", weight if weight is not None else None)
        self.reward = reward
        self.punish = punish
        self.dist_penalty = dist_penalty
        self.use_distance = use_distance
        self.label_smoothing = label_smoothing
        self.normalize_dist = normalize_dist
        self.symmetric_reward_punish = symmetric_reward_punish
        self.min_loss = min_loss
        
        print(f"✓ RewardPunishCrossEntropy 初始化:")

    def forward(self, logits, targets):
        num_classes = logits.size(1)
        
        # ========= Soft Label with Smoothing =========
        with torch.no_grad():
            smooth = self.label_smoothing
            true_dist = torch.zeros_like(logits)
            true_dist.fill_(smooth / (num_classes - 1))
            true_dist.scatter_(1, targets.unsqueeze(1), 1 - smooth)
        
        # ========= CE Replacement: KLDiv (Soft Label CE) =========
        log_probs = F.log_softmax(logits, dim=1)
        ce = F.kl_div(log_probs, true_dist, reduction="none").sum(dim=1)
        
        # 數值穩定性檢查
        if torch.isnan(ce).any() or torch.isinf(ce).any():
            print("⚠️  Warning: NaN or Inf detected in CE loss!")
            ce = torch.nan_to_num(ce, nan=0.0, posinf=1e6, neginf=-1e6)
        
        # 應用類別權重
        if self.weight is not None:
            weight_per_sample = self.weight[targets]
            ce = ce * weight_per_sample
        
        # ========= 預測 & Mask =========
        probs = F.softmax(logits, dim=1)
        preds = probs.argmax(dim=1)
        correct_mask = (preds == targets).float()
        wrong_mask = 1 - correct_mask
        
        # ========= Reward/Punish =========
        if self.symmetric_reward_punish:
            # 對稱版本（對數空間）
            reward_factor = torch.exp(torch.tensor(-self.reward, device=logits.device))
            punish_factor = torch.exp(torch.tensor(self.punish, device=logits.device))
        else:
            # 原始版本
            reward_factor = 1 - self.reward
            punish_factor = 1 + self.punish
        
        loss = ce * (correct_mask * reward_factor + wrong_mask * punish_factor)
        
        # ========= 距離懲罰 =========
        if self.use_distance:
            class_idx = torch.arange(num_classes, device=logits.device, dtype=logits.dtype)
            expected_class = (probs * class_idx).sum(dim=1)
            dist = (expected_class - targets.float()).abs()
            
            # 歸一化距離
            if self.normalize_dist:
                max_dist = num_classes - 1
                dist = dist / max_dist
            
            loss += wrong_mask * dist * self.dist_penalty
        
        # 防止梯度消失
        if self.min_loss > 0:
            loss = torch.clamp(loss, min=self.min_loss)
        
        return loss.mean()


# ==================== ResNet Backbone ====================
class ResNetBackbone(nn.Module):
    """ResNet特徵提取器 (不含分類層)"""
    def __init__(self, weights=ResNet18_Weights.DEFAULT):
        super().__init__()
        backbone = resnet18(weights=weights)
        self.features = nn.Sequential(*list(backbone.children())[:-1])
        self.feature_dim = 512
    
    def forward(self, x):
        feat = self.features(x)
        return feat.view(feat.size(0), -1)


# ==================== 新增 MobileNetV2 Backbone ====================
class MobileNetV2Backbone(nn.Module):
    """MobileNetV2 特徵提取器 (參數量僅 3.5M)"""
    def __init__(self, weights=MobileNet_V2_Weights.DEFAULT):
        super().__init__()
        backbone = mobilenet_v2(weights=weights)
        # MobileNetV2 的特徵提取部分
        self.features = backbone.features
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.feature_dim = 1280  # MobileNetV2 輸出維度
        
        print(f"✓ MobileNetV2 初始化完成，特徵維度: {self.feature_dim}")
    
    def forward(self, x):
        x = self.features(x)
        x = self.avgpool(x)
        return x.view(x.size(0), -1)


class EfficientNetB3Backbone(nn.Module):
    def __init__(self, weights=EfficientNet_B3_Weights.DEFAULT):
        super().__init__()
        backbone = efficientnet_b3(weights=weights)

        self.features = backbone.features
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.feature_dim = backbone.classifier[1].in_features
        print(f"✓ EfficientNet-B3 初始化完成，特徵維度: {self.feature_dim}")

    def forward(self, x):
        x = self.features(x)
        x = self.pool(x)
        return torch.flatten(x, 1)



# ==================== 新增統一 Backbone 工廠函數 ====================
def get_backbone(backbone_type='resnet18', pretrained=True):
    """
    獲取指定的 Backbone
    
    Args:
        backbone_type: 'resnet18', 'mobilenetv2', 'efficientnet_B3'
        pretrained: 是否使用預訓練權重
    
    Returns:
        backbone: Backbone 模型
    """
    backbone_type = backbone_type.lower()
    
    if backbone_type == 'resnet18':
        weights = ResNet18_Weights.DEFAULT if pretrained else None
        return ResNetBackbone(weights)
    
    elif backbone_type == 'mobilenetv2':
        weights = MobileNet_V2_Weights.DEFAULT if pretrained else None
        return MobileNetV2Backbone(weights)
    
    elif backbone_type == 'efficientnet_b3':
        weights = EfficientNet_B3_Weights.DEFAULT if pretrained else None
        return EfficientNetB3Backbone(weights)
    
    else:
        raise ValueError(f"不支援的 backbone 類型: {backbone_type}")


# ==================== 基礎ResNet分類器 ====================
class BasicResNetClassifier(nn.Module):
    """基礎ResNet分類器 (Backbone + FC, 不使用metadata)"""
    def __init__(self, num_classes=5, weights=ResNet18_Weights.DEFAULT, 
                 backbone_type='resnet18'):  # 新增參數
        super().__init__()
        self.num_classes = num_classes
        
        # 使用工廠函數獲取 Backbone
        if backbone_type == 'resnet18':
            # 保持向後兼容
            self.backbone = ResNetBackbone(weights)
        else:
            self.backbone = get_backbone(backbone_type, pretrained=(weights is not None))
        
        in_features = self.backbone.feature_dim
        
        # 增強正則化
        if num_classes == 2:
            self.classifier = nn.Sequential(
                nn.Linear(in_features, 256),
                nn.ReLU(),
                nn.BatchNorm1d(256),
                nn.Dropout(0.5),
                nn.Linear(256, 1)
            )
        else:
            self.classifier = nn.Sequential(
                nn.Linear(in_features, 256),
                nn.ReLU(),
                nn.BatchNorm1d(256),
                nn.Dropout(0.5),
                nn.Linear(256, num_classes)
            )
        
        print(f"✓ 分類器初始化完成 (backbone={backbone_type}, classes={num_classes})")
    
    def forward(self, x):
        feat = self.backbone(x)
        logits = self.classifier(feat)
        
        if self.num_classes == 2:
            return logits.squeeze(-1)
        return logits
    
    def freeze_backbone_partial(self):
        """凍結backbone前半部（針對不同架構調整）"""
        if isinstance(self.backbone, ResNetBackbone):
            for name, param in self.backbone.named_parameters():
                if any(layer in name for layer in ['layer1', 'layer2']):
                    param.requires_grad = False
            print("🔒 已凍結 ResNet layer1, layer2")
        
        elif isinstance(self.backbone, MobileNetV2Backbone):
            # MobileNetV2: 凍結前 10 個 inverted residual blocks
            for i, module in enumerate(self.backbone.features):
                if i < 10:
                    for param in module.parameters():
                        param.requires_grad = False
            print("🔒 已凍結 MobileNetV2 前 10 層")
        
        elif isinstance(self.backbone, EfficientNetB3Backbone):
            # EfficientNet: 凍結前 3 個 stage
            for i, module in enumerate(self.backbone.features):
                if i < 3:
                    for param in module.parameters():
                        param.requires_grad = False
            print("🔒 已凍結 EfficientNet 前 3 個 stage")
    
    def unfreeze_all(self):
        """解凍所有層"""
        for param in self.parameters():
            param.requires_grad = True
        print("🔓 已解凍所有層")


# ==================== MLP分類器 ====================
class MLPClassifier(nn.Module):
    """MLP分類器 (Backbone + MLP + FC)"""
    def __init__(self, num_classes=5, meta_dim=Config.meta_dim, 
                 weights=ResNet18_Weights.DEFAULT, backbone_type='resnet18'):  # 新增參數
        super().__init__()
        self.num_classes = num_classes
        self.meta_dim = meta_dim
        
        # 使用工廠函數獲取 Backbone
        if backbone_type == 'resnet18':
            self.backbone = ResNetBackbone(weights)
        else:
            self.backbone = get_backbone(backbone_type, pretrained=(weights is not None))
        
        in_features = self.backbone.feature_dim
        
        # image feature MLP - 增強正則化
        self.feature_mlp = nn.Sequential(
            nn.Linear(in_features, 256),
            nn.ReLU(),
            nn.BatchNorm1d(256),
            nn.Dropout(0.5)
        )

        # metadata MLP - 增強正則化
        self.meta_mlp = nn.Sequential(
            nn.Linear(meta_dim, 32),
            nn.ReLU(),
            nn.BatchNorm1d(32),
            nn.Dropout(0.3)
        )

        # 最終分類器
        if num_classes == 2:
            self.classifier = nn.Linear(256 + 32, 1)
        else:
            self.classifier = nn.Linear(256 + 32, num_classes)
        
        print(f"✓ MLP分類器初始化完成 (backbone={backbone_type}, meta_dim={meta_dim})")

    def forward(self, x, meta):
        # backbone 特徵
        feat = self.backbone(x)
        feat = self.feature_mlp(feat)

        # metadata 特徵
        meta_feat = self.meta_mlp(meta)
        
        # concat metadata
        x = torch.cat([feat, meta_feat], dim=1)
        
        # 最終分類
        logits = self.classifier(x)
        
        if self.num_classes == 2:
            return logits.squeeze(-1)
        return logits
    
    def freeze_backbone_partial(self):
        """凍結backbone前半部"""
        if isinstance(self.backbone, ResNetBackbone):
            for name, param in self.backbone.named_parameters():
                if any(layer in name for layer in ['layer1', 'layer2']):
                    param.requires_grad = False
            print("🔒 已凍結 ResNet layer1, layer2")
        
        elif isinstance(self.backbone, MobileNetV2Backbone):
            for i, module in enumerate(self.backbone.features):
                if i < 10:
                    for param in module.parameters():
                        param.requires_grad = False
            print("🔒 已凍結 MobileNetV2 前 10 層")
        
        elif isinstance(self.backbone, EfficientNetB3Backbone):
            for i, module in enumerate(self.backbone.features):
                if i < 3:
                    for param in module.parameters():
                        param.requires_grad = False
            print("🔒 已凍結 EfficientNet 前 3 個 stage")
    
    def unfreeze_all(self):
        """解凍所有層"""
        for param in self.parameters():
            param.requires_grad = True
        print("🔓 已解凍所有層")


# ==================== 特徵萃取器 ====================
class FeatureExtractor(nn.Module):
    """用於XGBoost/RF的特徵萃取器"""
    def __init__(self, pretrained_model_path, num_classes=5, device='cuda'):
        super().__init__()
        
        # 自動偵測模型類型
        state_dict = torch.load(pretrained_model_path, map_location=device, weights_only=True)
        
        # 檢查是否為 MobileNetV2 或 EfficientNet
        is_mobilenet = any('features.0.0.weight' in k and state_dict[k].shape[1] == 3 
                          and state_dict[k].shape[0] == 32 for k in state_dict.keys())
        is_efficientnet = any('features.0.0.weight' in k and state_dict[k].shape[1] == 3 
                             and state_dict[k].shape[0] == 32 for k in state_dict.keys())
        
        # 載入對應模型
        if is_mobilenet:
            full_model = BasicResNetClassifier(
                num_classes=num_classes, 
                backbone_type='mobilenetv2'
            )
            print("✓ 偵測到 MobileNetV2 模型")
        elif is_efficientnet:
            full_model = BasicResNetClassifier(
                num_classes=num_classes, 
                backbone_type='efficientnet_B3'
            )
            print("✓ 偵測到 EfficientNet 模型")
        else:
            full_model = BasicResNetClassifier(num_classes=num_classes)
            print("✓ 偵測到 ResNet18 模型")
        
        full_model.load_state_dict(state_dict)
        
        # 只使用backbone
        self.backbone = full_model.backbone
        self.backbone.eval()
        
        print(f"✓ 特徵萃取器已載入，輸出維度: {self.backbone.feature_dim}")
    
    def forward(self, x):
        """輸出: (batch_size, feature_dim) 的特徵向量"""
        with torch.no_grad():
            return self.backbone(x)


# ==================== 工具函數 ====================
def load_model_weights(model, path, device='cuda'):
    """載入模型權重"""
    model.load_state_dict(torch.load(path, map_location=device, weights_only=True))
    print(f"✓ 模型已載入: {path}")
    return model


def save_model_weights(model, path):
    """儲存模型權重"""
    torch.save(model.state_dict(), path)
    print(f"✓ 模型已儲存: {path}")


# ==================== ML Classifiers (保持不變) ====================
"""
ml_classifiers - 機器學習分類器
包含: XGBoost, Random Forest
"""
import numpy as np
import pickle
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import xgboost as xgb
XGBOOST_AVAILABLE = True


class XGBoostClassifier:
    """XGBoost分類器封裝"""
    
    def __init__(self, n_estimators=200, max_depth=6, learning_rate=0.1,
                 subsample=0.8, colsample_bytree=0.8, random_state=42):
        if not XGBOOST_AVAILABLE:
            raise ImportError("XGBoost未安裝")
        
        if random_state is None:
            random_state = Config.SEED
        
        self.model = xgb.XGBClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            random_state=random_state,
            eval_metric='mlogloss',
            use_label_encoder=False
        )
        self.is_trained = False
    
    def train(self, X_train, y_train, X_val=None, y_val=None):
        """訓練模型"""
        print(f"訓練XGBoost: {X_train.shape[0]}樣本, {X_train.shape[1]}特徵")
        
        if X_val is not None and y_val is not None:
            eval_set = [(X_train, y_train), (X_val, y_val)]
            self.model.fit(
                X_train, y_train,
                eval_set=eval_set,
                verbose=False
            )
        else:
            self.model.fit(X_train, y_train)
        
        self.is_trained = True
        
        train_acc = accuracy_score(y_train, self.model.predict(X_train))
        print(f"訓練準確率: {train_acc:.4f}")
        
        if X_val is not None and y_val is not None:
            val_pred = self.model.predict(X_val)
            val_acc = accuracy_score(y_val, val_pred)
            print(f"驗證準確率: {val_acc:.4f}")
            print("\n分類報告：")
            print(classification_report(y_val, val_pred))
            return train_acc, val_acc
        
        return train_acc, None
    
    def predict(self, X):
        if not self.is_trained:
            raise ValueError("模型尚未訓練")
        return self.model.predict(X)
    
    def predict_proba(self, X):
        if not self.is_trained:
            raise ValueError("模型尚未訓練")
        return self.model.predict_proba(X)
    
    def evaluate(self, X_test, y_test, class_names=None):
        y_pred = self.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        cm = confusion_matrix(y_test, y_pred)
        
        print(f"\n{'='*60}")
        print(f"測試準確率: {acc:.4f}")
        print(f"{'='*60}")
        print(classification_report(y_test, y_pred, target_names=class_names))
        print("\n混淆矩陣：")
        print(cm)
        
        return {
            'accuracy': acc,
            'predictions': y_pred,
            'probabilities': self.predict_proba(X_test),
            'confusion_matrix': cm
        }
    
    def save(self, path):
        with open(path, 'wb') as f:
            pickle.dump(self.model, f)
        print(f"✓ 模型已儲存: {path}")
    
    def load(self, path):
        with open(path, 'rb') as f:
            self.model = pickle.load(f)
        self.is_trained = True
        print(f"✓ 模型已載入: {path}")


class RandomForestClassifier_:
    """Random Forest分類器封裝"""
    
    def __init__(self, n_estimators=300, max_depth=12, min_samples_split=5,
                 min_samples_leaf=2, max_features='sqrt', random_state=42):
        
        if random_state is None:
            random_state = Config.SEED

        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            random_state=random_state,
            n_jobs=-1,
            class_weight='balanced'
        )
        self.is_trained = False
    
    def train(self, X_train, y_train, X_val=None, y_val=None):
        print(f"訓練Random Forest: {X_train.shape[0]}樣本, {X_train.shape[1]}特徵")
        
        self.model.fit(X_train, y_train)
        self.is_trained = True
        
        train_acc = accuracy_score(y_train, self.model.predict(X_train))
        print(f"訓練準確率: {train_acc:.4f}")
        
        if X_val is not None and y_val is not None:
            val_pred = self.model.predict(X_val)
            val_acc = accuracy_score(y_val, val_pred)
            print(f"驗證準確率: {val_acc:.4f}")
            print("\n分類報告：")
            print(classification_report(y_val, val_pred))
            return train_acc, val_acc
        
        return train_acc, None
    
    def predict(self, X):
        if not self.is_trained:
            raise ValueError("模型尚未訓練")
        return self.model.predict(X)
    
    def predict_proba(self, X):
        if not self.is_trained:
            raise ValueError("模型尚未訓練")
        return self.model.predict_proba(X)
    
    def evaluate(self, X_test, y_test, class_names=None):
        y_pred = self.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        cm = confusion_matrix(y_test, y_pred)
        
        print(f"\n{'='*60}")
        print(f"測試準確率: {acc:.4f}")
        print(f"{'='*60}")
        print(classification_report(y_test, y_pred, target_names=class_names))
        print("\n混淆矩陣：")
        print(cm)
        
        return {
            'accuracy': acc,
            'predictions': y_pred,
            'probabilities': self.predict_proba(X_test),
            'confusion_matrix': cm
        }
    
    def save(self, path):
        with open(path, 'wb') as f:
            pickle.dump(self.model, f)
        print(f"✓ 模型已儲存: {path}")
    
    def load(self, path):
        with open(path, 'rb') as f:
            self.model = pickle.load(f)
        self.is_trained = True
        print(f"✓ 模型已載入: {path}")


def get_classifier(classifier_type, **kwargs):
    """根據類型創建分類器"""
    classifiers = {
        'xgboost': XGBoostClassifier,
        'rf': RandomForestClassifier_
    }
    
    clf_class = classifiers.get(classifier_type.lower())
    if clf_class is None:
        raise ValueError(f"不支援的分類器類型: {classifier_type}")
    
    return clf_class(**kwargs)