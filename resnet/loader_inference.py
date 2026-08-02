"""
loader_inference.py - 數據載入器
支援metadata整合
"""
import os
import json
import torch
import pandas as pd
import numpy as np
from pathlib import Path
from PIL import Image
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import transforms
from torchvision.datasets import ImageFolder

from trainer import Config
from base_models import MLPClassifier, FeatureExtractor, load_model_weights, XGBoostClassifier, RandomForestClassifier_

# ==================== 帶Metadata與額外影像特徵的Dataset ====================
class ImageFolderWithMeta(ImageFolder):
    """自動適配 metadata 維度的 Dataset"""

    def __init__(self, root, meta_csv, transform=None,
                 stats=None, is_train=False):
        
        self.root = root
        self.transform = transform

        
        # 獲取 metadata 配置
        from trainer import Config
        self.meta_config = Config.get_metadata_config()
        self.actual_classes = list(Config.CLASS_NAMES.values())
        
        # 掃描所有影像
        self.samples = []
        class_to_idx = {}
        for class_dir in os.listdir(root):
            class_path = os.path.join(root, class_dir)
            if not os.path.isdir(class_path):
                continue
            if class_dir not in Config.DIR_TO_CLASS:
                raise ValueError(f"資料夾名稱 {class_dir} 不在 DIR_TO_CLASS 內")
            label = Config.DIR_TO_CLASS[class_dir]
            class_to_idx[class_dir] = label
            for fname in os.listdir(class_path):
                if fname.lower().endswith(('.png', '.jpg', '.jpeg')):
                    img_path = os.path.join(class_path, fname)
                    self.samples.append((img_path, label))
        
        self.class_to_idx = class_to_idx
        self.classes = sorted(class_to_idx.keys())
        
        # ======== 使用 MetadataConfig 載入並預處理 metadata ========
        meta_df = self.meta_config.load_and_preprocess_metadata(meta_csv)
        
        # ======== 計算或載入統計值 ========
        if is_train:
            # 訓練集: 計算統計值
            current_image_names = [os.path.basename(p) for p, _ in self.samples]
            self.stats = self.meta_config.compute_stats(meta_df, current_image_names)
        else:
            # 驗證/測試集: 使用傳入的統計值
            if stats is None:
                raise ValueError("驗證/測試集必須提供 stats 參數")
            self.stats = stats
        
        # ======== 標準化 metadata ========
        meta_normalized = self.meta_config.normalize_metadata(meta_df, self.stats)
        
        # ======== 創建 metadata 字典 ========
        self.meta_dict = self.meta_config.create_metadata_dict(meta_normalized)

    def __getitem__(self, index):
        path, label = self.samples[index]
        image = Image.open(path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        
        fname = os.path.basename(path)
        # 如果找不到 metadata，回傳零向量（維度自動匹配）
        meta_tensor = self.meta_dict.get(
            fname, 
            torch.zeros(self.meta_config.meta_dim)
        )
        return image, meta_tensor, label

# ==================== DataLoader工廠 ====================
def add_gaussian_noise(x):
    return x + 0.01*torch.randn_like(x)

def get_dataloaders(dataset_path, meta_csv, batch_size=8, 
                   use_weighted_sampler=False, save_stats=True):
    """
    創建train/val/test DataLoader
    
    Returns:
        train_loader, test_loader, val_loader
    """

    # 設置固定隨機種子
    from trainer import Config, seed_worker
    Config.set_seed()
    g = torch.Generator()
    g.manual_seed(Config.SEED)

    # 訓練集數據增強
    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.RandomRotation(degrees=20),
        transforms.RandomAffine(degrees=0, translate=(0.05,0.05), scale=(0.9,1.1), shear=5),  #  平移/仿射
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        transforms.RandomErasing(p=0.3, scale=(0.02, 0.15), ratio=(0.3, 3.3))
    ])
    
    # 驗證/測試集轉換
    eval_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    # 訓練集
    train_dataset = ImageFolderWithMeta(
        root=f"{dataset_path}/train",
        meta_csv=meta_csv,
        transform=train_transform,
        is_train=True
    )
    
    # 儲存訓練集統計值
    if save_stats:
        stats_path = os.path.join(os.path.dirname(meta_csv), "train_stats.json")
        stats = train_dataset.stats  # 完整五欄位
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=2)
        if not getattr(get_dataloaders, "_printed", False):
            print(f"✓ 訓練集統計值已儲存至: {stats_path}")
        #for c in stats:
        #    print(f"  {c}_mean={stats[c]['mean']:.2f}, {c}_std={stats[c]['std']:.2f}")

    
    # 驗證集/測試集
    val_dataset = ImageFolderWithMeta(
        root=f"{dataset_path}/val",
        meta_csv=meta_csv,
        transform=eval_transform,
        stats=train_dataset.stats,
        is_train=False
    )

    test_dataset = ImageFolderWithMeta(
        root=f"{dataset_path}/test",
        meta_csv=meta_csv,
        transform=eval_transform,
        stats=train_dataset.stats,
        is_train=False
    )
    
    if not getattr(get_dataloaders, "_printed", False):
        print(f"✓ 資料夾: {train_dataset.classes}")
        print(f"✓ 實際類別: {train_dataset.actual_classes}")
        get_dataloaders._printed = True
    
    # WeightedRandomSampler
    sampler = None
    shuffle = True
    
    if use_weighted_sampler:
        class_counts = np.bincount([label for _, label in train_dataset.samples])
        print(f"訓練集類別分布: {class_counts}")
        
        class_weights = 1.0 / class_counts
        sample_weights = [class_weights[label] for _, label in train_dataset.samples]
        sample_weights = torch.DoubleTensor(sample_weights)
        
        sampler = WeightedRandomSampler(
            weights=sample_weights,
            num_samples=len(sample_weights),
            replacement=True
        )
        shuffle = False
    
    num_workers = 0
    # 創建DataLoader
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size,
        sampler=sampler,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=True,
        drop_last=True,
        worker_init_fn=seed_worker if num_workers > 0 else None,
        generator=g
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True,
        worker_init_fn=seed_worker if num_workers > 0 else None,
        generator=g
    )
    
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True,
        worker_init_fn=seed_worker if num_workers > 0 else None,
        generator=g
    )

    return train_loader, test_loader, val_loader


