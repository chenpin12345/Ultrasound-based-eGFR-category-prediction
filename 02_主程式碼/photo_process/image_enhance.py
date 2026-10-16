import cv2
import numpy as np
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, Label, Button, Frame, messagebox, Scale, ttk
from PIL import Image, ImageTk
from threading import Thread
import time
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pywt

SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.jfif')
MAX_PREVIEW_SIZE = (800, 800)

def srad_denoise_optimized(img, num_iter=200, delta_t=0.05, decay_factor=1.0):
    """優化版 SRAD - 使用向量化運算加速"""
    I = img.astype(np.float32).copy()
    eps = 1e-13
    t = 0.0

    # 預先計算常數
    h, w = I.shape
    
    # 計算初始 q0
    I_pad = np.pad(I, ((1, 1), (1, 1)), mode='reflect')
    north = I_pad[:-2, 1:-1] - I
    south = I_pad[2:, 1:-1] - I
    east = I_pad[1:-1, 2:] - I
    west = I_pad[1:-1, :-2] - I

    grad_sq = (north**2 + south**2 + east**2 + west**2) * 0.25
    lap = (north + south + east + west) * 0.25
    num = 0.5 * grad_sq - (lap**2) * 0.0625
    den = (1.0 + 0.25 * lap)**2
    q0 = np.sqrt(np.maximum(num / (den + eps), 0))
    q0[np.isnan(q0)] = 0.0

    # 迭代擴散 - 減少重複計算
    for iteration in range(num_iter):
        I_pad = np.pad(I, ((1, 1), (1, 1)), mode='reflect')
        north = I_pad[:-2, 1:-1] - I
        south = I_pad[2:, 1:-1] - I
        east = I_pad[1:-1, 2:] - I
        west = I_pad[1:-1, :-2] - I

        grad_sq = (north**2 + south**2 + east**2 + west**2) * 0.25
        lap = (north + south + east + west) * 0.25
        num = 0.5 * grad_sq - (lap**2) * 0.0625
        den = (1.0 + 0.25 * lap)**2
        q = np.sqrt(np.maximum(num / (den + eps), 0))
        q[np.isnan(q)] = 0.0

        q_decay = q0 * np.exp(-decay_factor * t)
        temp = (q**2 - q_decay**2) / (q_decay**2 * (1 + q_decay**2) + eps)
        c = np.exp(-temp / 6.0)
        c = np.clip(c, 0, 1)

        div = c * (north + south + east + west) * 0.25
        I = np.clip(I + delta_t * div, 0, 1)
        t += delta_t

    return I

def wavelet_denoise(img, wavelet='db4', level=3, threshold_multiplier=1.0):
    """小波去噪
    
    Args:
        img: 輸入圖片 (0-1 範圍的 float32)
        wavelet: 小波類型 ('db4', 'sym4', 'coif2', 'bior3.3')
        level: 分解層數
        threshold_multiplier: 閾值倍數，控制去噪強度
    """
    # 執行小波分解
    coeffs = pywt.wavedec2(img, wavelet, level=level)
    
    # 估計雜訊標準差 (使用最高頻係數)
    sigma = np.median(np.abs(coeffs[-1][2])) / 0.6745
    
    # 計算閾值
    threshold = sigma * threshold_multiplier * np.sqrt(2 * np.log(img.size))
    
    # 對細節係數進行軟閾值處理
    new_coeffs = [coeffs[0]]  # 保留近似係數
    for detail_coeffs in coeffs[1:]:
        new_detail = []
        for coeff in detail_coeffs:
            # 軟閾值
            new_coeff = pywt.threshold(coeff, threshold, mode='soft')
            new_detail.append(new_coeff)
        new_coeffs.append(tuple(new_detail))
    
    # 重建圖片
    denoised = pywt.waverec2(new_coeffs, wavelet)
    
    # 確保尺寸一致並裁剪
    if denoised.shape != img.shape:
        denoised = denoised[:img.shape[0], :img.shape[1]]
    
    return np.clip(denoised, 0, 1)

