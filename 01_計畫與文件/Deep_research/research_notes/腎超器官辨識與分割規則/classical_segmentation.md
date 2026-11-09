# 2D B-mode 超音波中腎臟／腎竇／肝脾的傳統（非深度學習）分割方法

> 範圍說明：本筆記只涵蓋傳統影像處理／規則式方法與其可用特徵。共約 20 次搜尋與擷取；多篇原文 PDF 已實際擷取全文（Zheng 2018 graph cuts、Mendoza 2013 MICCAI、Yin 2020、Yang 2012 NLTV+DRLSE、Cha 2021 HRI）。部分經典論文（Xie 2005、Martín-Fernández 2005、Noble & Boukerroui 2006、Torres 2018 review、Ardon 2015）只取得書目／摘要，未取得數據，已在 Gaps 中標出。
> 標記：【舊】= 2015 年以前的經典論文；【半自動】= 需要人工初始化。

## 1. 腎臟分割：主動輪廓、level set、graph cuts、ASM/SSM、紋理、斑點統計、區域成長、watershed

### Takeaway
在 2D 腎超上，表現最好的傳統方法幾乎都是**半自動**（需人工點 6–10 點、ROI 或 UPJ），並結合「強度＋紋理（Gabor）＋形狀先驗」；有人工初始化時 Dice 可達 0.87–0.96，但都在單一中心、小樣本（34–85 位受試者）、多為兒科資料上。沒有人工初始化時，傳統方法普遍不穩，這正是後續研究轉向深度學習的主因。

