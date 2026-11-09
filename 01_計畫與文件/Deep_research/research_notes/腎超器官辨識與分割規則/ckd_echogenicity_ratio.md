# 成人 CKD 腎臟 B-mode 超音波變化與定量皮質回音比（右腎/肝、左腎/脾）

本份筆記延續兩份前作，**不重複**其內容：
- `腎臟超音波影像判讀入門/echogenicity_grading_ckd.md`（以下稱「前作 A」）
- `腎超音波標註資料來源/automated_echogenicity_methods.md`（以下稱「前作 B」）

前作已涵蓋以下內容，本份只補充新證據、矛盾與缺口：Hricak 0–III 分級（二手來源）、Moghazi 2005、Libório 2017 摘要、Araújo 2020、HRI 基本 ROI 規則、Kuo 2019、Yonsei Mask R-CNN、Open Kidney。

本輪約 15 次搜尋與擷取。**未能取得** Hricak 1982、Lucisano 2015、Webb 2009、Marshall 2012 的全文，相關內容均標示為二手。

---

## Q1. 各 CKD 期別的皮質回音、皮質厚度、實質厚度、腎長、皮髓質分界變化（定量值 vs eGFR）

### Takeaway
各參數與 eGFR 的相關強度差異很大：
- 回音（分級）與 eGFR 的相關最強，|r| 約 0.35–0.68。
- 腎長次之，r 約 0.34–0.44。
- 皮質厚度在各研究間不一致，r 從 0.25 到 0.85 都有。

腎長在 CKD 第 2–3 期即開始改變。皮髓質分界（CMD）消失屬晚期徵象；一旦消失，皮質厚度就無法量測。

目前**沒有**跨研究一致、依 G1–G5 分期的 mm 參考值表。