def calculate_comprehensive_metrics(original, processed):
    """計算全面的影像品質指標"""
    metrics = {}
    
    # 基本統計
    metrics['mean_orig'] = np.mean(original)
    metrics['mean_proc'] = np.mean(processed)
    metrics['std_orig'] = np.std(original)
    metrics['std_proc'] = np.std(processed)
    
    # PSNR
    mse = np.mean((original.astype(float) - processed.astype(float)) ** 2)
    if mse == 0:
        metrics['psnr'] = float('inf')
    else:
        metrics['psnr'] = 20 * np.log10(255.0 / np.sqrt(mse))
    
    # SNR (Signal-to-Noise Ratio)
    signal = np.mean(processed.astype(float) ** 2)
    if mse == 0:
        metrics['snr'] = float('inf')
    else:
        metrics['snr'] = 10 * np.log10(signal / mse)
    
    # 對比度 (標準差)
    contrast_orig = np.std(original)
    contrast_proc = np.std(processed)
    metrics['contrast_orig'] = contrast_orig
    metrics['contrast_proc'] = contrast_proc
    metrics['contrast_improvement'] = ((contrast_proc - contrast_orig) / contrast_orig) * 100
    
    # 銳利度 (Laplacian 變異數)
    sharpness_orig = cv2.Laplacian(original, cv2.CV_64F).var()
    sharpness_proc = cv2.Laplacian(processed, cv2.CV_64F).var()
    metrics['sharpness_orig'] = sharpness_orig
    metrics['sharpness_proc'] = sharpness_proc
    metrics['sharpness_ratio'] = sharpness_proc / sharpness_orig if sharpness_orig > 0 else 1.0
    
    # 邊緣強度 (Sobel)
    sobelx_orig = cv2.Sobel(original, cv2.CV_64F, 1, 0, ksize=3)
    sobely_orig = cv2.Sobel(original, cv2.CV_64F, 0, 1, ksize=3)
    edge_orig = np.sqrt(sobelx_orig**2 + sobely_orig**2)
    
    sobelx_proc = cv2.Sobel(processed, cv2.CV_64F, 1, 0, ksize=3)
    sobely_proc = cv2.Sobel(processed, cv2.CV_64F, 0, 1, ksize=3)
    edge_proc = np.sqrt(sobelx_proc**2 + sobely_proc**2)
    
    metrics['edge_strength_orig'] = np.mean(edge_orig)
    metrics['edge_strength_proc'] = np.mean(edge_proc)
    metrics['edge_enhancement'] = ((metrics['edge_strength_proc'] - metrics['edge_strength_orig']) / 
                                   metrics['edge_strength_orig']) * 100
    
    # 動態範圍
    metrics['dynamic_range_orig'] = np.max(original) - np.min(original)
    metrics['dynamic_range_proc'] = np.max(processed) - np.min(processed)
    
    # 熵 (影像資訊量)
    hist_orig, _ = np.histogram(original, bins=256, range=(0, 256))
    hist_proc, _ = np.histogram(processed, bins=256, range=(0, 256))
    
    hist_orig = hist_orig / hist_orig.sum()
    hist_proc = hist_proc / hist_proc.sum()
    
    entropy_orig = -np.sum(hist_orig[hist_orig > 0] * np.log2(hist_orig[hist_orig > 0]))
    entropy_proc = -np.sum(hist_proc[hist_proc > 0] * np.log2(hist_proc[hist_proc > 0]))
    
    metrics['entropy_orig'] = entropy_orig
    metrics['entropy_proc'] = entropy_proc
    metrics['entropy_improvement'] = ((entropy_proc - entropy_orig) / entropy_orig) * 100
    
    return metrics

def calculate_metrics(original, processed):
    """計算影像品質指標 - 舊版相容"""
    metrics = calculate_comprehensive_metrics(original, processed)
    return {
        'psnr': metrics['psnr'],
        'snr': metrics['snr'],
        'contrast_improvement': metrics['contrast_improvement'],
        'sharpness_orig': metrics['sharpness_orig'],
        'sharpness_proc': metrics['sharpness_proc'],
        'sharpness_ratio': metrics['sharpness_ratio']
    }

def enhance_image(image_path, params, return_metrics=False):
    """對單張圖片進行去噪與增強"""
    try:
        start_time = time.time()
        
        img_bytes = Path(image_path).read_bytes()
        img_array = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("圖片讀取失敗")

        original_img = img.copy()
        img = img.astype(np.float32) / 255.0

        # 去噪處理
        denoise_time = 0
        denoise_method = params.get('denoise_method', 'srad')  # 'srad', 'wavelet', 'both', 'none'
        
        if denoise_method == 'srad' and params.get('use_srad', True):
            denoise_start = time.time()
            img = srad_denoise_optimized(img, params['num_iter'], params['delta_t'], params['decay_factor'])
            denoise_time = time.time() - denoise_start
            
        elif denoise_method == 'wavelet' and params.get('use_wavelet', False):
            denoise_start = time.time()
            img = wavelet_denoise(img, 
                                 wavelet=params.get('wavelet_type', 'db4'),
                                 level=params.get('wavelet_level', 3),
                                 threshold_multiplier=params.get('wavelet_threshold', 1.0))
            denoise_time = time.time() - denoise_start
            
        elif denoise_method == 'both':
            # 先小波後SRAD
            denoise_start = time.time()
            if params.get('use_wavelet', False):
                img = wavelet_denoise(img, 
                                     wavelet=params.get('wavelet_type', 'db4'),
                                     level=params.get('wavelet_level', 3),
                                     threshold_multiplier=params.get('wavelet_threshold', 1.0))
            if params.get('use_srad', True):
                img = srad_denoise_optimized(img, params['num_iter'], params['delta_t'], params['decay_factor'])
            denoise_time = time.time() - denoise_start
        
        img_u8 = (img * 255).astype(np.uint8)

        # CLAHE 對比度增強 - 使用自適應策略
        clahe = cv2.createCLAHE(clipLimit=params['clip_limit'], tileGridSize=(8, 8))
        enhanced = clahe.apply(img_u8)

        # Unsharp Masking 銳化 - 調整權重避免過度銳化
        gauss = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=1.5)
        sharpen_weight = 1.0 + (params['sharpen_amount'] * 0.5)  # 降低銳化強度
        enhanced = cv2.addWeighted(enhanced, sharpen_weight, gauss, -params['sharpen_amount'], 0)
        enhanced = np.clip(enhanced, 0, 255).astype(np.uint8)

        # 第二次 CLAHE (更輕微) - 僅在需要時使用
        if params.get('use_second_clahe', True):
            clahe2 = cv2.createCLAHE(clipLimit=1.1, tileGridSize=(8, 8))
            enhanced = clahe2.apply(enhanced)

        # Gamma 調整
        if params['gamma'] != 1.0:
            inv_gamma = 1.0 / params['gamma']
            lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
            enhanced = cv2.LUT(enhanced, lut)

        total_time = time.time() - start_time
        
        if return_metrics:
            metrics = calculate_metrics(original_img, enhanced)
            metrics['denoise_time'] = denoise_time
            metrics['total_time'] = total_time
            return enhanced, metrics
        
        return enhanced

    except Exception as e:
        print(f"處理 {image_path} 發生錯誤: {e}")
        return None

