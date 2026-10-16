"""
plot_dataset_distribution.py - 生成符合SCI論文標準的資料集分布圖
根據 trainer.py 的路徑配置自動統計五類 eGFR 分類的樣本數量
"""
import os
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from pathlib import Path

# 設定 matplotlib 參數以符合 SCI 論文標準
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.size'] = 14  # 增大基礎字體
plt.rcParams['font.family'] = 'Arial'
plt.rcParams['axes.labelsize'] = 16  # 增大座標軸標籤
plt.rcParams['axes.titlesize'] = 18  # 增大標題
plt.rcParams['xtick.labelsize'] = 14  # 增大 x 軸刻度
plt.rcParams['ytick.labelsize'] = 14  # 增大 y 軸刻度
plt.rcParams['legend.fontsize'] = 13  # 增大圖例
plt.rcParams['lines.linewidth'] = 1.5
plt.rcParams['axes.linewidth'] = 1.0
plt.rcParams['grid.linewidth'] = 0.5


class DatasetDistributionPlotter:
    """資料集分布繪圖器"""
    
    def __init__(self):
        """初始化路徑配置（與 trainer.py 保持一致）"""
        # 獲取當前檔案所在目錄
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.base_dir)
        
        # 資料集路徑（與 Config 一致）
        self.dataset_path = os.path.join(
            self.project_root, "IMG", "IMG_train", "method2"
        )
        
        # 輸出目錄
        self.output_dir = os.path.join(self.project_root, "figures")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 五類分類定義（從高到低排序，符合醫學慣例）
        self.classes = [
            "eGFR 90-",      # ≥90
            "eGFR 60-89",    # 60-89
            "eGFR 30-59",    # 30-59
            "eGFR 15-29",    # 15-29
            "eGFR -15"       # <15
        ]
        
        # 類別標籤（用於圖表顯示）
        self.class_labels = [
            "≥90",
            "60-89",
            "30-59",
            "15-29",
            "<15"
        ]
        
        # 顏色方案（黑白灰階，符合 SCI 論文印刷要求）
        # 從淺灰到深黑的漸變，確保黑白印刷時仍有清晰對比
        self.colors = [
            '#F5F5F5',  # 極淺灰 (≥90, 正常)
            '#BDBDBD',  # 淺灰 (60-89, 輕微異常)
            '#757575',  # 中灰 (30-59, 中度異常)
            '#424242',  # 深灰 (15-29, 重度異常)
            '#212121'   # 極深灰/黑 (<15, 極重度異常)
        ]
    
    def count_samples(self):
        """統計各類別的樣本數量（支援 train/val/test 子資料夾結構）"""
        # 子資料夾
        subsets = ['train', 'val', 'test']
        
        # 初始化計數器
        subset_counts = {subset: [] for subset in subsets}
        total_counts = []
        
        print("=" * 80)
        print("資料集樣本統計")
        print("=" * 80)
        print(f"資料集路徑: {self.dataset_path}")
        print()
        
        # 統計每個子集的每個類別
        for class_name in self.classes:
            class_total = 0
            print(f"\n{class_name}:")
            print("-" * 60)
            
            for subset in subsets:
                # 路徑: method2/train/eGFR 90-
                class_path = os.path.join(self.dataset_path, subset, class_name)
                
                if os.path.exists(class_path):
                    # 統計圖片文件數量（支援常見格式）
                    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
                    image_files = [
                        f for f in os.listdir(class_path)
                        if os.path.splitext(f.lower())[1] in image_extensions
                    ]
                    count = len(image_files)
                    subset_counts[subset].append(count)
                    class_total += count
                    print(f"  {subset:5s}: {count:4d} 張圖片")
                else:
                    subset_counts[subset].append(0)
                    print(f"  {subset:5s}: 路徑不存在")
            
            total_counts.append(class_total)
            print(f"  {'小計':5s}: {class_total:4d} 張圖片")
        
        # 計算總計
        train_total = sum(subset_counts['train'])
        val_total = sum(subset_counts['val'])
        test_total = sum(subset_counts['test'])
        grand_total = sum(total_counts)
        
        print()
        print("=" * 80)
        print("總計統計:")
        print("-" * 80)
        print(f"  Train: {train_total:4d} 張圖片")
        print(f"  Val:   {val_total:4d} 張圖片")
        print(f"  Test:  {test_total:4d} 張圖片")
        print("-" * 80)
        print(f"  總計:  {grand_total:4d} 張圖片")
        print("=" * 80)
        print()
        
        return total_counts, grand_total, subset_counts
    
    def plot_distribution(self, counts, total, subset_counts=None, 
                         save_formats=['png']):
        """
        繪製分布長條圖（總計版本）- 黑白灰階版本
        
        Args:
            counts: 各類別的總樣本數量
            total: 總樣本數
            subset_counts: 各子集的詳細計數（可選）
            save_formats: 儲存格式列表，預設只有 png
        """
        # 創建圖表
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # 繪製長條圖
        x_pos = np.arange(len(self.class_labels))
        bars = ax.bar(x_pos, counts, color=self.colors, 
                      edgecolor='black', linewidth=1.5, alpha=1.0)
        
        # 在長條上方標註數量和百分比
        for i, (bar, count) in enumerate(zip(bars, counts)):
            height = bar.get_height()
            percentage = (count / total * 100) if total > 0 else 0
            
            # 數量標籤（在頂部）
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{count}',
                   ha='center', va='bottom', fontsize=14, fontweight='bold')
            
            # 百分比標籤（根據長條顏色深淺決定文字顏色）
            # 前兩個長條較淺，用黑色文字；後三個較深，用白色文字
            text_color = 'black' if i < 2 else 'white'
            ax.text(bar.get_x() + bar.get_width()/2., height * 0.5,
                   f'({percentage:.1f}%)',
                   ha='center', va='center', fontsize=12, 
                   color=text_color, fontweight='bold')
        
        # 設定座標軸
        ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', 
                     fontsize=16, fontweight='bold')
        ax.set_ylabel('Number of Samples', 
                     fontsize=16, fontweight='bold')
        ax.set_title('Distribution of Dataset by eGFR Categories',
                    fontsize=18, fontweight='bold', pad=20)
        
        # 設定 x 軸刻度
        ax.set_xticks(x_pos)
        ax.set_xticklabels(self.class_labels, fontsize=14)
        
        # 設定 y 軸範圍（增加上方空間以顯示標籤）
        max_count = max(counts) if counts else 0
        ax.set_ylim(0, max_count * 1.15)
        
        # 添加網格線（僅 y 軸）
        ax.yaxis.grid(True, linestyle='--', alpha=0.3, zorder=0, color='gray')
        ax.set_axisbelow(True)
        
        # 添加總計資訊
        fig.text(0.99, 0.01, f'Total samples: {total}',
                ha='right', va='bottom', fontsize=12,
                style='italic', color='black')
        
        # 調整布局
        plt.tight_layout()
        
        # 儲存圖表（只有PNG）
        saved_files = []
        for fmt in save_formats:
            output_path = os.path.join(
                self.output_dir, 
                f'dataset_distribution_5class.{fmt}'
            )
            
            plt.savefig(output_path, format=fmt, bbox_inches='tight',
                       transparent=False, dpi=300)
            
            saved_files.append(output_path)
            print(f"✓ 已儲存: {output_path}")
        
        plt.close()
        
        return saved_files
    
    def plot_distribution_with_stages(self, counts, total, 
                                     save_formats=['png']):
        """
        繪製帶有 CKD 分期標註的分布長條圖 - 黑白灰階版本
        
        Args:
            counts: 各類別的樣本數量
            total: 總樣本數
            save_formats: 儲存格式列表，預設只有 png
        """
        # CKD 分期對應
        ckd_stages = ['G1', 'G2', 'G3b', 'G4', 'G5']
        
        # 創建圖表
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # 繪製長條圖
        x_pos = np.arange(len(self.class_labels))
        bars = ax.bar(x_pos, counts, color=self.colors, 
                      edgecolor='black', linewidth=1.5, alpha=1.0)
        
        # 在長條上方標註數量和百分比
        for i, (bar, count) in enumerate(zip(bars, counts)):
            height = bar.get_height()
            percentage = (count / total * 100) if total > 0 else 0
            
            # 數量標籤
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{count}',
                   ha='center', va='bottom', fontsize=14, fontweight='bold')
            
            # 百分比標籤（根據長條顏色深淺決定文字顏色）
            text_color = 'black' if i < 2 else 'white'
            ax.text(bar.get_x() + bar.get_width()/2., height * 0.5,
                   f'({percentage:.1f}%)',
                   ha='center', va='center', fontsize=12, 
                   color=text_color, fontweight='bold')
            
            # CKD 分期標籤（在底部）
            ax.text(bar.get_x() + bar.get_width()/2., -max(counts) * 0.05,
                   f'CKD {ckd_stages[i]}',
                   ha='center', va='top', fontsize=11, 
                   style='italic', color='black')
        
        # 設定座標軸
        ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', 
                     fontsize=16, fontweight='bold', labelpad=25)
        ax.set_ylabel('Number of Samples', 
                     fontsize=16, fontweight='bold')
        ax.set_title('Distribution of Dataset by eGFR Categories and CKD Stages',
                    fontsize=18, fontweight='bold', pad=20)
        
        # 設定 x 軸刻度
        ax.set_xticks(x_pos)
        ax.set_xticklabels(self.class_labels, fontsize=14)
        
        # 設定 y 軸範圍
        max_count = max(counts) if counts else 0
        ax.set_ylim(-max_count * 0.08, max_count * 1.15)
        
        # 添加網格線
        ax.yaxis.grid(True, linestyle='--', alpha=0.3, zorder=0, color='gray')
        ax.set_axisbelow(True)
        
        # 添加總計資訊
        fig.text(0.99, 0.01, f'Total samples: {total}',
                ha='right', va='bottom', fontsize=12,
                style='italic', color='black')
        
        # 調整布局
        plt.tight_layout()
        
        # 儲存圖表（只有PNG）
        saved_files = []
        for fmt in save_formats:
            output_path = os.path.join(
                self.output_dir, 
                f'dataset_distribution_5class_with_stages.{fmt}'
            )
            
            plt.savefig(output_path, format=fmt, bbox_inches='tight',
                       transparent=False, dpi=300)
            
            saved_files.append(output_path)
            print(f"✓ 已儲存: {output_path}")
        
        plt.close()
        
        return saved_files
    
    def plot_stacked_distribution(self, subset_counts, 
                                  save_formats=['png']):
        """
        繪製堆疊長條圖顯示 train/val/test 分布 - 黑白灰階版本
        使用不同灰階和填充圖案以區分 train/val/test
        
        Args:
            subset_counts: 字典，包含 'train', 'val', 'test' 的各類別計數
            save_formats: 儲存格式列表，預設只有 png
        """
        # 創建圖表
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # 準備數據
        train_counts = np.array(subset_counts['train'])
        val_counts = np.array(subset_counts['val'])
        test_counts = np.array(subset_counts['test'])
        
        x_pos = np.arange(len(self.class_labels))
        width = 0.6
        
        # 黑白灰階配色（使用不同灰度）
        train_color = '#404040'   # 深灰（Train）
        val_color = '#808080'     # 中灰（Val）
        test_color = '#C0C0C0'    # 淺灰（Test）
        
        # 繪製堆疊長條（使用不同的填充圖案以增加辨識度）
        bars1 = ax.bar(x_pos, train_counts, width, 
                      label='Train', color=train_color, 
                      edgecolor='black', linewidth=1.2, alpha=1.0,
                      hatch='///')  # 斜線圖案
        
        bars2 = ax.bar(x_pos, val_counts, width, 
                      bottom=train_counts,
                      label='Validation', color=val_color, 
                      edgecolor='black', linewidth=1.2, alpha=1.0,
                      hatch='xxx')  # 交叉圖案
        
        bars3 = ax.bar(x_pos, test_counts, width, 
                      bottom=train_counts + val_counts,
                      label='Test', color=test_color, 
                      edgecolor='black', linewidth=1.2, alpha=1.0,
                      hatch='...')  # 點狀圖案
        
        # 計算總數
        total_counts = train_counts + val_counts + test_counts
        grand_total = sum(total_counts)
        
        # 在每個堆疊上標註數量
        for i in range(len(self.class_labels)):
            # Train 數量
            if train_counts[i] > 0:
                ax.text(x_pos[i], train_counts[i] / 2, 
                       f'{train_counts[i]}',
                       ha='center', va='center', fontsize=11,
                       color='white', fontweight='bold')
            
            # Val 數量
            if val_counts[i] > 0:
                ax.text(x_pos[i], train_counts[i] + val_counts[i] / 2,
                       f'{val_counts[i]}',
                       ha='center', va='center', fontsize=11,
                       color='white', fontweight='bold')
            
            # Test 數量
            if test_counts[i] > 0:
                ax.text(x_pos[i], train_counts[i] + val_counts[i] + test_counts[i] / 2,
                       f'{test_counts[i]}',
                       ha='center', va='center', fontsize=11,
                       color='black', fontweight='bold')
            
            # 總數標籤（在頂部）
            ax.text(x_pos[i], total_counts[i],
                   f'{total_counts[i]}',
                   ha='center', va='bottom', fontsize=14,
                   fontweight='bold', color='black')
            
            # 百分比標籤
            percentage = (total_counts[i] / grand_total * 100) if grand_total > 0 else 0
            ax.text(x_pos[i], total_counts[i] + max(total_counts) * 0.05,
                   f'({percentage:.1f}%)',
                   ha='center', va='bottom', fontsize=11,
                   style='italic', color='black')
        
        # 設定座標軸
        ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', 
                     fontsize=16, fontweight='bold')
        ax.set_ylabel('Number of Samples', 
                     fontsize=16, fontweight='bold')
        ax.set_title('Dataset Distribution by eGFR Categories (Train/Val/Test Split)',
                    fontsize=18, fontweight='bold', pad=20)
        
        # 設定 x 軸刻度
        ax.set_xticks(x_pos)
        ax.set_xticklabels(self.class_labels, fontsize=14)
        
        # 設定 y 軸範圍
        max_count = max(total_counts) if len(total_counts) > 0 else 0
        ax.set_ylim(0, max_count * 1.2)
        
        # 添加圖例
        ax.legend(loc='upper right', fontsize=13, framealpha=0.95,
                 edgecolor='black', fancybox=False)
        
        # 添加網格線
        ax.yaxis.grid(True, linestyle='--', alpha=0.3, zorder=0, color='gray')
        ax.set_axisbelow(True)
        
        # 添加統計資訊
        train_total = sum(train_counts)
        val_total = sum(val_counts)
        test_total = sum(test_counts)
        
        info_text = (f'Train: {train_total} | '
                    f'Val: {val_total} | '
                    f'Test: {test_total} | '
                    f'Total: {grand_total}')
        
        fig.text(0.99, 0.01, info_text,
                ha='right', va='bottom', fontsize=12,
                style='italic', color='black')
        
        # 調整布局
        plt.tight_layout()
        
        # 儲存圖表（只有PNG）
        saved_files = []
        for fmt in save_formats:
            output_path = os.path.join(
                self.output_dir, 
                f'dataset_distribution_5class_stacked.{fmt}'
            )
            
            plt.savefig(output_path, format=fmt, bbox_inches='tight',
                       transparent=False, dpi=300)
            
            saved_files.append(output_path)
            print(f"✓ 已儲存: {output_path}")
        
        plt.close()
        
        return saved_files
    
    def generate_summary_table(self, counts, total, subset_counts=None):
        """生成統計摘要表格"""
        print("\n" + "=" * 90)
        print("資料集統計摘要表")
        print("=" * 90)
        
        if subset_counts:
            # 詳細版本（包含 train/val/test）
            print(f"{'eGFR Category':<20} {'CKD Stage':<12} {'Train':<8} {'Val':<8} {'Test':<8} {'Total':<8} {'%':<8}")
            print("-" * 90)
            
            ckd_stages = ['G1', 'G2', 'G3b', 'G4', 'G5']
            
            for i, label in enumerate(self.class_labels):
                full_label = f"eGFR {label}"
                train_n = subset_counts['train'][i]
                val_n = subset_counts['val'][i]
                test_n = subset_counts['test'][i]
                total_n = counts[i]
                percentage = (total_n / total * 100) if total > 0 else 0
                
                print(f"{full_label:<20} {ckd_stages[i]:<12} "
                      f"{train_n:<8} {val_n:<8} {test_n:<8} "
                      f"{total_n:<8} {percentage:>6.2f}%")
            
            print("-" * 90)
            
            # 總計行
            train_total = sum(subset_counts['train'])
            val_total = sum(subset_counts['val'])
            test_total = sum(subset_counts['test'])
            
            print(f"{'Total':<20} {'':<12} "
                  f"{train_total:<8} {val_total:<8} {test_total:<8} "
                  f"{total:<8} {'100.00%':>8}")
            
        else:
            # 簡化版本（僅總計）
            print(f"{'eGFR Category':<20} {'CKD Stage':<12} {'Samples':<10} {'Percentage':<12}")
            print("-" * 70)
            
            ckd_stages = ['G1', 'G2', 'G3b', 'G4', 'G5']
            
            for i, (label, count) in enumerate(zip(self.class_labels, counts)):
                percentage = (count / total * 100) if total > 0 else 0
                full_label = f"eGFR {label}"
                print(f"{full_label:<20} {ckd_stages[i]:<12} {count:<10} {percentage:>6.2f}%")
            
            print("-" * 70)
            print(f"{'Total':<20} {'':<12} {total:<10} {'100.00%':>12}")
        
        print("=" * 90)
        print()