# ==================== 類別權重計算 ====================
def get_class_weights(train_loader, num_classes=5, device='cuda'):
    """計算類別權重（用於損失函數）"""
    class_counts = torch.zeros(num_classes)
    
    for batch in train_loader:
        # 支援 (image, meta, label) 與 (image, label)
        if isinstance(batch, (list, tuple)) and len(batch) == 3:
            _, _, labels = batch
        elif isinstance(batch, (list, tuple)) and len(batch) == 2:
            _, labels = batch
        else:
            raise ValueError(
                f"Unexpected batch format: {type(batch)} len="
                f"{len(batch) if hasattr(batch, '__len__') else 'N/A'}"
            )
        for label in labels:
            class_counts[label] += 1
    
    print(f"類別分布: {class_counts.numpy()}")
    
    total = class_counts.sum()
    class_weights = total / (num_classes * class_counts.sqrt())
    class_weights = class_weights / class_weights.sum() * num_classes
    # 調整特定類別權重
    #if num_classes == 5:
    #    class_weights[0] *= 1.3 
    #    class_weights[1] *= 1.4 
    #    class_weights[2] *= 1.2 
    #    class_weights[3] *= 0.85
    #    class_weights[4] *= 1.5

    print(f"類別權重: {class_weights.numpy()}")
    return class_weights.to(device)


"""
inference- 統一推論接口
支援 MLP, XGBoost, RandomForest 三種模型
"""
 