### Cited Findings
**Graph cuts＋Gabor 紋理（Zheng et al., Med Phys 2018；arXiv 2017）**
- 方法：先算多尺度、多方向 Gabor 濾波，每個像素取「反應較大的方向」融合成紋理特徵圖（相當於沿邊緣濾波）；只在**靠近腎臟邊界的窄帶（narrow band）**上建圖，用**局部區域**相似度計算邊權以處理弱邊界，再迭代更新直到收斂 — [Zheng et al., arXiv 1706.03372](https://arxiv.org/pdf/1706.03372)
- 資料：費城兒童醫院（CHOP）85 位兒童的雙側 2D 腎超；20 位用來調參，65 位用來測試。內文未記載機型 — [Zheng et al.](https://arxiv.org/pdf/1706.03372)
- 結果（65 位受試者、雙側腎臟）：Dice 0.9581±0.0131、Jaccard 0.9204、Mean Distance 1.72。比較方法（初始化相同）：geodesic active contour（GAC）Dice 0.9315±0.0374；localizing region-based active contour（Lankton）Dice 0.9051；AMFSM 多特徵模型 Dice 0.9046（均 p<1e-19）— [Zheng et al.](https://arxiv.org/pdf/1706.03372)
- 單用強度或單用 Gabor 都比合併差（20 位受試者的調參實驗中，單用 Gabor 的 Dice >0.943）— [Zheng et al.](https://arxiv.org/pdf/1706.03372)
- 限制：**半自動**，需人工點 6–10 點勾出初始輪廓；作者承認不同初始化可能讓結果不穩，但三組初始化的 ICC 約 0.89–0.90 — [Zheng et al.](https://arxiv.org/pdf/1706.03372)
- 作者對既有方法的評論：主動輪廓（ACM）以梯度下降最佳化，**容易卡在局部極小值**；graph cuts 可求全域最佳。斑點雜訊與低對比若直接作為輸入會降低效果 — [Zheng et al.](https://arxiv.org/pdf/1706.03372)

**ASM＋影像擷取先驗（Mendoza et al., MICCAI 2013）【舊】【半自動】**
- 改良經典 ASM：(1) 用 particle swarm optimization 自動初始化；(2) **依超音波入射角做 rotation correction**，處理「與聲束方向相切的邊緣會變淡」的問題，讓 radial intensity-derivative profile 依入射角對應，而非依解剖 landmark 對應 — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- 資料：34 例兒科水腎的 2D 矢狀切面；機型為 Philips iU22 ×1 與 GE Logiq E9 ×3；leave-one-out — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- 腎臟 Dice：經典 ASM 0.83±0.04 → 改良 ASM 0.87±0.05；兩位人工標註者之間 0.95±0.03。平均周界距離 MPD 17.3 px，人工間為 6.5 px — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- 作者指出腎臟內部結構異質，許多邊界因與周圍組織密度相近或陰影而消失 — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)

**NLTV 去噪＋DRLSE level set＋PCA 形狀空間（Yang et al., BioMed Eng OnLine 2012）【舊】**
- 流程：NLTV 去噪 → DRLSE（不需重新初始化）得到粗略二值遮罩 → 演化結束後**只做一次** PCA 形狀投影（11 個特徵向量，涵蓋 98.8% 形狀變異）把邊界平滑 — [Yang et al. 2012, PMC3585889](https://pmc.ncbi.nlm.nih.gov/articles/PMC3585889/)
- 資料：Mindray DC-7、凸陣探頭、左腎、512×512；**ROI 為人工框選**；**未報告影像或病人數** — [Yang et al. 2012](https://pmc.ncbi.nlm.nih.gov/articles/PMC3585889/)
- 結果（Table 1，未報 Dice）：DRLSE 的 SN/SP/PPV 為 0.97/0.88/0.78；加 NLTV 後 0.99/0.94/0.89；完整方法 0.96/0.95/0.91。**摘要、Table 1、Table 2 的數字彼此不一致**，作者未解釋 — [Yang et al. 2012](https://pmc.ncbi.nlm.nih.gov/articles/PMC3585889/)
- 失敗模式：病人腎形不在訓練形狀空間內時結果差；DRLSE 單獨使用會產生凹陷邊界 — [Yang et al. 2012](https://pmc.ncbi.nlm.nih.gov/articles/PMC3585889/)

**其他經典方法（只取得書目／描述）**
- Xie, Jiang, Tsui, IEEE TMI 2005【舊】：以 Gabor 濾波組做雙側卷積取紋理，用 EM 估計半平面高斯混合紋理模型，再嵌入 Leventon 參數化形狀模型；能量讓內部紋理相似度高、變異低，外部紋理變異高。在自然影像與 US 上與手動分割比較，但檢索結果中**沒有取得數值** — [Ghose et al. review, arXiv 1911.09863](https://arxiv.org/pdf/1911.09863)；[visionbib 書目](https://www.visionbib.com/bibliography/medical867kidney1.html)
- Martín-Fernández & Alberola-López, Med Image Anal 2005【舊】：貝氏方法，以 Markov field 對形變做平滑先驗；likelihood 用回波資料的**經驗分布**加梯度項；屬於 3D US 逐切片處理並含跨切片平滑項。在真實病人資料驗證並做參數敏感度分析 — [UVa LPI](https://lpi.tel.uva.es/node/236)
- Marsousi et al.：早期 2D 版本在 Morison's pouch（肝腎隱窩）影像上用 level set 加機率腎臟形狀模型（PKSM）初始化；後期轉為 3D 的 shape-to-volume 配準（IEEE JBHI 2019）— [Marsousi 描述, arXiv 1911.09863](https://arxiv.org/pdf/1911.09863)；[搜尋摘要轉述](https://arxiv.org/pdf/1611.09811)
- Yin et al. 2020 整理的既有方法類別：ACM（Yang 2012；Song 2016 改良 level set 分割腎實質面積）、atlas（Marsousi 2015）、MRF（Martín-Fernández 2005）、watershed（Tamilselvi 2012）、random forest（Sharma 2015）、ASM/SSM（Cerrolaza 2014、2016；Mendoza 2013）。作者評論「多數把問題當作邊界偵測，且**依賴人工初始化**」 — [Yin et al. 2020, arXiv 1811.04815](https://www.arxiv.org/pdf/1811.04815)
- Watershed 在含斑點的 US 上**一定會過度分割**。常見的補救流程：直方圖等化 → 7×7 中值濾波 → 多尺度形態學梯度 → reconstruction-by-erosion 去除小極小值（Bhushan 2009，屬一般性 US 方法，非腎臟專用）— [Ghose et al. review](https://arxiv.org/pdf/1911.09863)
- 相位法（Torres 等）Dice 約 0.81，精修步驟易卡在局部極小值；相位式距離正則化演化模型需要太多人工設定參數（取自搜尋摘要對系統性綜述的轉述，未讀到原文）— [搜尋結果：Liang et al. QIMS review](https://qims.amegroups.org/article/view/112984/html)

**對照：深度學習在同一族資料上的結果**
- Yin et al. 2020（CHOP）：185 張出生後第一次的矢狀切面腎超（85 張來自 50 位 CAKUT 兒童、100 張來自 50 位單側輕度水腎兒童），105 張訓練／20 張驗證／60 張測試，另有 104 張外部測試。boundary-distance regression＋像素分類端到端模型，Dice 0.9451±0.0315（只用邊界偵測網路為 0.9427）。**全自動**，不需初始化 — [Yin et al. 2020](https://www.arxiv.org/pdf/1811.04815)
- 系統性綜述：腎臟 US 分割研究共 10 篇，5 篇 2D、5 篇 3D（數量少）— [搜尋結果：Liang et al., QIMS](https://qims.amegroups.org/article/view/112984/html)

### Inferences
- 同一團隊（CHOP／U Penn Fan 實驗室）的半自動 graph cuts（Dice 0.958）與全自動 DL（Dice 0.945）數值接近。差別主要在「是否需要人工初始化」，而非邊界精度本身。若我們的 pipeline 已有 DL／MedSAM 草稿可當初始化，**narrow-band graph cuts＋Gabor 特徵**很適合當「邊界精修」步驟：用草稿取代人工點選，在邊界兩側 ±k 像素建圖。
- 已發表的數字都是**在研究者自選的清楚影像**上（Cha 2021 明確排除畫質不佳的影像）。在一般臨床影像上的表現可能更差，這是推論，沒有直接證據。
- ASM／PCA 形狀先驗對「形狀不在訓練集內」的病變腎（水腎、囊腫、萎縮）會失敗。這類規則較適合當**合理性檢查**（例如投影誤差太大就標記），而不是硬性約束。

### Gaps
- Xie 2005、Martín-Fernández 2005、Marsousi、Ardon 2015、Torres 2018 系統性綜述的實際 Dice 與資料量：只取得摘要或書目（PubMed 需 cookie），無法引用數字。
- 沒找到專門用 **Rayleigh／Nakagami 參數圖** 分割腎臟的論文與數據。Martín-Fernández 用的是「經驗分布」，不確定是否為 Rayleigh。
- 沒找到 region growing 用於 2D 腎臟、且有可信 Dice 的近十年論文。
- 幾乎所有資料都來自兒科（CHOP、Children's National）；**成人腎超**的傳統方法數據非常少。

## 2. 腎竇／內部結構分離（腎竇 vs 實質 vs 髓質錐體）

### Takeaway
已有兩種可直接仿照的作法：(a) Cha 2021 在腎臟遮罩內做**三類 GMM**，取中間亮度類當皮質，最亮類當腎竇、最暗類當髓質或陰影；(b) Mendoza 2013 用 graph cuts 結合**強度與位置先驗（靠近 UPJ／腎門）**，加上**強度偏差校正**，並以「面積大、相對低回音、靠近 UPJ」的分數挑選候選區域。髓質錐體（低回音）與擴張集尿系統（同樣低回音）容易混淆，兒童尤其明顯；傳統方法在這裡的 Dice 只有約 0.6。

### Cited Findings
- Cha et al. 2021：在 DL 腎臟遮罩內先做距離圖把分析限縮在腎臟內部，再用**三類 GMM**；中間亮度類視為皮質，排除較亮的腎竇與較暗的髓質／陰影偽影，最後用滑動視窗找**最均質的皮質區域**放 ROI — [Cha et al., Ultrasonography 2021, PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- Mendoza 2013 集尿系統（CS）分割：CS 為從 UPJ 向實質延伸的低回音區。難點包括強度偏移、陰影造成訊號流失、2D 切面失去 3D 連通性；**「幼兒的腎錐體比其他人更低回音，連有經驗的人都可能與 CS 混淆」** — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- Mendoza 的強度校正：假設腎臟內強度有一個**常數偏移**（來自使用者的深度增益設定與衰減）；以測試影像腎內 PDF 與訓練影像 PDF 的交叉相關，找出最相似的 K=10 個訓練腎臟並估計偏移，不需假設 bias field 模型 — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- Mendoza 的位置先驗：以訓練分割做 KDE，取得 CS 相對位置的機率圖。Graph cuts 產生的候選連通區以分數 S 排序，分數結合「面積大」「相對低回音程度高」「靠近 UPJ」 — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- 結果（34 例）：CS Dice 由經典 GC 的 0.32±0.22 提升到 0.62±0.32；**人工間 Dice 也只有 0.76±0.18**。水腎指數 HI 誤差 2.67±5.22 個百分點（人工間 2.31±4.54），r=0.99。ASM 每例約 45 s，GC 約 4 s — [Mendoza et al. 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- 3D 集尿系統分割（Cerrolaza 團隊系列）：主動輪廓模擬液體在腎內擴散；用 positive delta detector 偵測擴張系統周圍的腎周／腎竇脂肪，以該脂肪區內**最暗的 3×3×3 區塊**自動初始化；13 例病理個案的體積 HI 差 2.8 個百分點 — [搜尋結果彙整（Children's National 系列）](https://hsrc.himmelfarb.gwu.edu/smhs_peds_facpubs/3189)
- 深度學習對照：attention U-Net 分割腎臟與擴張腎盂腎盞，Dice 為 0.92／0.83（搜尋摘要轉述，未讀到原文）— [搜尋結果](https://link.springer.com/chapter/10.1007/978-3-319-24574-4_85)

### Inferences
- **成人正常腎**的腎竇以脂肪為主，呈**高回音**；Mendoza 處理的是兒科水腎的**低回音** CS，兩者極性相反。成人規則可設為「腎內最亮的 GMM 類＋位置在腎臟中央長軸附近＋連通到腎門側」。兒科或水腎則需另設低回音分支。
- 錐體與腎竇的分離可以利用：(1) 亮度極性，錐體偏暗、成人腎竇偏亮；(2) 位置，錐體呈三角形、排列在皮質內側，**沿著腎竇周緣分布**，而腎竇位於中央；(3) 連通性，腎竇是單一中央大區，錐體是多個分散的小區。這是根據上述文獻與解剖常識的推論，未找到直接驗證的傳統方法論文。
- 單切面 2D 的 CS／腎竇人工 Dice 只有 0.76，代表**標註本身的上限就低**，評估腎竇草稿時不宜以 0.9 為目標。

### Gaps
- 找不到專門以 k-means／Otsu 分離**成人高回音腎竇**並報告 Dice 的傳統方法論文。
- 找不到以形態學（如 top-hat、opening）分離錐體與腎竇的量化研究。

## 3. 腎臟視野中肝／脾區域辨識與 HRI 自動 ROI

### Takeaway
已發表並有驗證的自動 HRI 方法（Cha 2021）是「DL 分割＋三類 GMM＋規則」：在肝臟內取中間亮度類（排除血管壁與血管／肋骨陰影），**在與腎臟 ROI 相近的深度**、靠近右腎處放 15×15 mm ROI。肝臟分割比腎臟差（Jaccard 76.6% vs 89.4%），主因是肋骨與肺的陰影。純傳統、不靠 DL 的肝／脾辨識，沒有找到有驗證數據的論文。

### Cited Findings
- Cha 2021 資料：294 位活體肝捐贈者（2003–2016，自 790 位篩選）；Philips、GE、Siemens；組織學：95 正常、198 輕度、1 中度；DL 訓練集 2,021 張 — [Cha et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- 規則：肝與腎都只保留機率 >50% 的**最大連通物件**；肝臟同樣用三類 GMM 取中間類；肝 ROI 放在與腎 ROI **相近的深度**，以降低深度造成的亮度差；兩個 ROI 都是 15×15 mm²，HRI = 肝平均亮度／腎平均亮度 — [Cha et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- 一致性：演算法對兩位放射科醫師平均值的 ICC：肝亮度 0.919、腎亮度 0.916、HRI 0.734；**放射科醫師之間的 HRI ICC 只有 0.681／0.579**。HRI 計算無失敗案例，每張約 80 ms — [Cha et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- 限制：排除畫質不佳、視野不足、皮質疤痕或囊腫的影像；幾乎沒有中重度脂肪肝；廠商有限；沒有外部驗證 — [Cha et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- 專利（無臨床驗證，只作設計參考）：在 Morison's pouch 視圖分割肝與腎皮質，篩選有效樣本後自動放 ROI；有專利以神經網路計算信心值並建議 ROI 位置；另有專利指出**肋骨使肝與腎難以同時入鏡** — [US12026886](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12026886)；[US 2021/0177373](https://patents.justia.com/patent/20210177373)；[US12551187](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12551187)
- Marsousi 早期的 2D 研究以 Morison's pouch（肝腎隱窩）影像為對象，表示「肝臟在腎臟上方相鄰」這個先驗可用於定位 — [arXiv 1911.09863 轉述](https://arxiv.org/pdf/1911.09863)

### Inferences
- 可轉成規則：肝／脾候選區 = 腎臟遮罩**上方**（近探頭側、較淺）的大型均質區；用局部變異係數（CV = σ/μ）或 GLCM homogeneity 衡量均質度；GMM 中間類排除血管（暗）與血管壁（亮）；肝 ROI 的深度與腎 ROI 對齊。右腎視圖預期上方是肝，左腎視圖預期上方是脾（解剖推論）。
- 肝與皮質的邊界對比低，正是 HRI 的物理基礎（脂肪肝時肝變亮）。因此**不能用「亮度差」當作肝腎邊界的主要線索**，應改用腎被膜的高回音線與腎周脂肪。這是推論。

### Gaps
- 沒找到純傳統（紋理＋位置）方法辨識腎臟視圖中肝／脾、並有 Dice 的論文。
- 沒找到脾腎指數（spleen-kidney）自動 ROI 的論文。

## 4. 斑點前處理：SRAD、anisotropic diffusion、median／bilateral、NLTV、log 壓縮

### Takeaway
SRAD 類擴散濾波是公認的強基準；比較研究中 OSRAD 在邊緣保留上最好。前處理對下游分割有實際幫助，例如 NLTV 讓 DRLSE 的 PPV 由 0.78 升到 0.89。但所有平滑都會模糊**弱邊界**，而與聲束平行的邊緣本來就弱。也有觀點認為斑點本身是紋理特徵，不應全部去除。

### Cited Findings
- 心臟超音波的斑點抑制比較（IEEE TUFFC）：OSRAD 最好，兼顧抑制斑點與保留邊緣，並且讓模擬影像的平均 SNR 約加倍 — [Univ. of Galway 摘要](https://research.universityofgalway.ie/en/publications/echocardiographic-speckle-reduction-comparison/)
- 傳統擴散濾波**對迭代次數敏感**且細節保留差；加入 Tukey error norm 的版本可防止過度擴散（期刊標示可疑，見 Gaps）— [PMC3287496](https://pmc.ncbi.nlm.nih.gov/articles/PMC3287496)
- Feature-asymmetry anisotropic diffusion 對**低對比邊緣**保留較好，參數可自動計算，並以去斑點後的分割準確度驗證 — [PolyU](https://research.polyu.edu.hk/en/publications/feature-asymmetry-anisotropic-diffusion-for-speckle-reduction/)
- SRAD 加多尺度 geodesic active contour（由粗到細），在模擬與臨床 US 上提升分割準確度 — [PolyU](https://research.polyu.edu.hk/en/publications/multiscale-geodesic-active-contours-for-ultrasound-image-segmenta/)
- NLTV 以 patch 加權，平滑均質區而保留大梯度邊界；在腎超上，NLTV 讓 DRLSE 的 PPV 由 0.78 升到 0.89，Bresson 法由 0.80 升到 0.87。DRLSE 邊緣指標內建的 Gaussian 平滑會**模糊弱邊界**，但作者未量化 — [Yang et al. 2012](https://pmc.ncbi.nlm.nih.gov/articles/PMC3585889/)
- Watershed 前處理慣例是 7×7 中值濾波，加多尺度形態學梯度 — [Ghose et al. review](https://arxiv.org/pdf/1911.09863)
- 斑點有時本身就是特徵，去噪可能讓偵測變差 — [Ghose et al. review](https://arxiv.org/pdf/1911.09863)
- 早期方法多假設斑點為白色高斯雜訊；較好的作法是依影像型態，以 Rayleigh（包絡）或 Fisher-Tippett（log 壓縮後）建模 — [Sabanci Univ.](https://research.sabanciuniv.edu/12995/1/18395_GU-UltrasoundSegmentation.pdf)；BMVC 2012 指出局部 Rayleigh 模型在模擬 US 上表現良好 — [BMVA](https://bmva-archive.org.uk/bmvc/2012/BMVC/paper084/paper084.pdf)

### Inferences
- 臨床 DICOM 是**已經 log 壓縮並經廠商後處理的灰階**，因此統計模型應採 Fisher-Tippett（log-Rayleigh）或直接用非參數經驗分布，Rayleigh 不適用。這是根據上述資料的推論。
- 實務建議：分割前用 SRAD 或 bilateral（OpenCV `bilateralFilter`；scikit-image `denoise_tv_chambolle`／`denoise_nl_means`），但**紋理特徵（Gabor、GLCM）應在原圖上計算**，避免平滑掉紋理。

### Gaps
- 沒找到「濾波器 × 腎臟 Dice」的直接比較研究。
- 搜尋結果中有一篇擴散濾波論文標示為 BMC Genomics 期刊，期刊類別不尋常，可信度未查證。

## 5. 可直接寫成規則的特徵

### Takeaway
文獻支持的可規則化特徵包括：入射角相關的邊緣強度（與聲束平行的邊緣較弱）、腎內強度 PDF 偏差校正（處理增益差異）、相對深度、最大連通物件、三類 GMM 亮度分層、靠近腎門／UPJ 的位置先驗、Gabor 方向紋理、橢圓初始化；陰影可用 confidence map 偵測。

### Cited Findings
- **邊緣與入射角**：與聲束傳播方向相切的邊緣會變淡；ASM profile 應依入射角而非解剖位置對應 — [Mendoza 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- **增益正規化**：使用者的深度增益與衰減造成強度偏差；Mendoza 以 PDF 交叉相關估計常數偏移 — [Mendoza 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)。Cha 2021 則採**比值**（HRI）並讓 ROI 深度對齊，以抵消深度相關的亮度變化 — [Cha 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- **橢圓先驗**：Prevost／Ardon 的 3D CEUS 方法先以**穩健橢球偵測**定位腎臟，再以模板形變分割；作者承認雜訊、偽影與視野有限造成的部分遮蔽是挑戰 — [Ghose review](https://arxiv.org/pdf/1911.09863)；[HAL](https://hal.archives-ouvertes.fr/hal-00703134)
- **最大連通物件與機率門檻**：>50% 機率，只保留最大物件 — [Cha 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- **陰影偵測**：Karamalis 2012（MedIA）的 random walks confidence map 估計每個像素的可信度，突顯衰減與陰影區；有 MATLAB／C++ 程式碼。後續研究指出它**對探頭設定敏感** — [TUM CAMP code](https://campar.in.tum.de/Main/AthanasiosKaramalisCode.html)；[arXiv 2011.11956](https://arxiv.org/pdf/2011.11956)。一篇碩士論文以 confidence map 自動偵測陰影，與專家標註相比準確度最高 85% — [MUN thesis](https://research.library.mun.ca/13308)
- **形狀空間檢查**：PCA 11 模態涵蓋 98.8% 變異；SN／SP／PPV <0.9 時擴大形狀空間 — [Yang 2012](https://pmc.ncbi.nlm.nih.gov/articles/PMC3585889/)

### Inferences（建議的 Python 規則，皆未經文獻直接驗證）
- 陰影：從每個高亮反射點（例如肋骨，亮度在第 99 百分位以上）沿掃描線方向往深處，計算行平均亮度；若連續 >N mm 低於局部背景的某個比例，就標記為陰影帶。凸陣探頭的掃描線是**扇形放射狀**，要先轉成極座標再處理。陰影帶內的草稿邊界應降低信心，不應被當成腎臟邊界。也可直接實作 Karamalis confidence map（random walk 可用 `skimage.segmentation.random_walker` 的概念自行建圖）。
- 被膜邊緣：沿草稿輪廓法線方向取 profile，檢查外側是否有高回音線（被膜與腎周脂肪）；在聲束方向與法線平行處（上下緣）應要求較強邊緣，在左右側緣則放寬。
- 形狀：`cv2.fitEllipse` 的長短軸比，成人矢狀切面腎臟約為長橢圓形（具體範圍需以自有資料統計）；凸性（solidity）偏低時，代表可能漏掉一段或混入腎竇外的區域。
- 位置：腎臟視圖中腎臟通常位於肝／脾的深側；腎竇位於腎臟中央、朝向腎門側。

### Gaps
- 找不到「深度方向暗帶規則」的量化準確度。
- 找不到成人腎臟長短軸比、solidity 的文獻常模（需自行從標註資料統計）。

## 6. 限制：何時傳統方法失敗、何時 DL 較好

### Takeaway
傳統方法的主要失敗點包括：需要人工初始化、局部極小值、肝與皮質對比低、陰影與部分視野、病變腎形狀超出形狀先驗、跨機器的強度差。DL 在同一資料族上全自動就能達到 Dice 約 0.945，但同樣會因肋骨陰影而讓肝臟表現較差，而且跨廠商的泛化性未經驗證。

### Cited Findings
- ACM 的梯度下降易卡在局部極小值 — [Zheng 2018](https://arxiv.org/pdf/1706.03372)；多數半自動方法依賴人工初始化 — [Yin 2020](https://www.arxiv.org/pdf/1811.04815)
- 經典 ASM（平均形狀初始化）Dice 0.83；經典 GC 分割 CS 只有 0.32 — [Mendoza 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)
- 形狀先驗在未見過的腎形上失敗 — [Yang 2012](https://pmc.ncbi.nlm.nih.gov/articles/PMC3585889/)
- 陰影與部分遮蔽 — [Mendoza 2013](https://iacl.ece.jhu.edu/proceedings/miccai2013/papers/8151/81510259.pdf)；[Prevost via Ghose review](https://arxiv.org/pdf/1911.09863)
- 肝臟因肋骨與肺陰影，分割 Jaccard 只有 76.6%（DL 方法也是如此）— [Cha 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- Confidence map 對探頭設定敏感 — [arXiv 2011.11956](https://arxiv.org/pdf/2011.11956)
- 不同研究之間的資料與指標不同，不能直接比較數字（Yang 用 SN／SP／PPV，Zheng 用 Dice，Mendoza 用像素 MPD）— 見上述各來源

### Inferences
- 文獻之間的分歧：Zheng 宣稱 ACM「對雜訊、弱邊界、外觀變異穩健」，但同一段又說 ACM 易卡在局部極小值；Mendoza 則顯示經典方法（ASM／GC）不加 US 專用先驗時效果明顯差。綜合來看，**傳統方法的效果取決於 US 專用先驗（入射角、偏差校正、位置），而不是演算法家族本身**。
- 最實際的定位：傳統方法不應取代 DL／MedSAM 草稿，而應做為 (1) 邊界精修（narrow-band GC＋Gabor）、(2) 腎內分層（三類 GMM）、(3) 品質旗標（陰影帶、形狀異常、邊緣強度不足）、(4) 增益正規化。

### Gaps
- 沒有找到在**同一個成人資料集**上直接比較傳統方法與 DL 的研究。
- 跨機器（machine dependence）對傳統方法影響的量化數據沒有找到；只有 Cha 2021 與 Mendoza 2013 提到多廠商，但都沒有分廠商報告結果。