def main():
    """主程式"""
    print("\n" + "="*60)
    print("資料集分布圖生成程式")
    print("符合 SCI 論文發表標準（黑白印刷版本）")
    print("="*60 + "\n")
    
    # 創建繪圖器
    plotter = DatasetDistributionPlotter()
    
    # 統計樣本數量
    counts, total, subset_counts = plotter.count_samples()
    
    if total == 0:
        print("⚠️  警告: 未找到任何樣本，請檢查資料集路徑是否正確")
        print(f"   預期路徑: {plotter.dataset_path}")
        print(f"   預期結構: method2/train/{'{類別名稱}'}")
        print(f"              method2/val/{'{類別名稱}'}")
        print(f"              method2/test/{'{類別名稱}'}")
        return
    
    # 生成統計表格
    plotter.generate_summary_table(counts, total, subset_counts)
    
    # 繪製基本分布圖（總計）
    print("\n正在生成總體分布圖...")
    saved_files = plotter.plot_distribution(counts, total, subset_counts)
    
    # 繪製帶有 CKD 分期的分布圖
    print("\n正在生成帶有 CKD 分期標註的分布圖...")
    saved_files_stages = plotter.plot_distribution_with_stages(counts, total)
    
    # 繪製堆疊分布圖（顯示 train/val/test）
    print("\n正在生成 Train/Val/Test 堆疊分布圖...")
    saved_files_stacked = plotter.plot_stacked_distribution(subset_counts)
    
    print("\n" + "="*60)
    print("✓ 所有圖表已成功生成！")
    print("="*60)
    print("\n生成的圖表:")
    print("  1. dataset_distribution_5class.png")
    print("     → 總體分布（所有樣本）")
    print("  2. dataset_distribution_5class_with_stages.png")
    print("     → 總體分布 + CKD 分期標註")
    print("  3. dataset_distribution_5class_stacked.png")
    print("     → Train/Val/Test 堆疊分布（含圖案填充）")
    print("\n黑白印刷優化:")
    print("  • 灰階漸變: 從淺灰(正常)到深黑(嚴重)")
    print("  • 圖案填充: Train(斜線), Val(交叉), Test(點狀)")
    print("  • 高對比度: 確保黑白列印時清晰可讀")
    print("  • 粗邊框: 1.5pt 黑色邊框增強辨識度")
    print("\nSCI 論文標準:")
    print("  • 解析度: 300 DPI（符合 SCI 期刊要求）")
    print("  • 格式: PNG（適用於黑白印刷）")
    print("  • 字體: Arial（國際期刊標準）")
    print("  • 標註: 完整的數量、百分比和 CKD 分期資訊")
    print(f"\n所有圖表已儲存至: {plotter.output_dir}")
    print()


if __name__ == "__main__":
    main()