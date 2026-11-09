# 腎臟超音波分割基準數字與人類標註者一致性（用於設定 4 類：腎實質／腎竇／肝／脾 的目標）

研究日期：2026-10-25。本筆記補充先前的 `segmentation_models.md` 與 `public_kidney_us_datasets.md`。那兩份筆記無法讀取 OKUD PDF；這次已用 pdftotext 抽出 OKUD 論文（arXiv 2206.06657v2）全文，所以先前標為 UNVERIFIED 的 inter-rater、intra-rater、nnU-Net 逐類 Dice 與 HD，這裡都已補上原始數字。共使用約 17 次工具呼叫。

**判讀注意：** pdftotext 的 layout 模式會讓 OKUD 表格的列標籤錯位一列。下面的對應是依「Mean 欄 = 四類平均」驗算後重建的（例如 Both 模型：(0.85+0.52+0.59+0.78)/4 = 0.685 ≈ 0.69）。建議人工對照 PDF 的 Table 3／4 再確認一次。

---

## Q1. 成人 2D B-mode 全腎（capsule）分割 Dice，含 CKD 族群

### Takeaway
成人 2D 全腎 Dice 的範圍很大，取決於資料：
- **多廠牌、CKD／移植族群的 OKUD**：nnU-Net 官方基準為 **0.85–0.87**（HD 約 11–15 mm）。後續自訂網路在 OKUD 上可到 0.90–0.94。
- **單中心、影像品質較一致的資料**：常見 0.93–0.97。

人類 inter-rater 全腎 Dice 為 0.93–0.95。所以「全腎約 0.92–0.94」是合理的天花板等級目標，超過 0.95 多半代表測試集太乾淨或有資料洩漏。

### Cited Findings