# ==================== 基礎推論器 ====================
class BaseInference:
    """基礎推論器（自動適配 metadata 維度）"""
    
    def __init__(self, stats_path=None, train_stats=None, device='cuda'):
        from trainer import Config
        self.device = device
        self.meta_config = Config.get_metadata_config()
        Config.set_seed()

        # 統計值載入：只有一個優先順序，不重複設定
        if train_stats is not None:
            self.stats = train_stats
            print("✓ 使用傳入的統計值")
        elif stats_path is not None and os.path.exists(stats_path):
            with open(stats_path, 'r') as f:
                self.stats = json.load(f)
            print(f"✓ 從檔案載入統計值: {stats_path}")
        else:
            # 動態產生預設值，根據當前 meta_cols 而不是寫死
            self.stats = {
                col: {
                    'mean': self.meta_config.get_fallback_value(col),
                    'std': 1.0
                }
                for col in self.meta_config.meta_cols
                if col not in self.meta_config.binary_cols
            }
            print("⚠️  使用預設統計值，推論結果可能不準確")
        
        # 驗證統計值完整性（只檢查連續欄位）
        continuous_cols = [c for c in self.meta_config.meta_cols 
                        if c not in self.meta_config.binary_cols]
        missing_cols = set(continuous_cols) - set(self.stats.keys())
        if missing_cols:
            raise ValueError(
                f"❌ 統計值缺少連續欄位: {missing_cols}\n"
                f"   (二元欄位 {self.meta_config.binary_cols} 不需要統計值)"
            )
        
        # 設定圖片轉換
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])
        
        def tta(extra=None):
            return transforms.Compose([
                transforms.Resize((224, 224)),
                *(extra or []),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                )
            ])

        self.tta_transforms = [
            tta(),  # 原圖
            tta([transforms.RandomRotation((5, 5))]),
            tta([transforms.RandomRotation((10, 10))]),
            tta([transforms.RandomRotation((-5, -5))]),
            tta([transforms.ColorJitter(brightness=0.15)]),
            tta([transforms.ColorJitter(contrast=0.15)]),
            tta([transforms.ColorJitter(brightness=0.1, contrast=0.1)])
        ]

    
    def load_train_stats(self, stats_path=None, train_stats=None):
        """
        載入訓練集統計值
        
        Args:
            stats_path: 統計值 JSON 檔案路徑
            train_stats: 統計值字典
        """
        #  優先使用字典
        if train_stats is not None:
            self.stats = train_stats
            print("✓ 載入統計值（字典）:")
            #for c in self.stats:
            #    print(f"  {c}_mean={self.stats[c]['mean']:.2f}, {c}_std={self.stats[c]['std']:.2f}")
        
        #  向後兼容：從檔案載入
        elif stats_path is not None and os.path.exists(stats_path):
            with open(stats_path, 'r') as f:
                self.stats = json.load(f)
            print(f"✓ 載入統計值（檔案）: {stats_path}")
            #for c in self.stats:
            #    print(f"  {c}_mean={self.stats[c]['mean']:.2f}, {c}_std={self.stats[c]['std']:.2f}")

    def preprocess_metadata(self, **kwargs):
        """
        預處理 metadata（自動適配所有欄位）
        
        Args:
            **kwargs: 欄位名稱與值的對應（如 age=50, Length_px=200）
        
        Returns:
            標準化後的 tensor
        """
        return self.meta_config.prepare_inference_metadata(self.stats, **kwargs)


    def preprocess_image_tta(self, image_path):
        """
        使用 TTA 預處理圖片
        Returns:
            tensors: List[Tensor] - 8個增強版本的圖片
            image: PIL.Image - 原始圖片（用於顯示）
        """
        image = Image.open(image_path).convert('RGB')
        tensors = []
        
        for transform in self.tta_transforms:
            tensor = transform(image).unsqueeze(0)
            tensors.append(tensor)
        
        return tensors, image
    
    def preprocess_image(self, image_path):
        """預處理圖片"""
        image = Image.open(image_path).convert('RGB')
        tensor = self.transform(image).unsqueeze(0)
        return tensor, image
    
    def predict(self, image_path, age=None, gender=None):
        """預測單張圖片（需子類實現）"""
        raise NotImplementedError