### Cited Findings
- **Yaprak et al., Int Urol Nephrol 2017（摘要；前作寫為 2019，實為 2017，DOI 10.1007/s11255-016-1443-4）**
  - 族群：n=120，CKD 1–5 期，平均 63 歲，eGFR 以 CKD-EPI 計算。
  - 操作：單一放射科醫師，對臨床資料盲測。國家與機型在摘要中未載明。
  - 平均值：腎長 96.2±12.3（mm）；實質厚度 10.97±2.59 mm。
  - 與 eGFR 相關：腎長 r=0.343，實質厚度 r=0.37，**實質回音 r=−0.683**，CKD score r=−0.587。
  - 診斷表現：CKD score >4.75 判 eGFR<60，sens 81%、PPV 92%、AUC 0.829（0.74–0.92）。
  - — [Springer Medicine abstract](https://www.springermedicine.com/role-of-ultrasonographic-chronic-kidney-disease-score-in-the-ass/21758436)
- **Yaprak score 的計分表（二手，西班牙 Nefrología 回顧之 Table 2）**
  - 腎長：<80 mm =5；80–89 =4；90–99 =3；100–109 =2；110–119 =1；>120 =0。
  - 實質厚度：<8 mm =4；9–10 =3；11–12 =2；13–14 =1；>15 =0。
  - 回音：Grade 0–IV 對應 0–4 分（**5 級**，非 Hricak 的 4 級）。
  - 回顧稱 score >4.75 的 specificity 為 65%，並稱糖尿病者相關較強。
  - — [Revista Nefrología review](https://revistanefrologia.com/en-correlation-renal-ultrasound-parameters-with-articulo-S2013251426000404)
- **Lucisano et al. 2015（二手）**
  - 對象：eGFR 30–90。
  - 結論：腎長需以身高、體重校正；最大變化出現在 CKD 2–3 期。
  - 校正腎長的表現 sens 82.4%、spec 75.8%，優於單獨的實質或皮質厚度。
  - 回顧引用的公式不完整（缺截距）。
  - — [Revista Nefrología review](https://revistanefrologia.com/en-correlation-renal-ultrasound-parameters-with-articulo-S2013251426000404)
- **Siddappa et al., J Clin Imaging Sci 2013（印度 Bangalore；稍舊）**
  - 族群與排除：n=60（>30 歲），**排除脂肪肝與肝病**。
  - 機型：GE Voluson PRO 730，2.5–4 MHz 凸陣，開啟 SRI 與低階組織諧波，gain/TGC 手動調整。
  - 各回音等級的平均值如下：

  | 回音等級 | n | Cr（mg/dL） | 腎長（mm） | 實質厚度（mm） | 皮質厚度（mm） |
  |---|---|---|---|---|---|
  | Grade 1 | 29 | 2.80 | 101.4 | 47.4 | 15.6 |
  | Grade 2 | 21 | 3.69 | 91.4 | 41.1 | 12.9 |
  | Grade 3 | 7 | 3.86 | 89.4 | 40.0 | 11.3 |
  | Grade 4 | 3 | 7.90 | 78 | 37.3 | 無法量（CMD 消失） |

  - 分級與 Cr 的關聯 P=0.004；論文未報告 r 值。
  - 注意：此研究的「實質厚度」40–47 mm 與 Yaprak 的約 11 mm 定義顯然不同。
  - — [PMC3779384](https://pmc.ncbi.nlm.nih.gov/articles/PMC3779384)
- **Hoi, Takata et al., J Clin Med 2018（日本鳥取）**
  - 族群：n=87，基線 eGFR 中位數 67（10–138）。
  - 機型：**Toshiba Aplio 500，3.5 MHz 凸陣**，單一操作者。
  - 量法：皮質厚度從皮髓質交界量到腎被膜，每腎至少 3 點，取雙腎平均，並以身高校正。
  - 數值：皮質厚度中位數 4.4 mm/cm（3.0–6.9）；腎長 60.9 mm/cm。
  - 與基線 eGFR 相關：腎長 r=0.439，皮質厚度 r=0.253，髓質厚度 r=0.166（不顯著）。
  - 預後：皮質厚度可預測 2 年 eGFR 下降≥30% 或透析，AUC 0.786；cut-off 4.0 mm/cm，sens 72.5%、spec 80%。
  - 此研究未量化回音。
  - — [PMC6306756](https://pmc.ncbi.nlm.nih.gov/articles/PMC6306756)
- **其他皮質厚度研究（結果不一）**
  - 迦納：皮質厚度與 eGFR ρ=0.270，腎長 ρ=0.406。作者提出皮質厚度 <4.8 mm 疑似 G4、<1.3 mm 疑似 G5。— [pure.ug.edu.gh](https://pure.ug.edu.gh/en/publications/renal-cortical-thickness-and-bipolar-renal-length-and-their-corre/)
  - 土耳其縱向研究（n=41）：皮質厚度 r=0.85，腎長 r=0.66；24 個月內皮質厚度 5.76→5.28 mm，eGFR 35.9→28.4。— [PMC5769950 / Ultrasonography 2018 (DOAJ)](https://doaj.org/article/81e5ee54ce0642ce90df15714767f338)
  - 另一回顧稱皮質厚度在晚期 CKD 的再現性差。— [Revista Nefrología](https://revistanefrologia.com/en-correlation-renal-ultrasound-parameters-with-articulo-S2013251426000404)

### Inferences
- 回音是唯一與 eGFR 呈中至強相關（約 −0.35 至 −0.68）的單一 B-mode 參數，支持專案以回音比作為主要影像指標。腎長或皮質厚度宜作為輔助協變項，並以身高校正。
- 「實質厚度」與「皮質厚度」在各文獻中的量測端點不同（例如 Siddappa 的實質厚度約 40 mm，Yaprak 約 11 mm）。專案必須明文定義端點：皮質＝錐體底部至被膜；實質＝竇脂肪邊緣至被膜。
- CMD 消失時皮質厚度不可量，這本身就是晚期訊號。

### Gaps
- 沒有找到同一族群依 G1–G5 分期列出回音比、皮質厚度、腎長平均值的大型研究。
- Lucisano 2015 原文（n、機型、回音結果）未取得。
- Yaprak 的回音 Grade 0–IV 文字定義與參考器官未取得，摘要中未提供。

---

## Q2. 回音分級 Grade 0–3 的精確定義、原始出處、觀察者間一致性

### Takeaway
「0 < 肝、I = 肝、II > 肝、III = 腎竇」這套 4 級定義，**普遍歸於 Hricak 1982（Radiology 144:141–147；屬 >40 年的舊文獻）**，但全網只能找到二手表格，無法以原文核對。

文獻中至少有三種互不相容的變體：
- **Hricak 型 4 級**：0 至 III，以腎竇為上錨點。
- **5 級 CMD 型**：Siddappa 2013 與 Yaprak 2017 都是 0 至 IV，以 CMD 是否保留來區分高等級。
- **Brenbridge 型 1–4 級**：最高級等於腎竇或門靜脈。

**目前沒有任何研究報告成人腎皮質回音分級的 kappa。**

### Cited Findings
- 二手表格（2007 超音波期刊）的 Hricak 定義：
  - Grade 0：比肝實質暗（正常）。
  - Grade I：與肝相同（正常）。
  - Grade II：比肝亮（病理）。
  - Grade III：與腎竇相同（病理）。
  - — [PMC3552768 Table 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC3552768/table/tbl1)
- Siddappa 2013 採用 5 級制，**未引用任何原始出處**：
  - Grade 0：<肝，CMD 保留。
  - Grade 1：=肝，CMD 保留。
  - Grade 2：>肝，CMD 保留。
  - Grade 3：>肝，CMD 不佳。
  - Grade 4：>肝，CMD 消失。
  - 兩位放射科醫師以共識解決分歧，未報告 kappa。
  - — [PMC3779384](https://pmc.ncbi.nlm.nih.gov/articles/PMC3779384)
- 搜尋摘要提到 Brenbridge 型量表：grade 1–4，grade 4 等於中央腎竇或門靜脈。此項未開啟原文驗證，出處可能是伊朗兒科研究。— [jpp.mums.ac.ir](https://jpp.mums.ac.ir/article_15837.html)（**未驗證**）
- 系統性搜尋「renal cortical echogenicity grading kappa」，沒有找到成人研究；最接近的只有長度與厚度的一致性（0.754/0.833）。— [SciELO Radiol Bras](https://www.scielo.br/j/rb/a/VLcHYqjHh8Pv9PWbbrJYXDH/?lang=en)
- 作為參考：定量 HRI（肝/腎）由兩位放射科醫師各自圈 ROI 時：
  - 單一器官亮度的 ICC 為 0.87–0.92。
  - **比值本身的 ICC 只有 0.58–0.68**。
  - 同一人重複量測，比值 ICC 約 0.70，Bland-Altman 界限約 ±0.46。
  - 換言之，即使是定量比值，一致性也只是中等。
  - — [Cha et al., Ultrasonography 2021, PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)

### Inferences
- 專案的 Grade 3 若定義為「接近腎竇」，最接近 Hricak III。但 Siddappa 和 Yaprak 的高等級是以 **CMD 消失**來定義，不是以竇亮度。建議在標註手冊中同時記錄兩個欄位，「cortex≈sinus」與「CMD 消失」，以便日後對應不同文獻。
- 由於比值誤差約 ±0.4（HRI 數據），比值帶寬若小於 0.15（例如 1.0 vs 1.15）的分級邊界，單張影像難以穩定區分。應以多張影像或病人層級取平均。

### Gaps
- Hricak 1982 原文的確切分級文字未驗證，也無法確認 0–III 分級是否真的出自該文。
- 成人視覺分級的觀察者間與觀察者內 kappa 完全缺乏，專案自行測量將是新貢獻。
- Yaprak 0–IV 的定義未取得。

---

## Q3. 定量比值的量測協定細節（ROI、深度、gain/TGC、平均 vs 中位、直方圖）

### Takeaway
已發表的協定共通點如下：
- 在同一張影像上，於腎皮質與相鄰的肝（或脾）各取 ROI，且位於**相同深度**。
- 取**平均**灰階；可取多個 ROI 再平均。
- 排除血管、膽管、腎竇、囊腫，並使用原始資料或 DICOM。

各研究的 gain/TGC 都只寫「由操作者最佳化」，沒有固定設定值。唯一有明確處理衰減與 TGC 的是一篇兒科研究：它把肝 ROI 位移，使其與腎 ROI 對齊。

### Cited Findings
- **Libório 2017（全文；巴西 Fortaleza，n=197）**
  - 機型：Medison PICO Mycolor 202，5.0 MHz phased array；影像輸出到熱感紙後再以 ScionImage 分析。
  - 前置：受試者禁食禁水 8 小時。
  - ROI：腎與肝**各取 3 個**，未描述大小與位置；只分析右腎。
  - 排除已知肝病，但作者承認未診斷的脂肪肝可能影響結果。
  - 由單一量測者執行，「以避免觀察者間變異」，未做再現性評估。
  - 腎長平均 10.3 cm，無人 <8 cm。
  - 平均比值在摘要中為 1.06±0.19，內文為 ±0.29（**原文不一致**）。
  - 判斷不可逆晚期 CKD 的 AUC 0.793（0.719–0.867）。
  - PPV：Results 寫 63.8%，Discussion 寫 57.4%，eGFR<30 子群寫 92%（**原文不一致**）。
  - — [Karger KBR 42(4):708](https://karger.com/kbr/article/42/4/708/189945)
- **自動化 HRI 協定（Cha 2021，韓國三星醫院，n=294）**
  - 機型：Philips iU22/HDI、GE LOGIQ E9、Siemens Sequoia。
  - ICNet 分割肝與腎。
  - 腎 ROI：以正規化距離圖（閾值 0.5）去掉外圈，3 類 GMM 取**中間亮度類**作為皮質，再以滑動視窗找最均質的位置。
  - 肝 ROI：放在與腎 ROI 相近的深度，排除血管壁與肋骨陰影。
  - ROI 大小 **15×15 mm²**；比值使用**平均**亮度。
  - 自動與人工的 ICC：肝 0.919、腎 0.916、HRI 0.734。
  - 腎分割 Jaccard 89.4%，肝 76.6%。
  - 排除：腎疤痕、囊腫、影像品質差。
  - — [PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- **兒科「全參數正規化」研究（Cornell，n=26，一半為 CKD 4–5 期）**
  - 做法：肝 ROI 經空間位移，以校正兩器官間的衰減與 TGC 差異。
  - 結果：皮質/肝平均強度，病腎 2.01（1.62–2.40）vs 正常 1.05（0.88–1.23），P<0.001。
  - — [Weill Cornell VIVO pubid27302896](https://vivo.weill.cornell.edu/display/pubid27302896)
- 搜尋 Webb 2009、Marshall 2012 原文均未取得。其 ROI 規則請見前作 B 的二手整理（肝 ROI ≥400 px、同深度、位於焦區或以上、3 對平均）。— [PMC8391375](https://pmc.ncbi.nlm.nih.gov/articles/PMC8391375/)
- **中位數與直方圖方法**：沒有找到任何以中位數或直方圖百分位作為腎/肝比值的已發表臨床研究。Cha 2021 只用中位數來挑選 GMM 類別，比值本身仍用平均。— [PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)

### Inferences（可實作的建議協定，屬推論，非已驗證標準）
1. **影像**：使用原始 DICOM，不用經壓縮的 PNG/JPEG；排除 color Doppler 疊圖的影格。記錄 gain、深度、機型、諧波模式作為協變項。
2. **皮質 ROI**：只取皮質，避開錐體、腎竇、弓狀血管與被膜外脂肪。
   - 自動化可參考 Cha 的流程：去除外圈後做 3 類 GMM 取中間類，再找最均質的視窗。
   - ROI 建議約 5×5 至 10×10 mm，視皮質厚度而定，因為 15×15 mm 在皮質薄時會溢出。
3. **參考 ROI**：右腎配肝、左腎配脾，**ROI 中心深度差不超過約 1 cm**，並位在同一 TGC 帶。肝 ROI 可較大（例如 15×15 mm），但須避開血管與肋影。
4. **統計量**：同時輸出 mean 與 median。主要結果以 mean 對齊文獻，median 作為穩健性分析。每張影像取 3 對 ROI 平均，病人層級再取多張平均。
5. **方向**：一律報告 cortex/reference（腎/肝），與 Moghazi 及 Libório 一致；HRI 是其倒數。

### Gaps
- 沒有任何研究以固定 gain/TGC/dynamic range 做比較，也沒有量化這些設定對腎/肝比的影響。
- 沒有腎/肝比的跨機型（含 Toshiba/Canon）再現性數據。
- 沒有 ROI 大小對腎/肝比影響的研究。

---

## Q4. 已發表的 cut-off 與 eGFR 相關性

### Takeaway
成人唯一有 ROC 的腎/肝比 cut-off 是 **>1.15**（Libório，AUC 0.79，巴西，Medison 機）。

正常值約 0.81–0.99（Manley & O'Neill，二手引用）。兒科病腎的平均約 2.0。

**Grade 2 與 3 之間沒有任何已驗證的數值界線**；左腎/脾比值也沒有經同儕審查的 CKD cut-off。

### Cited Findings
- Libório 2017：腎/肝 >1.15，AUC 0.793。比值與追蹤時的 eGFR 相關 r=−0.684，**與切片當下的 eGFR 無關**。— [Karger](https://karger.com/kbr/article/42/4/708/189945)
- Yaprak 2017：視覺分級的實質回音與 eGFR r=−0.683，這是目前所見最強的單一參數相關。— [Springer Medicine](https://www.springermedicine.com/role-of-ultrasonographic-chronic-kidney-disease-score-in-the-ass/21758436)
- 兒科 CKD 4–5 期：皮質/肝 2.01，正常 1.05。— [VIVO](https://vivo.weill.cornell.edu/display/pubid27302896)
- 前作 B 已整理的其他數值（此處不重複細節）：兒科 EI 1.0–1.1 對 eGFR<90、1.1–1.2 對 eGFR<60；Moghazi 的 >1.0。

### Inferences
- 文獻中的數值錨點如下（皆為單一研究，需在專案資料上重新校準）：

  | 比值（腎/肝） | 文獻意義 | 來源 |
  |---|---|---|
  | 約 0.8–1.0 | 正常 | Manley，二手 |
  | >1.0 | 皮質比肝亮 | Moghazi |
  | >1.15 | 晚期 CKD | Libório |
  | 約 2 | 兒科末期 | Cornell 兒科研究 |

- 推測 Grade 3（接近腎竇）的比值應遠高於 1.15，但沒有數據支持任何特定數字。建議以「皮質/竇」比接近 1 作為操作性定義，並明確標示為未驗證。

### Gaps
- Grade 3 沒有已驗證的 cut-off。
- 沒有腎/脾比的 CKD cut-off。
- 沒有台灣或亞洲成人的腎/肝定量 cut-off 研究。本輪搜尋未找到，前作也未找到。

---

## Q5. 干擾因子（脂肪肝、肝病、gain、深度、機型、肥胖）

### Takeaway
脂肪肝是最大的干擾因子。驗證研究的處理方式都是「排除」，例如 Libório 與 Siddappa 都排除了肝病或脂肪肝，而沒有加以校正。

比值的再現性明顯低於單一器官亮度（ICC 約 0.6–0.7 vs 約 0.9），這代表兩個 ROI 的誤差會在比值中累積。

### Cited Findings
- Siddappa 以超音波排除脂肪肝與肝病。— [PMC3779384](https://pmc.ncbi.nlm.nih.gov/articles/PMC3779384)
- Libório 只排除了已知肝病，並承認未診斷的脂肪肝是限制。— [Karger](https://karger.com/kbr/article/42/4/708/189945)
- HRI 比值的 ICC（0.58–0.68）低於肝或腎單獨亮度的 ICC（0.87–0.92）。研究對象為健康捐肝者，作者明言結果不適用於慢性腎病或中重度脂肪肝。— [PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- Cornell 兒科研究以位移肝 ROI 來處理衰減與 TGC，顯示深度與 TGC 是公認的干擾因子。— [VIVO](https://vivo.weill.cornell.edu/display/pubid27302896)

### Inferences
- 專案應做到以下三點：
  1. 每位病人同時計算右腎/肝與左腎/脾比值。
  2. 以肝/脾亮度比（同深度）標記疑似脂肪肝。
  3. 在主要分析中排除疑似脂肪肝，或將其改用脾作參考。
- 肥胖會增加深度與衰減，應將深度與 BMI 列為協變項。

### Gaps
- 沒有找到脂肪肝對腎/肝比的定量校正公式。
- 沒有肥胖或 BMI 對比值影響的數據。

---

## Q6. 自動與半自動回音量測及其再現性

### Takeaway
最接近專案設計的已發表研究有兩個：
- Yonsei Mask R-CNN（前作 B 已述）：自動抽取腎/肝比後，AUROC 從 0.81 提升到 0.88。但**未報告比值本身的再現性**。
- Cha 2021：自動 HRI 與放射科醫師的 ICC 為 0.734，可作為「自動比值可達到的一致性」上限參考。

### Cited Findings
- Cha 2021：自動 vs 人工 HRI ICC 0.734，無失敗案例，處理時間 80 ms。— [PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)
- Yonsei J Digit Imaging（n=909）：只報告分類 AUROC，沒有比值的 test-retest 數據。— [Yonsei repository](https://ir.ymlib.yonsei.ac.kr/handle/22282913/193103)
- 2026 年深度學習回顧指出，觀察者間變異限制了腎超音波的準確度。— [PMC12832298](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12832298/)

### Inferences
- 專案驗證時建議同時報告兩項：自動 vs 醫師 ROI 比值的 ICC，以 Cha 的 0.73 為參照；以及同一病人多張影像間比值的 ICC。

### Gaps
- 沒有找到在 CKD 族群中驗證自動腎/肝比再現性的研究。
- 沒有找到自動化的腎/脾比研究。