**OKUD 資料集本身（Singla et al., ASMUS 2023 / arXiv 2206.06657v2）**
- 規模：514 張獨立 2D B-mode 影像，每位病人 1 張；另含 20 張重複複本，用於 intra-rater 評估，共 534 個檔案。
- 收案：2015/01–2019/09，單一加拿大三級醫院（UBC／Vancouver）。
- 族群：年齡 53.2±14.7 歲，男 63%，BMI 27.0±5.4。**平均 eGFR 28.7±21.3**。ESKD 病因為糖尿病 32%、IgA 腎病 11%、高血壓 10%。
- 機器：Philips、GE、Acuson、Siemens、Toshiba、SonoSite 多廠牌。
- 以上均見 [arXiv 2206.06657v2 PDF](https://arxiv.org/pdf/2206.06657v2)；機器清單見 [GitHub kidneyUS](https://github.com/rsingla92/kidneyUS)。

**OKUD Table 1 的分布（表格錯位，順序需人工確認）**
- 品質：good 486（91.0%）、fair 41（7.7%）、poor 6（1.1%）、unsatisfactory 1（0.2%）。
- 切面：縱切 371（69.5%）、橫切 145（27.2%）、other 18（3.4%）。
- 腎臟類型：解析結果為 148（27.8%）對 386（72.2%）。依文中「transplant recipients…」描述與 eGFR 推測，**移植腎佔多數**，但哪一個數字對應 native、哪一個對應 transplant，需看原表確認。
- 來源：[arXiv 2206.06657v2](https://arxiv.org/pdf/2206.06657v2)

**OKUD 官方 nnU-Net 基準**
- 設定：2D nnU-Net，**80:20 隨機分 train/test**（每病人只有 1 張，所以等同病人層級切分），train 部分做 5-fold CV，再以 ensemble 推論。訓練 500 epochs、batch 4、Dice+CE loss，單張 V100，每個網路約 9 小時。
- 訓練了三個模型：只用 S1 標註、只用 S2 標註、每張隨機 50/50 抽一位標註者（Both）。
- Capsule 結果：

| 模型 | DSC | HD (mm) |
|---|---|---|
| S1 | 0.87 | 11.0 |
| S2 | 0.85 | 15.5 |
| Both | 0.85 | 12.2 |

- 來源：[arXiv 2206.06657v2 Table 4](https://arxiv.org/pdf/2206.06657v2)

**同組 J. Med. Imaging 2023**
- 用同一個 nnU-Net（514 張、80:20、5-fold、標註隨機二選一）得到 capsule **Dice 0.86±0.01**。
- 來源：[PMC10248852](https://pmc.ncbi.nlm.nih.gov/articles/PMC10248852/)

**MAT-UNet（Diagnostics 2025, 15(15):1978）在 OKUD 上的 capsule 結果**
- 設定：只用**第二位標註者（S2）**的標註，排除無 capsule 標註者後剩 481 人。隨機切分為 341/49/97（train/val/test），訓練時 crop 成 512×512。

| 方法 | DSC (%) | IoU (%) | HD95 |
|---|---|---|---|
| UNet | 89.95 | 82.54 | 81.02 |
| Attention UNet | 90.69 | 83.79 | 71.13 |
| SwinUNet | 78.94 | 67.16 | 82.09 |
| I2UNet | 92.14 | 86.12 | 38.02 |
| MAT-UNet | 93.83 | 88.74 | 32.02 |

- 論文表格標的 HD95 單位是 "mm"，但數值（32–82）遠大於 OKUD 原作的 HD（11–15 mm），很可能其實是像素，或採用不同定義，**不可直接比較**。
- 本文沒有跑 nnU-Net baseline。
- 來源：[PMC12346135](https://pmc.ncbi.nlm.nih.gov/articles/PMC12346135/)

**Valente et al., EMBC 2023（OKUD 多類比較）**
- 設定：只用 4 類標註齊全的 321 張影像，比較 7 個網路（DynUNet、SwinUNETR、UNet++、DeepLabV3+、FCN、PSPNet、UNet）。
- 最佳的 DeepLabV3+：capsule 94.2%、CEC 85.8%、cortex 62.4%、medulla 69.6%；四類平均 78.0%，作者報告的 inter-rater 平均為 75.6%。
- 只取得摘要，切分方式與 inter-rater 的計算方式都未驗證。
- 來源：[IEEE DOI 10.1109/embc40787.2023.10341170](https://doi.org/10.1109/embc40787.2023.10341170)；[SDU portal](https://portal.findresearcher.sdu.dk/en/publications/a-comparative-study-of-deep-learning-methods-for-multi-class-sema/)

**Yin et al.（Med Image Anal 2020；CHOP）**
- 資料：289 張 2D 矢狀切、152 位受試者；機器為 Philips、Siemens、GE；依作者單位推測為小兒族群。
- 切分：105 train / 20 val / 164 test（影像層級；文中未說明同一病人的左右腎是否跨集合），另做 5-fold CV。
- 有資料增強時的 test Dice：

| 方法 | Dice |
|---|---|
| U-Net | 0.9245±0.040 |
| DeepLabV3+ | 0.9311 |
| PSPNet | 0.9372 |
| 提出的 Bnet | 0.9427±0.045（Jaccard 0.894） |
| end-to-end | 0.9451 |

- 沒有資料增強時，baseline 只有 0.80–0.90。
- 來源：[PMC6980346](https://pmc.ncbi.nlm.nih.gov/articles/PMC6980346/)

**TRUSTED（3D 經腹超音波，48 人／96 腎）**
- 4 種 DNN 在 US 上的 Dice 為 **70.5–80.7%**，同一批病人的 CT 為 79.6–90.1%。
- 這是 3D 資料，不能直接拿來和 2D 比。
- 來源：[Scientific Data 2025](https://www.nature.com/articles/s41597-025-04467-1)；[arXiv 2310.12646](https://arxiv.org/pdf/2310.12646)

**其他全腎數字（先前筆記已列，這裡不重複細節）**
- YSegNet 0.97、Fast-UNet++ >0.95、MLAU-Net 0.902、Biomolecules 2023 0.946，多為單中心。
- 來源：[Frontiers Oncol 2026 review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)；[PMC10604927](https://pmc.ncbi.nlm.nih.gov/articles/PMC10604927)

### Inferences
- **OKUD nnU-Net（0.85）明顯低於後續論文（0.90–0.94），原因可能包括：**
  - nnU-Net 的評估包含 test 中所有影像，連 poor 品質與橫切都算在內，而 MAT-UNet 只排除了「無 capsule 標註」的影像。
  - 評估時用的標註者不同（S1、S2，或混合）。
  - 隨機切分的變異：測試集只有約 100 張，±0.02–0.03 都屬噪音範圍。
  - 先前筆記中提到的 v1 = 0.74 → v2 = 0.85 的版本差異，也說明這個數字對設定高度敏感。
- **本專案的條件**是單院、單一（或少數）機型、成人、約 181 位病人。這比 OKUD 單純，又比 Yin 的乾淨資料略雜。全腎（parenchyma ∪ sinus）**合理目標為 Dice 0.92–0.94**，最低可接受約 0.90。
- 若測試集超過 0.95，應檢查是否有同一病人同時出現在 train 與 test、或同一 cine 的相鄰幀分到不同集合。

### Gaps
- 沒有找到 Kim et al.、Alex et al.、Chen et al. 的成人 2D 全腎 Dice 原文數字，本次未檢索到。
- 沒有找到「只限 CKD 成人、非移植」的 2D 全腎 Dice 論文。OKUD 的 eGFR 偏低，但混入了移植腎。
- MAT-UNet 的 HD95 單位存疑，也沒有 nnU-Net 對照。

---

## Q2. 腎內部子區域（cortex／medulla／CEC＝腎竇）分割 Dice

### Takeaway
- **CEC／腎竇**：模型 Dice 約 **0.76–0.86**，人類 inter-rater 0.82。
- **Cortex 與 medulla 分開分割**：模型只有 0.43–0.70，人類 inter-rater 更低，只有 0.48 和 0.54。這兩類的天花板主要受標註定義與標註噪音限制，不是模型能力的問題。

本專案把 cortex 與 medulla 合併成「腎實質」，正好避開最不穩定的那條邊界（皮髓質交界）。

### Cited Findings

**OKUD 官方 nnU-Net DSC**

| 模型 | Capsule | Cortex | Medulla | CEC | Mean |
|---|---|---|---|---|---|
| S1 | 0.87 | 0.43 | 0.48 | 0.76 | 0.63 |
| S2 | 0.85 | 0.51 | 0.57 | 0.66 | 0.67 |
| Both | 0.85 | 0.52 | 0.59 | 0.78 | 0.69 |

**OKUD 官方 nnU-Net HD（mm）**

| 模型 | Capsule | Cortex | Medulla | CEC | Mean |
|---|---|---|---|---|---|
| S1 | 11.0 | 16.4 | 11.8 | 10.7 | 12.5 |
| S2 | 15.5 | 13.7 | 9.3 | 15.9 | 13.6 |
| Both | 12.2 | 12.9 | 9.8 | 10.8 | 11.4 |

- 來源：[arXiv 2206.06657v2 Table 4](https://arxiv.org/pdf/2206.06657v2)

**MAT-UNet（OKUD，S2 標註）**
- 設定：只用 cortex、medulla、CEC 三類都有標註的 323 人，隨機切分為 226/32/65。

| 方法 | CEC DSC | Medulla DSC | Cortex DSC |
|---|---|---|---|
| UNet | 81.48 | 64.81 | 57.04 |
| Attention UNet | 81.42 | 62.91 | 58.30 |
| SwinUNet | 72.72 | 52.41 | 43.54 |
| MAT-UNet | 84.34 | 66.34 | 58.93 |

- MAT-UNet 的 IoU：CEC 74.26、medulla 51.78、cortex 43.61。
- 來源：[PMC12346135](https://pmc.ncbi.nlm.nih.gov/articles/PMC12346135/)

**Valente EMBC 2023（DeepLabV3+）**
- CEC 85.8%、cortex 62.4%、medulla 69.6%。
- 來源：[DOI](https://doi.org/10.1109/embc40787.2023.10341170)

**OKUD 標註定義**
- CEC 是 sonographer 無法個別分開的腎盂、腎盞、血管、脂肪的集合。原作者明言 "there is no prior definition of the central echogenic complex"，而且 cortex 與 medulla 的解剖界線 "unclear"。
- 標註都是手畫多邊形，不限頂點數。
- 來源：[arXiv 2206.06657v2](https://arxiv.org/pdf/2206.06657v2)

**OKUD 敏感度分析**
- 腹部影像約 0.1 mm/pixel，所以 10 px 約等於 1 mm。
- 把標註 erosion 10 px，cortex 的 DSC 變動約 37–62%，CEC 約 16–28%。
- 1 px 的變動只造成約 2–7% 的 DSC 變化。
- 作者的結論是 DSC 對小結構太敏感。
- 來源：[arXiv 2206.06657v2 Table 5](https://arxiv.org/pdf/2206.06657v2)

**像素佔比**
- 在 S1／S2 的標註中，CEC 約佔 capsule 面積的 26%，cortex 約 13–14%（中位數）。
- 這張表的錯位嚴重，只作為量級參考。
- 來源：[arXiv 2206.06657v2 Table 2](https://arxiv.org/pdf/2206.06657v2)

**3D 小兒水腎超音波（半自動）**
- 腎實質與 capsule 的一致性高，collecting system 的 Dice 中位數約 0.77。
- 只看到摘要片段，屬於 3D 小兒資料，不可直接比較。
- 來源：[PubMed 40327095](https://pubmed.ncbi.nlm.nih.gov/40327095/)

### Inferences
- **「腎實質 = cortex ∪ medulla」沒有任何論文直接報告 Dice。** 幾何上，實質 = capsule − CEC，它的錯誤來自外框（capsule）與內框（CEC）兩條邊界。估計 Dice 會落在 capsule（約 0.90）與 CEC（約 0.82）之間，而且因為它是環狀的薄結構，可能偏低。
- 據此推論目標：
  - **腎實質 Dice 約 0.80–0.87**
  - **腎竇 Dice 約 0.78–0.86**

  以上為推論，非文獻數字。
- 腎竇的 Dice 應依切面分層報告。縱切面上的 CEC 較大；橫切面與 poor 品質的影像會拉低平均。

### Gaps
- 沒有找到 OKUD 把 cortex 與 medulla 合併成 parenchyma 後的 Dice 或 inter-rater 數字。可用 OKUD 的兩組標註自行計算，這是最直接的「人類上限」估計。
- 沒有找到 OKUD 以外的成人腎竇（sinus）2D 分割 Dice。

---

## Q3. 人類標註者之間（inter-observer）與自身前後（intra-observer）一致性；標註噪音佔多少差距

### Takeaway
在 OKUD（2 位資深 sonographer，各有超過 30 年經驗）中：
- **Inter-rater Dice**：capsule 0.93、CEC 0.82、medulla 0.54、cortex 0.48。
- **Intra-rater Dice**：capsule 0.95–0.96、CEC 0.85–0.89、cortex 0.62–0.72、medulla 0.75–0.80。

也就是說，capsule 與 CEC 的模型 Dice（0.85–0.94、0.76–0.86）已接近人類之間的一致性。Cortex 與 medulla 的模型分數甚至「超過」inter-rater，因為模型是對同一位標註者評估的。所以目前多數剩下的差距屬於標註噪音或定義模糊，而不是模型可改善的錯誤。

### Cited Findings

**OKUD Table 3 Dice**

| | Capsule | Cortex | Medulla | CEC |
|---|---|---|---|---|
| Intra S1 | 0.95±0.02 | 0.62±0.26 | 0.75±0.21 | 0.85±0.07 |
| Intra S2 | 0.96±0.01 | 0.72±0.20 | 0.80±0.18 | 0.89±0.06 |
| **Inter（S1 vs S2）** | **0.93±0.10** | **0.48±0.37** | **0.54±0.38** | **0.82±0.17** |

- Intra-rater 的評估方式：10 張影像各重複 3 次、盲測。Inter-rater 的評估方式：隨機抽 50 張比較。
- 來源：[arXiv 2206.06657v2](https://arxiv.org/pdf/2206.06657v2)
- OKUD 的品質把關：由工程師覆核，發現「有 cortex 卻沒 medulla」這類不一致時退回重標、達成共識。兩位 sonographer 的標註沒有融合，資料集分別釋出各自的標註。
- 同一資料的類別出現頻率（有幾張圖標了 medulla 等）在兩位 sonographer 之間不同，作者歸因於判讀差異。
- 以上兩點的來源：[arXiv 2206.06657v2 Table 1/2](https://arxiv.org/pdf/2206.06657v2)

**Valente EMBC 2023**
- inter-rater 四類平均 75.6%，DeepLabV3+ 為 78.0%，作者據此宣稱「超越 inter-rater」。
- 注意：用 OKUD Table 3 的 inter-rater 四類值平均只有約 0.69，與 75.6% 不一致。原因可能是 Valente 只在 321 張完整影像上自行計算。**兩者不可混用。**
- 來源：[DOI](https://doi.org/10.1109/embc40787.2023.10341170)

**Yin et al.（小兒 2D 全腎）**
- 兩位泌尿科醫師在 20 張影像上的 inter-rater Dice 為 **0.95±0.02**。其中腎臟被畫面截斷的影像為 0.92±0.03，其餘為 0.96±0.01。
- 對照模型 0.94–0.945，同樣已接近人類水準。
- 來源：[PMC6980346](https://pmc.ncbi.nlm.nih.gov/articles/PMC6980346/)

**TRUSTED（3D US）**
- 兩位 radiographer 的一致性 >93% Dice，以 STAPLE 產生共識標註。各標註者對共識在 US 上約 94.4–94.5%，CT 上約 95.4–95.7%。模型在 US 上只有 70.5–80.7%。
- 與 2D 不同：在 3D US，模型與人類之間的差距仍然很大。
- 來源：[Scientific Data](https://www.nature.com/articles/s41597-025-04467-1)

**Frontiers 2026 review**
- 不同操作者造成 Dice 變動 5–7%，標註耗時每張 10–15 分鐘。
- 這是 review 的整理，原始來源未追查。
- 來源：[PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)

### Inferences
- **評估方式的建議：**
  - 在本地資料抽 30–50 張，請第二位標註者（或同一人間隔 ≥2 週）重標，算出本專案自己的 inter-／intra-rater Dice，作為「天花板」。
  - 目標設為「模型 vs 標註者 ≥ inter-rater 的 95–100%」，而不是追求絕對數字。
- 若只有一位標註者，模型的 test Dice 反映的是「學到該標註者的習慣」，會比與第二位專家比較時高。報告時應註明這一點。
- **邊界距離指標：** HD 與 HD95 對單一離群像素很敏感。OKUD 的 HD 約 10–16 mm。本專案若要報告，建議同時報告 HD95 與 mean surface distance（以 mm 計，需要 DICOM pixel spacing）。

### Gaps
- 沒有找到成人 2D 腎超音波「腎實質（合併）」與「腎竇」由第二組獨立團隊做的 inter-rater 研究。
- 沒有肝臟或脾臟超音波 2D 分割的 inter-rater Dice（見 Q5）。

---

## Q4. 自動化腎長度／皮質厚度 vs 人工（Bland-Altman、ICC）

### Takeaway
目前只有一篇經同儕審查、以超音波分割推導腎長度的研究（UBC，用 OKUD 訓練的 nnU-Net）：
- 演算法與專家的平均差 **2.6 mm**，LoA 為 0.17 到 5.03 mm。
- 專家之間的 inter-rater 變異為 1.5 mm，intra-rater 為 1.0 mm。

皮質或實質厚度的自動化 vs 人工一致性，在超音波上沒有找到可用的驗證數字。

### Cited Findings

**Beitollahi/Singla 等，J Med Imaging 2023**
- 資料：132 段 cine、92 位受試者（native 61、transplant 31），共 16,612 幀。
- Capsule Dice 0.86±0.01。
- 長度：

| 測量者 | 腎長度（mm） |
|---|---|
| 專家 | 84.8±26.4 |
| 演算法 | 86.3±24.4（與專家無顯著差異） |
| 新手 | 82.3±22.9 |

- Bland-Altman：
  - 演算法 vs 專家：mean diff 2.6 mm（SD 1.2），LoA 0.17–5.03 mm。
  - 新手 vs 專家：3.7 mm，LoA −1.98–9.38 mm。
- Inter-rater：專家 1.5 mm、新手 6.3 mm。Intra-rater：專家 1.0 mm、新手 6.6 mm。
- 未報告 ICC。
- 來源：[PMC10248852](https://pmc.ncbi.nlm.nih.gov/articles/PMC10248852/)；[PubMed 37304526](https://pubmed.ncbi.nlm.nih.gov/37304526/)
- 演算法系統性偏長約 2.6 mm（LoA 全為正值），表示存在固定偏差，可以校正。

**Research Square 預印本「Automated AI-Driven Measurement of Kidney Length…Adult and Pediatric」**
- 搜尋摘要顯示，AI 對放射科醫師的 ICC：右腎 0.94–0.98、左腎 0.96–0.98，並有 67 人以 CT 為參考。
- 全文抓取失敗，**未經同儕審查，數字未驗證**。
- 來源：[Research Square rs-6975938](https://www.researchsquare.com/article/rs-6975938/v1)

**Ultrasonography 2025（UMass／KAIST／SNUH）**
- 資料：258 顆右腎（正常 124、CKD 134），Philips EPIQ Elite，2–9 MHz。
- 方法：先手繪腎臟與腎竇輪廓，再用 OpenCV fitEllipse 自動計算實質厚度與實質／竇比例。
- 腎長度仍為手動量測；**未報告任何 Dice、ICC 或 Bland-Altman**。
- 用於分類 CKD 時，準確率 82%（只用影像 DL 為 64%）。
- 文中摘要提到皮質厚度正常約 8.9 mm、CKD 約 7.2 mm（人工量測）。
- 來源：[PMC12457927](https://pmc.ncbi.nlm.nih.gov/articles/PMC12457927/)

**CT 上的同類研究（方法學參考，非超音波）**
- 分割後的厚度與長度 ICC >0.90。
- 該文採用的 ICC 分級：<0.5 差、0.5–0.75 中等、0.75–0.9 好、≥0.9 優。
- 來源：[Eur Radiol Exp 2024](https://link.springer.com/article/10.1186/s41747-024-00507-4)

**Kim et al. 2021（小兒 331 人，U-Net + active contour）**
- 體積 vs CT 的 ICC 為 0.925（先前筆記已列）。
- 來源：[PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)

### Inferences
- 本專案腎長度驗收可參考：
  - Bland-Altman mean bias ≤3 mm
  - 95% LoA 寬度 ≤ ±5 mm
  - ICC ≥ 0.90

  最好同時算出本地 sonographer 的 inter-observer 差（文獻：專家約 1.5 mm）作為對照。
- 實質厚度約 7–9 mm。在 0.1–0.3 mm/pixel 下，1 mm 的邊界誤差就是 11–14% 的相對誤差。因此厚度的驗收標準應以 mm 絕對誤差設定，例如 MAE ≤1–1.5 mm（推論），而不是 Dice。

### Gaps
- 沒有找到超音波自動實質厚度 vs 人工的 ICC 或 Bland-Altman 研究。
- Research Square 預印本的資料細節（機型、人數、Dice）未取得。

---

## Q5. 超音波肝臟（與脾臟）分割的典型 Dice

### Takeaway
- **肝臟**：2D 超音波分割 Dice 通常 **0.88–0.95**。
- **脾臟**：明顯較差，在小兒 FAST 資料上 **0.60–0.82**。

沒有找到成人「腎＋肝＋脾」同時分割的 2D 論文數字。

### Cited Findings

**Sensors 2024（肝纖維化 RF 研究）**
- 用由 RF 訊號重建的 B-mode 影像做肝臟 ROI 分割，test Dice：U-Net 95.05%、Attention U-Net 94.68%。
- 來源：[PMC11397918](https://pmc.ncbi.nlm.nih.gov/articles/PMC11397918/)

**IEEE IUS 2023（肝臟分割＋脂肪肝分級）**
- 外部資料集 Dice 0.92（95% CI 0.78–1.00），CI 很寬。
- 來源：[IEEE 10307501](https://ieeexplore.ieee.org/abstract/document/10307501)

**自監督肝臟分割（小量標註，預印本）**
- Dice 78–89%；最佳 U-Net 變體在 3-fold CV 下 0.921。
- 來源：[ResearchGate](https://www.researchgate.net/publication/371358350_Liver_Segmentation_in_Ultrasound_Images_Using_Self-Supervised_Learning_with_Physics-inspired_Augmentation_and_Global-Local_Refinement)

**US-AbdomenSeg（Kornblith Lab，小兒 FAST，6 器官）**
- Test Dice：

| 模型 | Kidney | Liver | Spleen |
|---|---|---|---|
| U-Net | 0.92 | 0.84 | 0.70 |
| EVIT-UNet | 0.93 | 0.90 | 0.82 |
| UltraSam | 0.91 | 0.90 | 0.81 |
| nnU-Net | 0.85 | 0.89 | 0.60 |

- Test 張數：腎 306、肝 445、脾 172。
- 未報告訓練集大小、機型、inter-rater 與論文出處。
- 來源：[GitHub US-AbdomenSeg](https://github.com/Kornblith-Lab/US-AbdomenSeg)

**上腹部超音波標準切面＋多器官分割（PubMed 42399171）**
- 資料：單中心，521 段影片、5,535 幀。
- 搜尋摘要顯示：肝、膽囊、右腎表現強，脾與胰較弱（胰 IoU 53.76%）。具體數字未取得。
- 來源：[PubMed 42399171](https://pubmed.ncbi.nlm.nih.gov/42399171/)

**Fast-UNet 腎／肝**
- 腎 Dice 94%、肝 97%，用於肝腎指數（hepatorenal index），屬會議摘要（先前筆記已列）。
- 來源：[ESR](https://connect.myesr.org/?p=42230)

**CT 對照**
- LiTS 肝約 0.94～0.96 以上、MSD 脾約 0.87–0.96。
- 來源：[ScienceDirect review](https://www.sciencedirect.com/science/article/pii/S2950261625000408)

### Inferences
- 本專案的肝與脾通常只出現在影像的一部分（被扇形邊界或深度截斷），邊界的定義可能比腎臟更模糊。
- 推論目標：
  - **肝 Dice 0.88–0.93**
  - **脾 Dice 0.75–0.85**，樣本少時可能更低
- 由於肝與脾只用於回音比較 ROI，比 Dice 更有意義的驗收是「ROI 落在器官內的比例 ≥95%」與「同深度 ROI 灰階和人工 ROI 的 ICC」。這是推論。
- 「Dice 對大器官偏高」：肝在畫面中佔比大，Dice 容易高，不代表邊界準確。應另報告 HD95。

### Gaps
- 沒有找到成人 2D 超音波脾臟分割的專門研究，也沒有肝或脾超音波分割的 inter-rater Dice。
- US-AbdomenSeg 沒有對應的論文或標註協定可查。

---

## Q6. 部分標註（partial label）與小資料（數百張）情境

### Takeaway
已發表的腎超音波分割幾乎都落在數百張這個量級（OKUD 約 323–514、Yin 289 張其中 105 張 train、Valente 321 張），這些資料量已足以達到上述 Dice。所以本專案約 975 張、181 人的資料量並不吃虧。真正的瓶頸是標註一致性與切分方式。沒有找到腎超音波的學習曲線研究或 partial-label 方法的數字。

### Cited Findings
- Yin et al. 只用 105 張訓練影像，test Dice 0.94。資料增強影響很大：沒有增強時 baseline 為 0.80–0.90，有增強時為 0.92–0.94。來源：[PMC6980346](https://pmc.ncbi.nlm.nih.gov/articles/PMC6980346/)
- MAT-UNet 只用 226 張訓練（內部結構），CEC Dice 84%。來源：[PMC12346135](https://pmc.ncbi.nlm.nih.gov/articles/PMC12346135/)
- **OKUD 的「部分標註」事實**：
  - 514 張中只有約 316–323 張四類都有標註；有 capsule 的約 452–481 張。
  - 橫切面或品質差的影像常缺 medulla 或 CEC。
  - 文獻普遍的做法是**排除缺類影像**，而不是用 partial-label loss。
  - 來源：[arXiv 2206.06657v2 Table 1](https://arxiv.org/pdf/2206.06657v2)；[PMC12346135](https://pmc.ncbi.nlm.nih.gov/articles/PMC12346135/)
- OKUD 曾比較「單一標註者模型」與「兩者隨機混合模型」。混合模型的 cortex、medulla、CEC 與平均 Dice 略高（0.69 vs 0.63／0.67），但混合標註同時也引入了噪音。來源：[arXiv 2206.06657v2](https://arxiv.org/pdf/2206.06657v2)

### Inferences
- 本專案的肝或脾只在部分影像中出現（右腎配肝、左腎配脾），屬於「類別不在畫面中」，而不是「有但沒標」。
- 必須在標註規則中區分兩種情況：
  - 器官**不存在**：標為背景是正確的。
  - 器官**存在但未標**：會被當成背景，造成錯誤監督。
- 舊資料若只有腎臟遮罩，應使用 partial-label 的做法：對未標的類別做 loss masking，或使用 nnU-Net 的 ignore label。或者確保送進訓練的每張影像都完整標註 4 類。這是推論；nnU-Net 支援 ignore label 是依先前知識，未在本次查證。
- 評估時，每個類別只在「GT 有該類」的影像上計算 Dice。GT 沒有該類但模型預測出來的情況，另以偽陽性率報告。否則空類別會把 Dice 拉成 0 或 1，造成扭曲。

### Gaps
- 沒有找到腎超音波的「Dice vs 訓練張數」學習曲線。
- 沒有找到用 partial-label 或 ignore-label 訓練腎、肝、脾超音波的發表數字。

---

## Q7. 是否有完全相同 4 類設定的發表結果？合理目標為何？

### Takeaway
**沒有**找到「腎實質＋腎竇＋肝＋脾」4 類 2D 成人超音波分割的發表結果。目標只能拼湊：
- 腎內部來自 OKUD（CEC、capsule）。
- 肝與脾來自其他超音波研究。
- 人類天花板來自 OKUD 與 Yin 的 inter-rater 數據。

### Cited Findings（拼湊依據）

| 結構 | 已發表模型 Dice | 人類 inter-rater Dice | 主要來源與注意事項 |
|---|---|---|---|
| 全腎／capsule（2D 成人，多廠牌，CKD／移植） | 0.85–0.87（nnU-Net 官方）；0.90–0.94（UNet、MAT-UNet、DeepLabV3+） | 0.93±0.10（intra 0.95–0.96） | [OKUD](https://arxiv.org/pdf/2206.06657v2)、[PMC12346135](https://pmc.ncbi.nlm.nih.gov/articles/PMC12346135/)、[EMBC](https://doi.org/10.1109/embc40787.2023.10341170)；n 約 100 test、隨機切分、每人 1 張 |
| 全腎（2D 小兒，3 廠牌） | 0.92–0.945 | 0.95±0.02 | [PMC6980346](https://pmc.ncbi.nlm.nih.gov/articles/PMC6980346/)；164 張 test |
| 全腎（3D 成人） | 0.705–0.807 | >0.93 | [TRUSTED](https://www.nature.com/articles/s41597-025-04467-1)；3D，不可比 |
| CEC／腎竇 | 0.66–0.78（nnU-Net）；0.81–0.86（UNet 至 DeepLabV3+） | 0.82±0.17（intra 0.85–0.89） | OKUD、MAT-UNet、Valente |
| Cortex（單獨） | 0.43–0.62 | 0.48±0.37 | 同上；定義模糊 |
| Medulla（單獨） | 0.48–0.70 | 0.54±0.38 | 同上 |
| 腎實質（cortex＋medulla） | **無發表數字** | **無** | — |
| 肝 | 0.84–0.95 | 無 | [PMC11397918](https://pmc.ncbi.nlm.nih.gov/articles/PMC11397918/)、[IEEE](https://ieeexplore.ieee.org/abstract/document/10307501)、[US-AbdomenSeg](https://github.com/Kornblith-Lab/US-AbdomenSeg)（小兒） |
| 脾 | 0.60–0.82 | 無 | [US-AbdomenSeg](https://github.com/Kornblith-Lab/US-AbdomenSeg)（小兒 FAST） |
| 腎長度 | bias 2.6 mm，LoA 0.17–5.03 mm | 專家間 1.5 mm | [PMC10248852](https://pmc.ncbi.nlm.nih.gov/articles/PMC10248852/) |
| HD（腎） | OKUD nnU-Net 約 11–16 mm | — | OKUD；MAT-UNet 的 HD95 單位存疑 |

### Inferences（建議目標，為推論，請以本地 inter-rater 校正）
- **全腎**（實質 ∪ 竇）：Dice ≥0.92（理想 0.93–0.94），HD95 ≤10 mm。
- **腎竇**：Dice ≥0.80（理想 0.83–0.86）。
- **腎實質**：Dice ≥0.80（理想 0.85）。必須先在本地算 inter-rater；若人類只有約 0.80，模型目標就設在 0.78–0.80。
- **肝**：Dice ≥0.88（理想 0.90–0.93）。
- **脾**：Dice ≥0.75（理想 0.80–0.85），以只在有脾的影像上計算為準。
- **腎長度**：bias ≤3 mm、LoA ≤ ±5 mm、ICC ≥0.90。
- **報告規範**：
  - 病人層級切分，同一病人的左右腎與多張影像都在同一集合。
  - 依切面（縱／橫）與影像品質分層。
  - 同時報告 Dice、HD95、mean surface distance，以及 inter-rater 天花板。
  - 單院資料要註明會高估外部表現。OKUD 原作者也提醒過 acquisition shift。
- **不可比較的要點**：
  - OKUD 的 nnU-Net 數字包含 poor 與橫切影像；MAT-UNet 只用 S2 標註並排除缺類影像；Valente 只用 321 張完整影像。
  - 各研究的 HD 定義與單位不一。
  - 小兒、3D、移植腎的數字不能直接套用到成人原生腎 CKD。

### Gaps
- 完全相同的 4 類設定沒有任何發表基準。
- 腎實質（合併類）與肝、脾的 inter-rater 數字缺乏。
- 沒有成人 CKD 原生腎（非移植）專屬的 2D 分割數字。
- 沒有台灣或亞洲機型（例如 Canon／Toshiba Aplio）的腎超音波分割跨機型研究。