# ==================== ResNet推論器 ====================
class ResNetInference(BaseInference):
    """基礎ResNet推論 (不使用metadata)"""
    
    def __init__(self, model, device='cuda', stats_path=None, train_stats=None):
        super().__init__(
            stats_path=stats_path, 
            train_stats=train_stats,  #  傳入字典
            device=device
        )
        self.model = model.to(device)
        self.model.eval()
        self.num_classes = model.num_classes if hasattr(model, 'num_classes') else None
    
    def predict(self, image_path, **metadata_kwargs):
        """
        預測單張圖片 (忽略metadata參數)
        Returns:
            pred_class: int
            proba: numpy array
        """
        # 預處理圖片
        image_tensor, _ = self.preprocess_image(image_path)
        image_tensor = image_tensor.to(self.device)
        
        # 推論
        with torch.no_grad():
            output = self.model(image_tensor)
            
            #  根據類別數處理輸出
            if self.num_classes == 2:
                # 二元分類: output 是 [batch] 的 logits
                prob_class1 = torch.sigmoid(output)
                proba = torch.stack([1 - prob_class1, prob_class1], dim=1)
                pred_class = (prob_class1 > 0.5).long().item()
                proba = proba.cpu().numpy()[0]
            else:
                # 多類別分類: output 是 [batch, num_classes]
                proba = torch.nn.functional.softmax(output, dim=1)
                pred_class = torch.argmax(proba, dim=1).item()
                proba = proba.cpu().numpy()[0]
        
        return pred_class, proba
    
    def predict_with_tta(self, image_path, **metadata_kwargs):
        """
        使用 TTA 預測單張圖片
        Returns:
            pred_class: int - 預測類別
            proba: numpy array - 平均後的機率分布
        """
        # 獲取5個增強版本
        image_tensors, _ = self.preprocess_image_tta(image_path)
        
        all_probas = []
        
        with torch.no_grad():
            for image_tensor in image_tensors:
                image_tensor = image_tensor.to(self.device)
                output = self.model(image_tensor)
                
                if self.num_classes == 2:
                    prob_class1 = torch.sigmoid(output)
                    proba = torch.stack([1 - prob_class1, prob_class1], dim=1)
                else:
                    proba = torch.nn.functional.softmax(output, dim=1)
                
                all_probas.append(proba.cpu().numpy()[0])
        
        # 平均所有增強版本的預測
        avg_proba = np.mean(all_probas, axis=0)
        pred_class = np.argmax(avg_proba)
        
        return pred_class, avg_proba

# ==================== MLP推論器 ====================
class MLPInference(BaseInference):
    """MLP 推論器（自動適配 metadata 維度）"""
    
    def __init__(self, model, device='cuda', stats_path=None, train_stats=None):
        super().__init__(stats_path=stats_path, train_stats=train_stats, device=device)
        self.model = model.to(device)
        self.model.eval()
        self.num_classes = model.num_classes if hasattr(model, 'num_classes') else None
    
    def predict(self, image_path, **metadata_kwargs):
        """
        預測單張圖片（自動適配所有 metadata 欄位）
        
        Args:
            image_path: 圖片路徑
            **metadata_kwargs: metadata 欄位值（如 age=50, Length_px=200）
        
        Returns:
            pred_class, proba
        """
        # 預處理圖片
        image_tensor, _ = self.preprocess_image(image_path)
        image_tensor = image_tensor.to(self.device)
        
        # 預處理 metadata（自動處理所有欄位，缺失值用 mean 填充）
        meta_tensor = self.preprocess_metadata(**metadata_kwargs)
        meta_tensor = meta_tensor.unsqueeze(0).to(self.device)
        
        # 推論
        with torch.no_grad():
            output = self.model(image_tensor, meta_tensor)
            
            if self.num_classes == 2:
                prob_class1 = torch.sigmoid(output)
                proba = torch.stack([1 - prob_class1, prob_class1], dim=1)
                pred_class = (prob_class1 > 0.5).long().item()
                proba = proba.cpu().numpy()[0]
            else:
                proba = torch.nn.functional.softmax(output, dim=1)
                pred_class = torch.argmax(proba, dim=1).item()
                proba = proba.cpu().numpy()[0]
        
        return pred_class, proba

    def predict_with_tta(self, image_path, **metadata_kwargs):
        """使用 TTA 預測單張圖片"""
        # 獲取5個增強版本
        image_tensors, _ = self.preprocess_image_tta(image_path)
        
        # 處理 metadata（所有增強版本使用相同的metadata）
        meta_tensor = self.preprocess_metadata(**metadata_kwargs)
        meta_tensor = meta_tensor.unsqueeze(0).to(self.device)

        all_probas = []

        with torch.no_grad():
            for image_tensor in image_tensors:
                image_tensor = image_tensor.to(self.device)
                output = self.model(image_tensor, meta_tensor)
                
                if self.num_classes == 2:
                    prob_class1 = torch.sigmoid(output)
                    proba = torch.stack([1 - prob_class1, prob_class1], dim=1)
                else:
                    proba = torch.nn.functional.softmax(output, dim=1)
                
                all_probas.append(proba.cpu().numpy()[0])
        
        # 平均所有增強版本的預測
        avg_proba = np.mean(all_probas, axis=0)
        pred_class = np.argmax(avg_proba)
        
        return pred_class, avg_proba