def process_folder(folder_path, progress_callback, params=None, skip_png=True):
    """批次處理資料夾 - 兼容主程式調用"""
    folder = Path(folder_path)
    
    # 如果沒有提供參數，使用溫和優化的預設值
    if params is None:
        params = {
            'num_iter': 60,
            'delta_t': 0.04,
            'decay_factor': 1.5,
            'use_srad': True,
            'use_wavelet': False,   # ← 用來開關小波
            'clip_limit': 1.5,
            'sharpen_amount': 0.2,
            'gamma': 0.98,
            'use_second_clahe': True,
            'wavelet_type': 'db4',
            'wavelet_level': 3,
            'wavelet_threshold': 1.0
        }
    
    image_files = [
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
        and not any('移出圖片' in p.parts for p in f.parents)
    ]
    
    if skip_png:
        image_files = [f for f in image_files if f.suffix.lower() != '.png']

    total = len(image_files)
    if total == 0:
        return (0, 0)

    success_count = failure_count = 0
    all_metrics = []
    total_time = 0

    for idx, img_path in enumerate(image_files, 1):
        try:
            result = enhance_image(img_path, params, return_metrics=True)
            if result is not None:
                enhanced, metrics = result
                all_metrics.append(metrics)
                total_time += metrics['total_time']
                
                is_success, buffer = cv2.imencode('.jpg', enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if is_success:
                    img_path.write_bytes(buffer.tobytes())
                    success_count += 1
                    print(f"✓ [{idx}/{total}] {img_path.name} - {metrics['total_time']:.2f}s | PSNR: {metrics['psnr']:.1f}dB")
                else:
                    failure_count += 1
            else:
                failure_count += 1
        except Exception as e:
            print(f"✗ [{idx}/{total}] 錯誤 {img_path}: {e}")
            failure_count += 1

        if progress_callback:
            progress_callback()

    # 如果有收集指標，在控制台輸出統計
    if all_metrics:
        avg_psnr = np.mean([m['psnr'] for m in all_metrics if m['psnr'] != float('inf')])
        avg_snr = np.mean([m['snr'] for m in all_metrics if m['snr'] != float('inf')])
        avg_contrast = np.mean([m['contrast_improvement'] for m in all_metrics])
        avg_sharpness = np.mean([m['sharpness_ratio'] for m in all_metrics])
        avg_time = total_time / len(all_metrics)
        
        print(f"\n{'='*60}")
        print(f"批次處理統計 (溫和優化參數):")
        print(f"總時間: {total_time:.1f}秒 | 平均每張: {avg_time:.2f}秒")
        print(f"平均 PSNR: {avg_psnr:.2f} dB | 平均 SNR: {avg_snr:.2f} dB")
        print(f"平均對比度提升: {avg_contrast:.1f}% | 平均銳利度提升: {avg_sharpness:.2f}x")
        print(f"{'='*60}\n")
    
    return (success_count, failure_count)


class AnalysisWindow:
    """量化分析視窗"""
    def __init__(self, parent, original_img, enhanced_img, metrics, params):
        self.window = tk.Toplevel(parent)
        self.window.title("量化結果分析對比")
        self.window.geometry("1400x900")
        
        self.original_img = original_img
        self.enhanced_img = enhanced_img
        self.metrics = metrics
        self.params = params
        
        self._create_ui()
    
    def _create_ui(self):
        """建立分析介面"""
        # 主容器
        main_frame = Frame(self.window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 上方：圖片對比區
        image_frame = Frame(main_frame)
        image_frame.pack(fill="x", pady=(0, 10))
        
        # 原圖
        orig_frame = Frame(image_frame, relief="solid", borderwidth=2)
        orig_frame.pack(side="left", padx=5)
        Label(orig_frame, text="原圖", font=("Arial", 12, "bold")).pack()
        
        orig_canvas = Label(orig_frame, width=400, height=400)
        orig_canvas.pack(padx=5, pady=5)
        
        pil_orig = Image.fromarray(self.original_img)
        pil_orig.thumbnail((400, 400), Image.Resampling.LANCZOS)
        tk_orig = ImageTk.PhotoImage(pil_orig)
        orig_canvas.config(image=tk_orig)
        orig_canvas.image = tk_orig
        
        # 增強後
        enh_frame = Frame(image_frame, relief="solid", borderwidth=2)
        enh_frame.pack(side="left", padx=5)
        Label(enh_frame, text="增強後", font=("Arial", 12, "bold")).pack()
        
        enh_canvas = Label(enh_frame, width=400, height=400)
        enh_canvas.pack(padx=5, pady=5)
        
        pil_enh = Image.fromarray(self.enhanced_img)
        pil_enh.thumbnail((400, 400), Image.Resampling.LANCZOS)
        tk_enh = ImageTk.PhotoImage(pil_enh)
        enh_canvas.config(image=tk_enh)
        enh_canvas.image = tk_enh
        
        # 差異圖
        diff_frame = Frame(image_frame, relief="solid", borderwidth=2)
        diff_frame.pack(side="left", padx=5)
        Label(diff_frame, text="差異圖 (放大5倍)", font=("Arial", 12, "bold")).pack()
        
        diff_canvas = Label(diff_frame, width=400, height=400)
        diff_canvas.pack(padx=5, pady=5)
        
        diff = cv2.absdiff(self.original_img, self.enhanced_img)
        diff_enhanced = np.clip(diff * 5, 0, 255).astype(np.uint8)
        pil_diff = Image.fromarray(diff_enhanced)
        pil_diff.thumbnail((400, 400), Image.Resampling.LANCZOS)
        tk_diff = ImageTk.PhotoImage(pil_diff)
        diff_canvas.config(image=tk_diff)
        diff_canvas.image = tk_diff
        
        # 下方：量化指標與圖表
        bottom_frame = Frame(main_frame)
        bottom_frame.pack(fill="both", expand=True)
        
        # 左側：量化指標
        metrics_frame = Frame(bottom_frame, relief="solid", borderwidth=2)
        metrics_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        Label(metrics_frame, text="📊 量化指標對比", 
              font=("Arial", 14, "bold")).pack(pady=10)
        
        metrics_text = tk.Text(metrics_frame, font=("Courier", 10), 
                              wrap="word", height=15)
        metrics_text.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 填充量化指標
        self._fill_metrics(metrics_text)
        metrics_text.config(state="disabled")
        
        # 右側：圖表
        chart_frame = Frame(bottom_frame, relief="solid", borderwidth=2)
        chart_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        
        Label(chart_frame, text="📈 直方圖對比", 
              font=("Arial", 14, "bold")).pack(pady=10)
        
        self._create_histogram(chart_frame)
        
        # 底部按鈕
        btn_frame = Frame(self.window)
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="匯出報告", command=self._export_report,
               bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
               width=15).pack(side="left", padx=5)
        
        Button(btn_frame, text="關閉", command=self.window.destroy,
               bg="#f44336", fg="white", font=("Arial", 10, "bold"),
               width=15).pack(side="left", padx=5)
    
    def _fill_metrics(self, text_widget):
        """填充量化指標"""
        m = self.metrics
        
        # 顯示去噪方法
        method_name = {
            'srad': 'SRAD',
            'wavelet': '小波 (Wavelet)',
            'both': 'SRAD + 小波',
            'none': '無去噪'
        }.get(self.params.get('denoise_method', 'srad'), '未知')
        
        content = f"""
╔══════════════════════════════════════════════════════════╗
║                    處理參數設定                          ║
╚══════════════════════════════════════════════════════════╝

  去噪方法:          {method_name}
"""
        
        if self.params.get('denoise_method') in ['srad', 'both']:
            content += f"""  SRAD 迭代次數:     {self.params['num_iter']}
  SRAD delta_t:      {self.params['delta_t']}
  SRAD decay:        {self.params['decay_factor']}
"""
        
        if self.params.get('denoise_method') in ['wavelet', 'both']:
            content += f"""  小波類型:          {self.params.get('wavelet_type', 'db4')}
  小波分解層數:      {self.params.get('wavelet_level', 3)}
  小波閾值:          {self.params.get('wavelet_threshold', 1.0)}
"""
        
        content += f"""  對比度增強:        {self.params['clip_limit']}
  銳化強度:          {self.params['sharpen_amount']}
  Gamma:             {self.params['gamma']}

╔══════════════════════════════════════════════════════════╗
║                    量化指標對比                          ║
╚══════════════════════════════════════════════════════════╝

【基本統計】
  平均灰階值:        {m['mean_orig']:.2f} → {m['mean_proc']:.2f}
  標準差:            {m['std_orig']:.2f} → {m['std_proc']:.2f}
  動態範圍:          {m['dynamic_range_orig']:.0f} → {m['dynamic_range_proc']:.0f}

【品質指標】
  PSNR:              {m['psnr']:.2f} dB
  SNR:               {m['snr']:.2f} dB
  影像熵:            {m['entropy_orig']:.2f} → {m['entropy_proc']:.2f}
  熵提升:            {m['entropy_improvement']:+.2f}%

【對比度與銳利度】
  對比度:            {m['contrast_orig']:.2f} → {m['contrast_proc']:.2f}
  對比度提升:        {m['contrast_improvement']:+.2f}%
  
  銳利度:            {m['sharpness_orig']:.2f} → {m['sharpness_proc']:.2f}
  銳利度比:          {m['sharpness_ratio']:.2f}x

【邊緣增強】
  邊緣強度:          {m['edge_strength_orig']:.2f} → {m['edge_strength_proc']:.2f}
  邊緣增強:          {m['edge_enhancement']:+.2f}%

【處理時間】
  總處理時間:        {m.get('total_time', 0):.2f} 秒
  去噪時間:          {m.get('denoise_time', 0):.2f} 秒

╔══════════════════════════════════════════════════════════╗
║                    綜合評估                              ║
╚══════════════════════════════════════════════════════════╝
"""
        
        # 評估結果
        score = 0
        evaluation = []
        
        if m['psnr'] > 25:
            score += 20
            evaluation.append("✓ PSNR 優秀 (>25dB)")
        elif m['psnr'] > 20:
            score += 15
            evaluation.append("○ PSNR 良好 (>20dB)")
        else:
            evaluation.append("✗ PSNR 需改善 (<20dB)")
        
        if m['contrast_improvement'] > 10:
            score += 25
            evaluation.append("✓ 對比度顯著提升")
        elif m['contrast_improvement'] > 0:
            score += 15
            evaluation.append("○ 對比度適度提升")
        else:
            evaluation.append("✗ 對比度未提升")
        
        if m['sharpness_ratio'] > 1.2:
            score += 25
            evaluation.append("✓ 銳利度明顯改善")
        elif m['sharpness_ratio'] > 1.0:
            score += 15
            evaluation.append("○ 銳利度適度改善")
        else:
            evaluation.append("✗ 銳利度降低")
        
        if m['edge_enhancement'] > 10:
            score += 20
            evaluation.append("✓ 邊緣增強效果佳")
        elif m['edge_enhancement'] > 0:
            score += 10
            evaluation.append("○ 邊緣適度增強")
        else:
            evaluation.append("✗ 邊緣未增強")
        
        if m['entropy_improvement'] > 5:
            score += 10
            evaluation.append("✓ 影像資訊量提升")
        
        content += f"  總分: {score}/100\n\n"
        content += "\n".join(f"  {item}" for item in evaluation)
        
        if score >= 80:
            content += "\n\n  【結論】處理效果優秀！"
        elif score >= 60:
            content += "\n\n  【結論】處理效果良好"
        else:
            content += "\n\n  【結論】建議調整參數"
        
        text_widget.insert("1.0", content)
    
    def _create_histogram(self, parent):
        """建立直方圖"""
        fig = Figure(figsize=(6, 4), dpi=100)
        ax = fig.add_subplot(111)
        
        # 計算直方圖
        hist_orig = cv2.calcHist([self.original_img], [0], None, [256], [0, 256])
        hist_enh = cv2.calcHist([self.enhanced_img], [0], None, [256], [0, 256])
        
        # 正規化
        hist_orig = hist_orig.flatten() / hist_orig.sum()
        hist_enh = hist_enh.flatten() / hist_enh.sum()
        
        # 繪製
        ax.plot(hist_orig, color='blue', alpha=0.6, linewidth=1.5, label='原圖')
        ax.plot(hist_enh, color='red', alpha=0.6, linewidth=1.5, label='增強後')
        
        ax.set_xlabel('灰階值', fontsize=10)
        ax.set_ylabel('頻率', fontsize=10)
        ax.set_title('灰階分布對比', fontsize=12, fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        ax.set_xlim([0, 255])
        
        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
    
    def _export_report(self):
        """匯出分析報告"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("=" * 60 + "\n")
                    f.write("超音波影像處理 - 量化分析報告\n")
                    f.write("=" * 60 + "\n\n")
                    
                    m = self.metrics
                    
                    f.write("【處理參數】\n")
                    f.write(f"去噪方法: {self.params.get('denoise_method', 'srad')}\n")
                    if self.params.get('denoise_method') in ['srad', 'both']:
                        f.write(f"SRAD 迭代次數: {self.params['num_iter']}\n")
                        f.write(f"SRAD delta_t: {self.params['delta_t']}\n")
                        f.write(f"SRAD decay: {self.params['decay_factor']}\n")
                    if self.params.get('denoise_method') in ['wavelet', 'both']:
                        f.write(f"小波類型: {self.params.get('wavelet_type', 'db4')}\n")
                        f.write(f"小波層數: {self.params.get('wavelet_level', 3)}\n")
                        f.write(f"小波閾值: {self.params.get('wavelet_threshold', 1.0)}\n")
                    f.write(f"對比度增強: {self.params['clip_limit']}\n")
                    f.write(f"銳化強度: {self.params['sharpen_amount']}\n")
                    f.write(f"Gamma: {self.params['gamma']}\n\n")
                    
                    f.write("【量化指標】\n")
                    f.write(f"PSNR: {m['psnr']:.2f} dB\n")
                    f.write(f"SNR: {m['snr']:.2f} dB\n")
                    f.write(f"對比度提升: {m['contrast_improvement']:+.2f}%\n")
                    f.write(f"銳利度比: {m['sharpness_ratio']:.2f}x\n")
                    f.write(f"邊緣增強: {m['edge_enhancement']:+.2f}%\n")
                    f.write(f"熵提升: {m['entropy_improvement']:+.2f}%\n\n")
                    
                    f.write("【處理時間】\n")
                    f.write(f"總時間: {m.get('total_time', 0):.2f} 秒\n")
                    f.write(f"去噪時間: {m.get('denoise_time', 0):.2f} 秒\n")
                
                messagebox.showinfo("成功", f"報告已匯出至:\n{file_path}")
            except Exception as e:
                messagebox.showerror("錯誤", f"匯出失敗: {e}")


class ImageEnhanceApp:
    def __init__(self, root, mode_params=None):
        self.root = root
        self.root.title("超音波影像去噪與增強 (優化版)")
        self.root.geometry("2000x1050")

        self.image_path = None
        self.enhanced_img = None
        self.original_img_u8 = None
        self.processing = False
        self.cache = {'path': None, 'original': None, 'srad': None, 'srad_key': None}
        self.current_metrics = None

        self.external_params = mode_params
        self._create_ui()

    def _create_ui(self):
        """建立使用者介面"""
        # 參數區
        param_frame = Frame(self.root, relief="raised", borderwidth=2)
        param_frame.pack(side="left", fill="y", padx=10, pady=10, ipadx=10)

        Label(param_frame, text="參數調整", font=("Arial", 14, "bold")).pack(pady=10)

        # 去噪方法選擇
        denoise_frame = Frame(param_frame, relief="groove", borderwidth=2)
        denoise_frame.pack(pady=10, padx=10, fill="x")
        
        Label(denoise_frame, text="去噪方法", font=("Arial", 11, "bold")).pack(pady=5)
        
        self.denoise_method = tk.StringVar(value="srad")
        methods = [
            ("SRAD", "srad"),
            ("小波 (Wavelet)", "wavelet"),
            ("兩者結合", "both"),
            ("不去噪", "none")
        ]
        
        for text, value in methods:
            rb = tk.Radiobutton(denoise_frame, text=text, variable=self.denoise_method, 
                               value=value, command=self.on_denoise_method_change)
            rb.pack(anchor="w", padx=10)

        # SRAD 參數框
        self.srad_frame = Frame(param_frame, relief="groove", borderwidth=2)
        self.srad_frame.pack(pady=10, padx=10, fill="x")
        
        Label(self.srad_frame, text="SRAD 參數", font=("Arial", 10, "bold")).pack(pady=5)
        self._add_scale(self.srad_frame, "迭代次數:", "num_iter", 50, 500, 60, 1)
        self._add_scale(self.srad_frame, "delta_t:", "delta_t", 0.01, 0.2, 0.04, 0.01)
        self._add_scale(self.srad_frame, "decayFactor:", "decay_factor", 0.1, 5.0, 1.5, 0.1)

        # 小波參數框
        self.wavelet_frame = Frame(param_frame, relief="groove", borderwidth=2)
        self.wavelet_frame.pack(pady=10, padx=10, fill="x")
        
        Label(self.wavelet_frame, text="小波參數", font=("Arial", 10, "bold")).pack(pady=5)
        
        # 小波類型選擇
        Label(self.wavelet_frame, text="小波類型:").pack(anchor="w", padx=10, pady=(5, 0))
        self.wavelet_type = tk.StringVar(value="db4")
        wavelet_combo = ttk.Combobox(self.wavelet_frame, textvariable=self.wavelet_type, 
                                     values=['db4', 'db8', 'sym4', 'sym8', 'coif2', 'bior3.3'],
                                     state='readonly', width=15)
        wavelet_combo.pack(padx=10, pady=(0, 5))
        
        self._add_scale(self.wavelet_frame, "分解層數:", "wavelet_level", 1, 5, 3, 1)
        self._add_scale(self.wavelet_frame, "閾值強度:", "wavelet_threshold", 0.5, 2.0, 1.0, 0.1)
        
        # 初始狀態：顯示SRAD，隱藏小波
        self.wavelet_frame.pack_forget()

        # 增強參數框
        enhance_frame = Frame(param_frame, relief="groove", borderwidth=2)
        enhance_frame.pack(pady=10, padx=10, fill="x")
        
        Label(enhance_frame, text="增強參數", font=("Arial", 10, "bold")).pack(pady=5)
        self._add_scale(enhance_frame, "對比度增強:", "clip_limit", 1.0, 5.0, 1.5, 0.1)
        self._add_scale(enhance_frame, "銳化強度:", "sharpen", 0.0, 1.5, 0.2, 0.05)
        self._add_scale(enhance_frame, "Gamma 調整:", "gamma", 0.5, 1.5, 0.98, 0.01)

        # 控制按鈕
        Button(param_frame, text="🔄 更新預覽", command=self.update_preview,
               bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(pady=20, padx=10, fill="x")
        Button(param_frame, text="重置預設值", command=self.reset_params).pack(padx=10, fill="x")

        # PNG 處理選項
        self.skip_png_var = tk.BooleanVar(value=True)
        tk.Checkbutton(param_frame, text="批次處理時跳過 PNG", 
                      variable=self.skip_png_var).pack(anchor="w", padx=10, pady=(20, 0))

        # 主顯示區
        main_frame = Frame(self.root)
        main_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # 圖片顯示區
        img_frame = Frame(main_frame)
        img_frame.pack(pady=10)

        self.original_canvas = self._create_image_panel(img_frame, "原圖", "#e3f2fd", "尚未選擇圖片")
        self.enhanced_canvas = self._create_image_panel(img_frame, "增強後", "#e8f5e9", "尚未處理")

        # 品質指標顯示
        metrics_frame = Frame(main_frame, relief="solid", borderwidth=1, bg="#fff3e0")
        metrics_frame.pack(pady=10, fill="x", padx=20)
        
        Label(metrics_frame, text="📊 影像品質指標", font=("Arial", 12, "bold"), 
              bg="#fff3e0").pack(pady=5)
        
        self.metrics_label = Label(metrics_frame, text="尚未處理", font=("Arial", 10),
                                   bg="#fff3e0", justify="left")
        self.metrics_label.pack(pady=5, padx=10)

        # 控制按鈕
        control_frame = Frame(main_frame)
        control_frame.pack(pady=20)

        Button(control_frame, text="📁 選擇圖片", command=self.select_image,
               bg="#2196F3", fg="white", font=("Arial", 11, "bold"), width=15).pack(side="left", padx=5)
        
        self.save_btn = Button(control_frame, text="💾 覆蓋原圖", command=self.save_image,
                               state="disabled", bg="#FF9800", fg="white", 
                               font=("Arial", 11, "bold"), width=15)
        self.save_btn.pack(side="left", padx=5)

        # 新增：量化分析按鈕
        self.analysis_btn = Button(control_frame, text="📊 量化分析", command=self.show_analysis,
                                   state="disabled", bg="#9C27B0", fg="white", 
                                   font=("Arial", 11, "bold"), width=15)
        self.analysis_btn.pack(side="left", padx=5)

        Button(control_frame, text="📂 批次處理資料夾", command=self.batch_process,
               bg="#607D8B", fg="white", font=("Arial", 11, "bold"), width=18).pack(side="left", padx=5)

        # 進度條
        progress_frame = Frame(main_frame)
        progress_frame.pack(pady=10, fill="x")
        
        self.progress_label = Label(progress_frame, text="", font=("Arial", 10))
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(progress_frame, length=600, mode='determinate')
        self.progress_bar.pack(pady=5)

    def _add_scale(self, parent, label, name, from_, to, default, resolution):
        """新增滑桿控制項"""
        Label(parent, text=label).pack(anchor="w", padx=10, pady=(5, 0))
        scale = Scale(parent, from_=from_, to=to, resolution=resolution, 
                     orient="horizontal", length=200)
        scale.set(default)
        scale.pack(padx=10, pady=(0, 5))
        setattr(self, f"{name}_scale", scale)

    def on_denoise_method_change(self):
        method = self.denoise_method.get()
        if method in ['wavelet', 'both']:
            self.wavelet_frame.pack(pady=10, padx=10, fill="x")
        else:
            self.wavelet_frame.pack_forget()

        if method in ['srad', 'both']:
            self.srad_frame.pack(pady=10, padx=10, fill="x")
        else:
            self.srad_frame.pack_forget()

        # 如果已經載入圖片，自動更新預覽
        if self.image_path:
            self.update_preview()

    def _create_image_panel(self, parent, title, bg_color, placeholder_text):
        """建立圖片顯示面板"""
        frame = Frame(parent, relief="solid", borderwidth=2, bg=bg_color)
        frame.pack(side="left", padx=15)
        Label(frame, text=title, font=("Arial", 14, "bold"), bg=bg_color, pady=5).pack(fill="x")
        
        container = Frame(frame, width=800, height=800, bg="#f5f5f5")
        container.pack(padx=5, pady=5)
        container.pack_propagate(False)
        
        canvas = Label(container, text=placeholder_text, bg="#f5f5f5", font=("Arial", 12))
        canvas.place(relx=0.5, rely=0.5, anchor="center")
        return canvas

    def toggle_srad(self):
        """切換 SRAD 開關狀態 - 已廢棄，保留以維持相容性"""
        pass

    def get_params(self):
        """取得當前參數"""
        params = {
            'denoise_method': self.denoise_method.get(),
            'num_iter': int(self.num_iter_scale.get()),
            'delta_t': float(self.delta_t_scale.get()),
            'decay_factor': float(self.decay_factor_scale.get()),
            'wavelet_type': self.wavelet_type.get(),
            'wavelet_level': int(self.wavelet_level_scale.get()),
            'wavelet_threshold': float(self.wavelet_threshold_scale.get()),
            'clip_limit': float(self.clip_limit_scale.get()),
            'sharpen_amount': float(self.sharpen_scale.get()),
            'gamma': float(self.gamma_scale.get()),
            'use_second_clahe': True
        }
        
        # 根據去噪方法設置標誌
        method = params['denoise_method']
        params['use_srad'] = method in ['srad', 'both']
        params['use_wavelet'] = method in ['wavelet', 'both']
        
        return params

    def reset_params(self):
        """重置參數為優化值"""
        self.denoise_method.set("srad")
        self.num_iter_scale.set(60)
        self.delta_t_scale.set(0.04)
        self.decay_factor_scale.set(1.5)
        self.wavelet_type.set("db4")
        self.wavelet_level_scale.set(3)
        self.wavelet_threshold_scale.set(1.0)
        self.clip_limit_scale.set(1.5)
        self.sharpen_scale.set(0.2)
        self.gamma_scale.set(0.98)
        self.on_denoise_method_change()  # 更新UI顯示
        messagebox.showinfo("完成", "參數已重置為溫和優化值")

    def select_image(self):
        """選擇並載入圖片"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.webp *.jfif")]
        )
        if not file_path:
            return

        self.image_path = Path(file_path)

        if self.cache['path'] != str(self.image_path):
            self.cache = {'path': str(self.image_path), 'original': None, 
                         'srad': None, 'srad_key': None}
            
            try:
                img_bytes = self.image_path.read_bytes()
                img_array = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    self.cache['original'] = img.astype(np.float32) / 255.0
                    self.original_img_u8 = img.copy()
            except Exception as e:
                print(f"快取載入失敗: {e}")

        try:
            img_bytes = self.image_path.read_bytes()
            img_array = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            pil_img.thumbnail(MAX_PREVIEW_SIZE, Image.Resampling.LANCZOS)
            self.tk_original = ImageTk.PhotoImage(pil_img)
            self.original_canvas.config(image=self.tk_original, text="")
        except Exception as e:
            print(f"顯示原圖失敗: {e}")

        self.update_preview()

    def update_preview(self):
        """更新預覽"""
        if not self.image_path:
            messagebox.showwarning("警告", "請先選擇圖片！")
            return

        params = self.get_params()
        self.progress_label.config(text="處理中...")
        self.root.update()

        try:
            start_time = time.time()
            
            img = self.cache.get('original')
            if img is None:
                raise ValueError("快取圖片不存在")

            original_u8 = (img * 255).astype(np.uint8)

            # 去噪處理
            denoise_time = 0
            method = params['denoise_method']
            
            if method == 'srad' and params['use_srad']:
                denoise_start = time.time()
                self.cache['srad'] = srad_denoise_optimized(img, params['num_iter'], 
                                                 params['delta_t'], params['decay_factor'])
                denoise_time = time.time() - denoise_start
                img = self.cache['srad']
                print(f"SRAD 處理時間: {denoise_time:.2f}秒")
                
            elif method == 'wavelet' and params['use_wavelet']:
                denoise_start = time.time()
                img = wavelet_denoise(img, 
                                     wavelet=params['wavelet_type'],
                                     level=params['wavelet_level'],
                                     threshold_multiplier=params['wavelet_threshold'])
                denoise_time = time.time() - denoise_start
                print(f"小波 處理時間: {denoise_time:.2f}秒")
                
            elif method == 'both':
                denoise_start = time.time()
                # 先小波後SRAD
                img = wavelet_denoise(img, 
                                     wavelet=params['wavelet_type'],
                                     level=params['wavelet_level'],
                                     threshold_multiplier=params['wavelet_threshold'])
                img = srad_denoise_optimized(img, params['num_iter'], 
                                            params['delta_t'], params['decay_factor'])
                denoise_time = time.time() - denoise_start
                print(f"混合去噪時間: {denoise_time:.2f}秒")

            img_u8 = (img * 255).astype(np.uint8)

            # 後續增強
            clahe = cv2.createCLAHE(clipLimit=params['clip_limit'], tileGridSize=(8, 8))
            enhanced = clahe.apply(img_u8)

            # Unsharp Masking 銳化 - 使用溫和的權重
            gauss = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=1.5)
            sharpen_weight = 1.0 + (params['sharpen_amount'] * 0.5)
            enhanced = cv2.addWeighted(enhanced, sharpen_weight, gauss, -params['sharpen_amount'], 0)
            enhanced = np.clip(enhanced, 0, 255).astype(np.uint8)

            # 第二次 CLAHE (更輕微)
            clahe2 = cv2.createCLAHE(clipLimit=1.1, tileGridSize=(8, 8))
            enhanced = clahe2.apply(enhanced)

            if params['gamma'] != 1.0:
                inv_gamma = 1.0 / params['gamma']
                lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
                enhanced = cv2.LUT(enhanced, lut)

            total_time = time.time() - start_time

            # 計算全面的品質指標
            self.current_metrics = calculate_comprehensive_metrics(original_u8, enhanced)
            self.current_metrics['total_time'] = total_time
            self.current_metrics['denoise_time'] = denoise_time
            self.current_metrics['denoise_method'] = method

            # 顯示結果
            pil_enhanced = Image.fromarray(enhanced)
            pil_enhanced.thumbnail(MAX_PREVIEW_SIZE, Image.Resampling.LANCZOS)
            self.enhanced_img = enhanced
            self.tk_enhanced = ImageTk.PhotoImage(pil_enhanced)
            self.enhanced_canvas.config(image=self.tk_enhanced, text="")
            self.save_btn.config(state="normal")
            self.analysis_btn.config(state="normal")
            
            # 更新指標顯示
            method_name = {
                'srad': 'SRAD',
                'wavelet': '小波',
                'both': 'SRAD+小波',
                'none': '無去噪'
            }.get(method, method)
            
            metrics_text = (
                f"去噪方法: {method_name} | 處理時間: {total_time:.2f}秒 (去噪: {denoise_time:.2f}秒)\n"
                f"PSNR: {self.current_metrics['psnr']:.2f} dB | "
                f"SNR: {self.current_metrics['snr']:.2f} dB\n"
                f"對比度提升: {self.current_metrics['contrast_improvement']:.1f}% | "
                f"銳利度比: {self.current_metrics['sharpness_ratio']:.2f}x\n"
                f"邊緣增強: {self.current_metrics['edge_enhancement']:.1f}% | "
                f"熵提升: {self.current_metrics['entropy_improvement']:.1f}%"
            )
            self.metrics_label.config(text=metrics_text)
            
            self.progress_label.config(text=f"✓ 處理完成 ({method_name}) - {total_time:.2f}秒")

        except Exception as e:
            messagebox.showerror("錯誤", f"處理失敗: {e}")
            self.save_btn.config(state="disabled")
            self.analysis_btn.config(state="disabled")
            self.progress_label.config(text="✗ 處理失敗")

    def show_analysis(self):
        """顯示量化分析視窗"""
        if self.enhanced_img is None or self.original_img_u8 is None:
            messagebox.showwarning("警告", "請先處理圖片！")
            return
        
        params = self.get_params()
        AnalysisWindow(self.root, self.original_img_u8, self.enhanced_img, 
                      self.current_metrics, params)

    def save_image(self):
        """儲存處理後的圖片"""
        if self.image_path and self.enhanced_img is not None:
            try:
                is_success, buffer = cv2.imencode('.jpg', self.enhanced_img, 
                                                 [cv2.IMWRITE_JPEG_QUALITY, 95])
                if is_success:
                    self.image_path.write_bytes(buffer.tobytes())
                    messagebox.showinfo("完成", f"已覆蓋原圖:\n{self.image_path}")
                else:
                    messagebox.showerror("錯誤", "圖片編碼失敗！")
            except Exception as e:
                messagebox.showerror("錯誤", f"儲存失敗: {e}")

    def batch_process(self):
        """批次處理資料夾"""
        if self.processing:
            messagebox.showwarning("警告", "正在處理中,請稍候...")
            return

        folder_path = filedialog.askdirectory(title="選擇要批次處理的資料夾")
        if not folder_path:
            return

        result = messagebox.askyesno(
            "確認批次處理",
            f"將處理資料夾內所有圖片並直接覆蓋原檔\n\n資料夾: {folder_path}\n\n是否繼續？",
            icon='warning'
        )
        if not result:
            return

        self.processing = True
        params = self.get_params()
        skip_png = self.skip_png_var.get()

        def process_thread():
            folder = Path(folder_path)
            image_files = [
                f for f in folder.rglob("*")
                if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
                and not any('移出圖片' in p.parts for p in f.parents)
            ]
            
            if skip_png:
                image_files = [f for f in image_files if f.suffix.lower() != '.png']

            total = len(image_files)
            if total == 0:
                self.processing = False
                messagebox.showinfo("提示", "資料夾中沒有找到圖片")
                return

            success_count = 0
            failure_count = 0
            
            for idx, img_path in enumerate(image_files, 1):
                try:
                    enhanced = enhance_image(img_path, params, return_metrics=False)
                    if enhanced is not None:
                        is_success, buffer = cv2.imencode('.jpg', enhanced, 
                                                         [cv2.IMWRITE_JPEG_QUALITY, 95])
                        if is_success:
                            img_path.write_bytes(buffer.tobytes())
                            success_count += 1
                        else:
                            failure_count += 1
                    else:
                        failure_count += 1
                except Exception as e:
                    print(f"處理 {img_path} 失敗: {e}")
                    failure_count += 1
                
                # 更新進度
                progress = (idx / total) * 100
                self.progress_bar['value'] = progress
                self.progress_label.config(text=f"處理中: {idx}/{total} ({progress:.1f}%)")
                self.root.update()
            
            self.processing = False
            self.progress_label.config(text=f"✓ 完成! 成功: {success_count} 張, 失敗: {failure_count} 張")
            messagebox.showinfo("批次處理完成", 
                              f"成功處理: {success_count} 張\n失敗: {failure_count} 張")

        Thread(target=process_thread, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageEnhanceApp(root)
    root.mainloop()