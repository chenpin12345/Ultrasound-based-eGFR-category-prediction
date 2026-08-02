"""
metadata_manager.py - 自動化 Metadata 管理配置
只需在 Config 中設定 meta_cols,所有相關邏輯自動適配
支援二元欄位(不標準化)與連續欄位(標準化)
"""

import os
import json
import pandas as pd
import numpy as np
import torch
from typing import Dict, List, Any

class MetadataConfig:
    """Metadata 自動化配置管理器"""

    _printed = False  # 用於避免重複打印初始化訊息

    def __init__(self, meta_cols: List[str], metadata_csv_path: str, 
                 binary_cols: List[str] = None):
        """
        Args:
            meta_cols: 要使用的 metadata 欄位列表
            metadata_csv_path: metadata CSV 檔案路徑
            binary_cols: 二元欄位列表 (這些欄位不會被標準化)
        """
        self.meta_cols = meta_cols
        self.meta_dim = len(meta_cols)
        self.metadata_csv_path = metadata_csv_path
        
        # 定義哪些欄位是二元的 (0/1)，這些欄位不需要標準化
        default_binary_cols = ['gender', 'has_diabetes', 'diabetes', '有無糖尿病']
        self.binary_cols = set(binary_cols or default_binary_cols)
        
        # 欄位預處理器（可擴展）
        self.field_preprocessors = {
            'gender': self._parse_gender,
            # 如需新增特殊處理的欄位，在此添加
            # 'new_field': self._parse_new_field,
        }

        if not MetadataConfig._printed:
            print(f"✓ Metadata 配置初始化完成: {self.meta_cols}")
            binary_in_use = [c for c in self.meta_cols if c in self.binary_cols]
            if binary_in_use:
                print(f"  二元欄位(不標準化): {binary_in_use}")
            MetadataConfig._printed = True

    def _parse_gender(self, value):
        """性別欄位解析器"""
        if isinstance(value, str):
            return 1.0 if value in ['男', 'male', 'M', '1'] else 0.0
        return float(value)
    
    def load_and_preprocess_metadata(self, csv_path: str = None) -> pd.DataFrame:
        """
        載入並預處理 metadata
        
        Args:
            csv_path: CSV 路徑（可選，預設使用初始化時的路徑）
        
        Returns:
            預處理後的 DataFrame
        """
        if csv_path is None:
            csv_path = self.metadata_csv_path
        
        meta = pd.read_csv(csv_path)
        
        # 檢查所有必需欄位是否存在
        missing_cols = set(self.meta_cols) - set(meta.columns)
        if missing_cols:
            raise ValueError(f"❌ metadata.csv 缺少欄位: {missing_cols}")
        
        # 應用特殊預處理器
        for col in self.meta_cols:
            if col in self.field_preprocessors:
                meta[col] = meta[col].apply(self.field_preprocessors[col])
        
        return meta
    
    def compute_stats(self, meta_df: pd.DataFrame, 
                     image_names: List[str] = None) -> Dict[str, Dict[str, float]]:
        """
        計算統計值（僅針對指定圖片，二元欄位不計算統計值）
        
        Args:
            meta_df: metadata DataFrame
            image_names: 圖片名稱列表（用於過濾訓練集）
        
        Returns:
            統計值字典 {'col_name': {'mean': x, 'std': y}}
            注意: 二元欄位不會出現在統計值中
        """
        # 如果提供圖片列表，只計算這些圖片的統計值
        if image_names is not None:
            meta_df = meta_df[meta_df['image_name'].isin(image_names)]
        
        stats = {}
        for col in self.meta_cols:
            # 二元欄位跳過統計值計算
            if col in self.binary_cols:
                continue
            
            # 連續欄位計算統計值
            stats[col] = {
                'mean': float(meta_df[col].mean()),
                'std': float(meta_df[col].std())
            }
        
        return stats
    
    def normalize_metadata(self, meta_df: pd.DataFrame, 
                          stats: Dict[str, Dict[str, float]]) -> pd.DataFrame:
        """
        標準化 metadata (二元欄位保持原樣，連續欄位標準化)
        
        Args:
            meta_df: metadata DataFrame
            stats: 統計值字典
        
        Returns:
            標準化後的 DataFrame
        """
        meta_normalized = meta_df.copy()
        
        for col in self.meta_cols:
            if col in self.binary_cols:
                # 二元欄位: 不標準化，直接轉為 float
                meta_normalized[col] = meta_df[col].astype(float)
            else:
                # 連續欄位: 標準化
                if col not in stats:
                    raise ValueError(f"❌ 統計值中缺少欄位 {col}")
                
                mean = stats[col]['mean']
                std = stats[col]['std']
                meta_normalized[col] = (meta_df[col] - mean) / (std + 1e-10)
        
        return meta_normalized
    
    def create_metadata_dict(self, meta_df: pd.DataFrame) -> Dict[str, torch.Tensor]:
        """
        創建 metadata 字典（圖片名稱 -> tensor）
        
        Args:
            meta_df: 標準化後的 metadata DataFrame
        
        Returns:
            字典 {image_name: tensor}
        """
        meta_dict = {}
        for _, row in meta_df.iterrows():
            tensor = torch.tensor(
                [row[col] for col in self.meta_cols],
                dtype=torch.float32
            )
            meta_dict[row['image_name']] = tensor
        
        return meta_dict
    
    def save_stats(self, stats: Dict[str, Dict[str, float]], save_path: str):
        """儲存統計值到 JSON"""
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        print(f"✓ 統計值已儲存至: {save_path}")
    
    def load_stats(self, load_path: str) -> Dict[str, Dict[str, float]]:
        """從 JSON 載入統計值"""
        with open(load_path, 'r', encoding='utf-8') as f:
            stats = json.load(f)
        
        # 驗證統計值是否包含所有連續欄位 (不檢查二元欄位)
        continuous_cols = [c for c in self.meta_cols if c not in self.binary_cols]
        missing_cols = set(continuous_cols) - set(stats.keys())
        
        if missing_cols:
            raise ValueError(
                f"❌ 統計值缺少連續欄位: {missing_cols}\n"
                f"   (二元欄位不需要統計值)"
            )
        
        print(f"✓ 統計值已載入: {load_path}")
        return stats
    
    def get_fallback_value(self, col: str, stats: Dict[str, Dict[str, float]] = None) -> float:
        """
        獲取缺失值的預設值
        
        Args:
            col: 欄位名稱
            stats: 統計值字典（可選）
        
        Returns:
            預設值
        """
        # 二元欄位的預設值
        if col in self.binary_cols:
            binary_defaults = {
                'gender': 0.0,           # 預設女性
                'has_diabetes': 0.0,     # 預設無糖尿病
                'diabetes': 0.0,
                '有無糖尿病': 0.0,
            }
            return binary_defaults.get(col, 0.0)
        
        # 連續欄位: 優先使用統計值的 mean
        if stats and col in stats:
            return stats[col]['mean']
        
        # 連續欄位的預設回退值
        default_values = {
            'age': 50.0,
            'Length_px': 200.0,
            'Entropy': 0.5,
            'Contrast_Ratio': 1.0,
            'texture_chaos': 0.5,
            '內部紋理混亂度': 0.5,
        }
        
        # 如果找不到預設值，嘗試智能判斷
        if col not in default_values:
            col_lower = col.lower()
            # 布林類型欄位（有無、是否等）預設為 0
            if any(keyword in col_lower for keyword in ['has_', 'is_', '有無', '是否']):
                return 0.0
            # 其他連續型數值預設為 0.5
            return 0.5
        
        return default_values.get(col, 0.0)
    
    def normalize_single_value(self, col: str, value: float, 
                              stats: Dict[str, Dict[str, float]]) -> float:
        """
        標準化單一數值 (二元欄位不標準化)
        
        Args:
            col: 欄位名稱
            value: 原始值
            stats: 統計值字典
        
        Returns:
            標準化後的值
        """
        # 二元欄位: 不標準化
        if col in self.binary_cols:
            return float(value)
        
        # 連續欄位: 標準化
        if col not in stats:
            raise ValueError(
                f"❌ 統計值中缺少欄位 {col}\n"
                f"   這可能是因為模型訓練時未記錄該欄位的統計值"
            )
        
        mean = stats[col]['mean']
        std = stats[col]['std']
        return (value - mean) / (std + 1e-10)
    
    def prepare_inference_metadata(self, stats: Dict[str, Dict[str, float]], 
                                   **kwargs) -> torch.Tensor:
        """
        準備推論用的 metadata tensor
        
        Args:
            stats: 統計值字典
            **kwargs: 欄位名稱與值的對應（如 age=50, gender=1）
        
        Returns:
            標準化後的 tensor [meta_dim]
        """
        values = []
        
        for col in self.meta_cols:
            # 獲取原始值（如果沒提供則用預設值）
            raw_value = kwargs.get(col, self.get_fallback_value(col, stats))
            
            # 二元欄位: 不標準化
            if col in self.binary_cols:
                normalized_value = float(raw_value)
            else:
                # 連續欄位: 標準化
                try:
                    normalized_value = self.normalize_single_value(col, raw_value, stats)
                except ValueError as e:
                    # 如果統計值中沒有該欄位，使用原始值並發出警告
                    print(f"⚠️  警告: {e}")
                    print(f"   使用未標準化的值: {raw_value}")
                    normalized_value = float(raw_value)
            
            values.append(normalized_value)
        
        return torch.tensor(values, dtype=torch.float32)