# ==================== ML推論器 (XGBoost/RF) ====================
class MLClassifierInference(BaseInference):
    """XGBoost/RF推論"""
    
    def __init__(self, feature_extractor, classifier, device='cuda', 
                 stats_path=None, train_stats=None):
        super().__init__(
            stats_path=stats_path,
            train_stats=train_stats,  #  傳入字典
            device=device
        )
        self.feature_extractor = feature_extractor.to(device)
        self.classifier = classifier
        self.feature_extractor.eval()
    
    def predict(self, image_path, age=None, gender=None, Length_px=None, Entropy=None, Contrast_Ratio=None):
        """
        預測單張圖片
        Returns:
            pred_class: int
            proba: numpy array
        """
        # 預處理圖片
        image_tensor, _ = self.preprocess_image(image_path)
        image_tensor = image_tensor.to(self.device)
        
        # 萃取CNN特徵
        with torch.no_grad():
            cnn_features = self.feature_extractor(image_tensor)
            cnn_features = cnn_features.cpu().numpy()
        
        # Metadata缺值補平均
        age = self.stats['age']['mean'] if age is None else age
        gender = 0 if gender is None else (1.0 if gender in ['男','male','M',1] else 0.0)
        Length_px = self.stats['Length_px']['mean'] if Length_px is None else Length_px
        Entropy = self.stats['Entropy']['mean'] if Entropy is None else Entropy
        Contrast_Ratio = self.stats['Contrast_Ratio']['mean'] if Contrast_Ratio is None else Contrast_Ratio
        
        # 標準化
        age_norm = (age - self.stats['age']['mean']) / (self.stats['age']['std'] + 1e-10)
        length_norm = (Length_px - self.stats['Length_px']['mean']) / (self.stats['Length_px']['std'] + 1e-10)
        entropy_norm = (Entropy - self.stats['Entropy']['mean']) / (self.stats['Entropy']['std'] + 1e-10)
        contrast_norm = (Contrast_Ratio - self.stats['Contrast_Ratio']['mean']) / (self.stats['Contrast_Ratio']['std'] + 1e-10)

        
        # metadata tensor
        meta_features = np.array([age_norm, length_norm, entropy_norm, contrast_norm], dtype=np.float32).reshape(1, -1)
        
        # 合併特徵
        features = np.hstack([cnn_features, meta_features])
        
        # 推論
        pred_class = self.classifier.predict(features)[0]
        proba = self.classifier.predict_proba(features)[0]
        
        return pred_class, proba
    
    def predict_with_tta(self, image_path, age=None, gender=None, Length_px=None, 
                         Entropy=None, Contrast_Ratio=None):
        """使用 TTA 預測單張圖片"""
        # 獲取5個增強版本
        image_tensors, _ = self.preprocess_image_tta(image_path)
        
        # 萃取每個增強版本的CNN特徵
        all_cnn_features = []
        
        with torch.no_grad():
            for image_tensor in image_tensors:
                image_tensor = image_tensor.to(self.device)
                cnn_feat = self.feature_extractor(image_tensor)
                all_cnn_features.append(cnn_feat.cpu().numpy())
        
        # 平均CNN特徵
        avg_cnn_features = np.mean(all_cnn_features, axis=0)
        
        # 處理 metadata（與原版相同）
        age = self.stats['age']['mean'] if age is None else age
        gender = 0 if gender is None else (1.0 if gender in ['男','male','M',1] else 0.0)
        Length_px = self.stats['Length_px']['mean'] if Length_px is None else Length_px
        Entropy = self.stats['Entropy']['mean'] if Entropy is None else Entropy
        Contrast_Ratio = self.stats['Contrast_Ratio']['mean'] if Contrast_Ratio is None else Contrast_Ratio
        
        # 標準化
        age_norm = (age - self.stats['age']['mean']) / (self.stats['age']['std'] + 1e-10)
        length_norm = (Length_px - self.stats['Length_px']['mean']) / (self.stats['Length_px']['std'] + 1e-10)
        entropy_norm = (Entropy - self.stats['Entropy']['mean']) / (self.stats['Entropy']['std'] + 1e-10)
        contrast_norm = (Contrast_Ratio - self.stats['Contrast_Ratio']['mean']) / (self.stats['Contrast_Ratio']['std'] + 1e-10)
        
        meta_features = np.array([age_norm, length_norm, entropy_norm, contrast_norm], 
                                dtype=np.float32).reshape(1, -1)
        
        # 合併特徵
        features = np.hstack([avg_cnn_features, meta_features])
        
        # 推論
        pred_class = self.classifier.predict(features)[0]
        proba = self.classifier.predict_proba(features)[0]
        
        return pred_class, proba


# ==================== 推論pipline ====================
def create_inference_pipeline(model_type, model_path, device='cuda', 
                              stats_path=None, train_stats=None, **kwargs):
    """
    創建推論Pipeline
    
    Args:
        model_type: 'resnet', 'mlp', 'xgboost', 'rf'
        model_path: 模型路徑
        device: 設備
        stats_path: 統計值檔案路徑（向後兼容）
        train_stats: 統計值字典（新方法，優先使用）
        **kwargs: 其他參數
    
    Returns:
        推論器實例
    """
    config = Config()
    
    if model_type.lower() == 'resnet':
        # 載入基礎ResNet模型
        from base_models import BasicResNetClassifier
        model = BasicResNetClassifier(num_classes=config.class_num)
        model = load_model_weights(model, model_path, device)
        inference = ResNetInference(
            model, device, 
            stats_path=stats_path, 
            train_stats=train_stats  #  傳入字典
        )

    elif model_type.lower() == 'mobilenetv2':
        from base_models import BasicResNetClassifier
        model = BasicResNetClassifier(
            num_classes=config.class_num, 
            backbone_type='mobilenetv2'
        )
        model = load_model_weights(model, model_path, device)
        inference = ResNetInference(
            model, device,
            stats_path=stats_path,
            train_stats=train_stats
        )
    
    elif model_type.lower() == 'efficientnetb3':
        from base_models import BasicResNetClassifier
        model = BasicResNetClassifier(
            num_classes=config.class_num,
            backbone_type='efficientnet_b3'
        )
        model = load_model_weights(model, model_path, device)
        inference = ResNetInference(
            model, device,
            stats_path=stats_path,
            train_stats=train_stats
        )

    elif model_type.lower() in ['mlp', 'mobilenetv2_mlp', 'efficientnetb3_mlp']:
        # 自動偵測 backbone 類型
        if 'mobilenetv2' in model_type.lower():
            backbone_type = 'mobilenetv2'
        elif 'efficientnetb3' in model_type.lower() or 'efficientnet_b3' in model_type.lower():
            backbone_type = 'efficientnet_b3'
        else:
            backbone_type = 'resnet18'
        
        model = MLPClassifier(
            num_classes=config.class_num, 
            meta_dim=Config.meta_dim,
            backbone_type=backbone_type
        )
        model = load_model_weights(model, model_path, device)
        inference = MLPInference(
            model, device,
            stats_path=stats_path,
            train_stats=train_stats
        )

    elif model_type.lower() in ['xgboost', 'rf']:
        # XGBoost / RF
        if 'resnet_path' not in kwargs:
            raise ValueError("需要提供 resnet_path 參數")

        feature_extractor = FeatureExtractor(
            pretrained_model_path=kwargs['resnet_path'],
            num_classes=config.class_num,
            device=device
        ).to(device)

        if model_type.lower() == 'xgboost':
            classifier = XGBoostClassifier()
        else:
            classifier = RandomForestClassifier_()

        classifier.load(model_path)

        inference = MLClassifierInference(
            feature_extractor, classifier, device,
            stats_path=stats_path,
            train_stats=train_stats  #  傳入字典
        )
    
    else:
        raise ValueError(f"不支援的模型類型: {model_type}")
    
    return inference