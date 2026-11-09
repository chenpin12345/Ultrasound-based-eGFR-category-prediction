# 成人腎臟縱切超音波：腎 / 肝 / 脾的影像特徵與易混淆結構（給分割初稿演算法的規則素材）

> 範圍：成人 B-mode 縱切腎影像中 cortex、medullary pyramids、renal sinus、liver、spleen 的形狀、位置、相對亮度、紋理、正常尺寸，以及易混淆結構與區分方法。重點放在「可從像素量化」的線索。
> 與前作的關係：`腎臟超音波影像判讀入門/basics_normal_anatomy.md`（方位慣例、量測方法、台灣 Su 2019 正常值、pseudotumor）與 `abnormalities_artifacts.md`（cyst/Bosniak、stone、hydronephrosis、artifacts）已涵蓋的內容只摘要引用、不重述，本篇補缺口並轉成可執行的規則。
> 方法限制：本輪約 15 次搜尋/擷取。AIUM/ACR practice parameter 原文、Manley & O'Neill (AJR 2001) 原文、Rha RadioGraphics 2004 renal sinus 全文都沒有讀到。標為「推論」的內容是依引用事實推導出的演算法規則，不是文獻原文。

---

## Q1. 標準縱切影像的形狀與空間關係（腎輪廓、capsule/perirenal fat 亮邊、肝/脾相對位置、螢幕方位）

### Takeaway
縱切時腎臟是長橢圓 / 豆形，外圍有一圈亮邊（capsule 與 perirenal fat 的介面），中央是長橢圓形的亮 sinus。右腎影像中肝臟位於近場（較淺），並往頭側延伸。左腎影像中脾臟位於上極的頭側與外側，面積通常比肝小。radiology 慣例下螢幕左 = 頭側、上 = 近探頭，但實際資料可能被翻轉，所以「肝 / 脾在哪一側」不能只靠螢幕方位判斷。

### Cited Findings
- 腎臟外圍常見亮邊：capsule 是一層薄纖維組織，緊貼脂肪；當腎與鄰近組織的 acoustic impedance 不同時，腎臟常被一圈 bright rim 勾勒出來 — [Faubel et al., CJASN 2014 (PMC3913238)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)
- Renal sinus 在縱切面呈「oval」，橫切面呈圓形；sinus 比 parenchyma 亮 — [Radiopaedia: Renal sinus](https://radiopaedia.org/articles/26397)
- 方位慣例（前作已整理）：螢幕上方 = 靠近探頭；radiology 縱切時 marker 朝頭、顯示於螢幕左，所以螢幕左 = cranial。cardiac 慣例相反 — 見前作 Q1 及 [ultrasound.guide](https://ultrasound.guide/46/ultrasound-image-orientation-and-conventions)、[POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- 掃描窗（前作已整理）：右腎從右 mid-axillary line 第 10–11 肋間經肝掃；左腎從左 posterior axillary line 第 8–10 肋間掃；左 longitudinal 影像中脾位於腎的上方 — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- 台灣 Chang Gung 大型健檢研究採俯臥（prone）、3.5 MHz curvilinear、tissue harmonic imaging — [Su et al., PLoS One 2019 (PMC6837751)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)。俯臥時近場是背部肌肉，不是肝。
- 脾的 flank（後側）掃描評估項目包含「superior pole, relation to kidney」。正常脾門血管位於中央，splenic vein 在 artery 後方 — [articl.net: Splenic ultrasound introduction](https://articl.net/ultrasound/splenic-ultrasound-introduction)（次級來源）

### Inferences（規則化）
- **R1 腎輪廓先驗**：縱切腎 mask 應為單一連通、近似凸的橢圓（長寬比約 2:1，依台灣長 ~10.7 cm、寬 ~4.8–5.1 cm 推算；寬度為橫切量測，縱切面的前後徑通常更小，所以縱切長寬比可能 >2）。外緣應貼齊一圈「比 cortex 亮」的細邊，可用法線方向 profile 上的亮度峰值定位 capsule。
- **R2 sinus 先驗**：sinus mask 應完全落在腎 mask 內、呈與腎長軸大致平行的長橢圓、偏向內側（hilum 側），且不碰到兩極的 capsule。若一個亮區碰到腎外緣並延伸出去，多半是 perirenal fat、腸氣或 hilum 外的脂肪，不屬於 sinus。
- **R3 肝/脾位置**：仰臥 / 側臥經肝掃的右腎影像中，肝佔據腎上方（近場）與一側（頭側）的大片均質區，腎肝之間的界面即 Morison's pouch（hepatorenal recess）。左腎影像中脾通常只出現在上極旁、面積較小的區塊。俯臥掃描時近場通常沒有肝或脾。所以「近場有大片均質實質」不是必要條件，需先依姿勢 / metadata 分流。
- **R4 方位不要寫死**：以「與腎相接的大片實質在哪一側」推出頭側，比讀取螢幕左右更穩健（同前作的推論）。

### Gaps
- 沒有找到權威來源量化「縱切面腎長 / 前後徑比」或 sinus 面積佔比的正常值（見 Q3 Gaps）。
- 沒有讀到 AIUM/ACR practice parameter 原文中對影像方位與必拍切面的規定。
- 沒有找到直接描述 Morison's pouch 在縱切影像上幾何位置的權威引文（上面 R3 屬一般解剖推論）。

---

## Q2. 相對亮度與紋理（cortex vs liver / spleen、spleen vs liver、pyramids vs cortex、sinus vs 全部）

### Takeaway
正常成人的亮度大致為：**renal sinus（最亮）> spleen ≥ liver ≥ renal cortex ≥ medullary pyramids**，cyst / 尿液則接近全黑。這裡的 cortex vs liver 是「isoechoic 或 hypoechoic」，不是一定比較暗，文獻間有分歧。比較成立的前提是肝 / 脾本身正常：脂肪肝會讓肝變亮。脾的紋理被描述為「均質、比 cortex 細緻」。

### Cited Findings
- 腎實質（cortex + medulla）相對正常肝或正常脾為「normally isoechoic (equal in brightness) or hypoechoic (darker)」，且只有肝 / 脾正常時比較才成立；hepatic steatosis 使肝變亮，會讓右腎判讀變難 — [Faubel et al., CJASN 2014 (PMC3913238)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)
- 腎實質比肝亮通常為異常，新生兒除外 — 同上
- 成人 cortex 比肝暗；pyramids 比 cortex 稍暗；sinus fat 與 calyces 比 cortex 亮 — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)（前作已引用）。**與 Faubel 有分歧**：Radiopaedia 寫「暗於肝」，Faubel 寫「等於或暗於肝」。另一篇 nephrology 文獻也指出，傳統觀點認為正常 cortex 比相鄰器官暗，但 grade I（約等於肝）也可見於正常腎 — [African J Nephrology (journals.ac.za)](https://www.journals.ac.za/ajn/article/download/857/229)（只有搜尋摘要）
- Cortex 與 medulla 正常時亮度相近，medulla 可稍暗；也有描述 pyramids 呈 cortex 與 sinus 之間的暗區 — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)。新生兒 cortex 相對較亮、pyramids 較暗，約 4–6 個月大時 cortex 才變得比肝暗 — 同上
- Sinus 含 fibro-fatty tissue，比 parenchyma 亮；尿液與血液 anechoic；急性血塊比 parenchyma 暗，亞急性 / 慢性血塊則偏亮；color Doppler 可區分尿液（無血流）與 sinus 血管 — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)
- Sinus 的主要成分是脂肪，且「increases with age and obesity」；sinus 內 urothelium 也是高回音 — [Radiopaedia: Renal sinus](https://radiopaedia.org/articles/26397)
- 脾 vs 肝：正常脾「homogeneous, slightly hyperechoic to liver; finer than renal cortex」，或與肝等亮；若反過來脾比肝暗，暗示 hepatic steatosis — [articl.net: Splenic US](https://articl.net/ultrasound/splenic-ultrasound-introduction)（次級來源）
- 脾明顯比 renal cortex 亮；拿脾與左腎比較是同時檢查兩器官瀰漫性病變的快速方法 — 同上（經搜尋摘要）
- 腎回音分級研究在脂肪肝時改以脾作為參考：「compared…with echogenicity of the liver or with spleen (in case of fatty liver)」 — [Nepal study (NHRC eLibrary)](https://elibrary.nhrc.gov.np/bitstream/20.500.14356/1306/1/2760-Manuscript-18848-1-10-20201115.pdf)（只有搜尋摘要）
- 可量化的肝 / 腎亮度比（hepatorenal index, HRI）：一項研究的對照組 hepatic/renal brightness ratio 為 1.09 ± 0.13，嚴重脂肪肝組 2.04 ± 0.3，脂肪肝 cutoff ≥1.24（sensitivity 92.7%，specificity 92.5%）；另一項 45 人、以病理對照的研究最佳 cutoff 為 2.01（sens 62.5%，spec 95.2%）；兒童研究 cutoff 1.5 — 經搜尋摘要彙整，來源包含 [UMN experts record](https://experts.umn.edu/en/publications/diagnostic-accuracy-of-hepatorenal-index-in-the-detection-and-gra/)、[PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496)、[Diagnostics 2021;11:1443](https://www.mdpi.com/2075-4418/11/8/1443)（**哪個數值對應哪篇研究未逐一以全文核對**；各研究的機器 / ROI 方式不同）
- HRI 受 ROI 大小與位置影響；隨機放置 ROI 會降低一致性；JPEG/PNG 壓縮會改變強度，建議使用 DICOM — 同上（搜尋摘要）

### Inferences（規則化）
- **R5 亮度排序約束（同一深度帶比較）**：在正常病例中，`mean(sinus) > mean(cortex)`、`mean(pyramid) ≤ mean(cortex)`，而 `mean(liver) / mean(cortex)` 約 ≥1（HRI 對照組 ~1.09 ± 0.13，但這是「肝 / 腎」的比值，且 ROI 方法不同）。
  - 實作：在 cortex 與肝的相鄰帶（同深度 ±1 cm）各取 ROI，計算比值 `r = median(liver) / median(cortex)`。若 `r < ~0.9`，則腎 cortex 比肝亮 → 標示「可能 CKD 型高回音腎、或肝 / 腎分割互換」，交人工確認。
  - 若肝的區塊明顯比脾亮（同時有兩者時），代表可能為脂肪肝，改用脾作為參考（依使用者既有的 fatty-liver 決策）。
- **R6 sinus 偵測**：腎 mask 內「最亮、連通、中央偏內側」的長條區域就是 sinus。可用腎內 intensity 的高分位（例如 >P75–P85）加上形態學閉運算取得；中央若有 anechoic 區且與周邊管狀暗區相連，則為擴張的 pelvis / calyx（前作 Q3），不能把 sinus 的暗洞補成實心。
- **R7 pyramid 偵測**：pyramid = cortex 內側、沿 sinus 周圍規律排列的「較暗三角形」，底朝外、尖朝 sinus。成人 corticomedullary differentiation 常不明顯，所以 pyramid 偵測失敗時應退回「parenchyma = cortex + medulla」單一類別，不要強行分割。
- **R8 紋理**：肝與脾的紋理都較均質；文獻指出脾比 cortex「細緻」。可以 speckle 統計（局部變異係數、GLCM homogeneity）作為輔助特徵，但缺乏量化正常值（見 Gaps）。

### Gaps
- 沒有找到人類成人「腎 cortex / 肝」像素亮度比的正常分佈（只有 HRI 用於脂肪肝的資料，而且 HRI 的 ROI 常取 cortex 或「腎實質」，各研究定義不一）。
- Manley & O'Neill（AJR 2001，常被引用為「部分正常人的 cortex 等於或亮於肝」）原文未取得，無法給出比例。
- 沒有找到脾 / cortex 或脾 / 肝亮度比的人類量化正常值；目前的「脾 ≥ 肝 > cortex」只有質性描述（次級來源）。
- 沒有找到 speckle / 紋理參數（如 GLCM）在正常肝、脾、cortex 之間差異的人類參考值。

---

## Q3. 正常尺寸（長度、cortical / parenchymal thickness、sinus 比例；性別、身高、BMI、左右；亞洲 / 台灣資料）

### Takeaway
成人腎長大多落在 10–12 cm（台灣約 10.6–10.8 cm，印度一小型研究約 9.6 cm）。**「cortical thickness」在不同研究中定義不一致**：只量 cortex（capsule → pyramid base）約 0.9–1.0 cm；量 parenchyma（capsule → sinus 邊緣）約 1.4–2.0 cm。台灣 Su 2019 的「cortical thickness」約 1.46–1.49 cm，數值上更接近 parenchyma。尺寸與體重相關最強，與身高和 BMI 弱相關，左腎通常略大。

### Cited Findings
**長度與厚度（依研究）**

| 研究 | 族群 / n / 年齡 | 機器 / 探頭 | 定義 | 數值 (mean ± SD) |
|---|---|---|---|---|
| [Su et al., PLoS One 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)（前作已詳列） | 台灣 Chang Gung 健檢，n = 3,707 | 3.5 MHz curvilinear、THI、俯臥 | "cortical thickness" = cortex–perirenal fat 介面到 cortex–pyramid base 的最大垂直距離 | 長：右 10.62 ± 0.69、左 10.76 ± 0.70 cm；"cortical"：右 1.46 ± 0.32、左 1.49 ± 0.30 cm |
| [El-Reshaid & Abdul-Fattah, Med Princ Pract 2014 (PMC5586921)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5586921/) | 科威特，n = 252（男 111、女 141），18–80 歲 | GE LOGIQ C8（未註明探頭） | cortex = cortex 外緣 → pyramid 外緣 | 長：右 男 10.8 ± 0.9 / 女 10.5 ± 1.1，左 男 10.9 ± 0.8 / 女 11.2 ± 0.9 cm；cortex：右 0.98、左 1.02 cm（範圍 0.60–1.61；女性 SD 0.8/0.6 疑為誤植） |
| 伊朗研究（搜尋摘要） | n = 142，20–50 歲 | 未知 | medulla 外緣 → capsule | cortex 9.09 ± 0.99 mm；與性別相關，左右無差 — [KUMS PDF](https://www.kums.ac.ir/kums_content/media/image/2021/04/156002_orig.pdf)（**來源歸屬未以全文確認**） |
| 奈及利亞 Enugu（搜尋摘要） | n = 310 | 未知 | parenchyma = cortex 外緣 → sinus echoes 外緣，量三處取平均 | 右 1.85 ± 0.20、左 1.95 ± 0.19 cm — [AJOL Afr Health Sci](https://www.ajol.info/index.php/ahs/article/view/107255) |
| [Cureus 2023 (PMC10361447)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10361447/) | 印度 Ranchi，60 人 / 123 腎，21–72 歲 | Toshiba Power Vision 6000，3.5 MHz convex | 未清楚定義 | 長 9.63 ± 0.64 cm；parenchyma 2.05 ± 0.1 cm；左 98.5–103.6 mm、右 94.5–98.7 mm |
| 巴基斯坦 Aga Khan（前作） | n = 4,035 | 未知 | parenchyma = 腎外緣 → sinus，橫切 | 右腎長 101.6 ± 8.9 mm；parenchyma 14.4 ± 2.9 mm — [Aga Khan](https://scholars.aku.edu/en/publications/sonographic-measurement-of-renal-dimensions-in-adults-and-its-cor/) |
| 499 名志願者，18–80 歲（搜尋摘要，國別不明） | — | — | "cortical thickness" | 右：男 13.68 ± 2.47 mm、女 12.63 ± 1.91 mm — [搜尋結果 PMC6029337/PMC4209654，未核對](https://pmc.ncbi.nlm.nih.gov/articles/PMC4209654) |

- 綜述值：cortex 約 1 cm、整體 parenchyma 約 1.5 cm；健康對照 parenchyma 13.6 mm、AKI 13.8 mm、CKD 10.7 mm；量測依技術而異，因為 cortex 在兩極或 column of Bertin 處會看起來較厚 — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)
- Radiopaedia：cortex ≥ 6 mm；pyramid 不清楚時用 parenchyma 15–20 mm — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- 長度：正常約 11 cm（10–12）；左比右長約 0.3 cm；女性比男性小約 0.5 cm，以身高校正後性別差異消失；60 歲以下 <10 cm 少見；右腎中位長由 30 歲約 11.1 cm 降到 70 歲約 10.4 cm；與前次相差 >1 cm 不太可能只是觀察者間差異 — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)

**影響因子（研究間有分歧）**
- 科威特：長度與體重相關（r = 0.57，60–120 kg 間每 10 kg 增加約 0.23 cm）；與身高無關（r = 0.23，p = 0.46）；cortex 厚度與體重、BMI 都無關；>60 歲的長度與 cortex 無顯著下降（cortex 0.89 vs 0.96 cm，p = 0.23） — [PMC5586921](https://pmc.ncbi.nlm.nih.gov/articles/PMC5586921/)
- 台灣：與右腎長的相關為體重 r = 0.422、身高 0.363、BMI 0.300、年齡 −0.155；cortical thickness 隨年齡線性下降 — [Su 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)。**與科威特在身高與年齡效應上互相矛盾**（科威特 >60 歲只有 n = 13）。
- 印度：長度與身高 r = 0.19、體重 0.31–0.32、BMI 0.20–0.23、BSA 0.32–0.33；迴歸式 LL(cm) = 0.03×W + 6.95 + 1.02×H(m)、RL(cm) = 0.04×W + 6.45 + 1.12×H(m)；parenchyma 左右有顯著差異 — [PMC10361447](https://pmc.ncbi.nlm.nih.gov/articles/PMC10361447/)（文內數字有自相矛盾處，品質偏低）

**Sinus 比例**
- Sinus 脂肪隨年齡與肥胖增加 — [Radiopaedia: Renal sinus](https://radiopaedia.org/articles/26397)；一項 CT 立體學研究（240 名 21–80 歲成人）顯示 sinus 脂肪體積與年齡正相關，70 歲後似乎下降 — [Folia Morphologica (viamedica)](https://journals.viamedica.pl/folia_morphologica/article/download/FM.2014.0016/27424)（搜尋摘要）
- 越南研究（2004，n = 878）：parenchyma 與 parenchyma / 腎腔比值隨年齡變化，與年齡呈負相關，以最高齡組變化最明顯 — [BVS record wpr-4781](https://search.bvsalud.org/gim/resource/en/wpr-4781)（只有摘要，無數值）

### Inferences（規則化）
- **R9 長度合理性檢查**（以 px/mm 換算）：腎 mask 長軸 7–14 cm 視為合理；<8 cm 或 >13.5 cm 時標記為需確認（可能是斜切、切到部分腎、腎萎縮，或誤把肝 / 脾納入）。台灣成人可用 10.7 ± 0.7 cm 作為先驗中心。
- **R10 厚度合理性檢查**：parenchyma（腎外緣 → sinus 邊緣，沿法線）若中段 <8–10 mm 或 >25 mm，標記為可疑；cortex-only（外緣 → pyramid base）約 6–15 mm。兩極會偏厚，不要在兩極套用同一門檻。
- **R11 sinus 面積比例**：沒有找到正常值，不建議設硬門檻；但 sinus 會隨年齡與肥胖變大，所以年長或肥胖者的 sinus / 腎面積比偏高屬可預期，不應判為錯誤。
- 本專案若要報「cortical thickness」，必須寫出定義；建議同時輸出 parenchyma 與 cortex-only 兩種量測。

### Gaps
- 沒有找到 parenchyma / sinus 或 sinus / 全腎面積比的正常參考值（CNKI 或 J-STAGE 可能有，本輪未搜）。
- 沒有台灣或東亞以「cortex-only」定義量測的正常值；Su 2019 的定義與其他文獻不可直接比較。
- Emamian 1993（丹麥 665 人）原文數值仍未取得。
- 499 人研究與伊朗研究的來源歸屬只看到搜尋摘要，未核對全文。

---

## Q4. 易混淆結構與區分方式

### Takeaway
最常出問題的分割錯誤可分三類：
1. **把腎外結構納入腎**：肝 / 脾的邊緣、腸道形成的 pseudokidney、adrenal 或 diaphragmatic crus 接在上極、psoas。
2. **把腎內結構排除或誤分**：column of Bertin、dromedary hump、fetal lobulation、sinus lipomatosis、sinus cyst 或 hydronephrosis 造成 sinus 中空。
3. **由 artifact 造成的亮度假象**：rib 或腸氣的陰影、cyst 後方增強、stone 的陰影、mirror image。

可量化的區分線索主要是：「與 cortex 是否同亮且連續」「是否有後方陰影或增強」「是否位於腎輪廓外」「是否為管狀並有血流」。

### Cited Findings
**腸道 / pseudokidney**
- 增厚的大腸壁（暗）包著中央腸氣（亮）會形成看起來像腎的結構（pseudokidney）；若在一位病人身上「找到三個腎」，要懷疑其中一個是 pseudokidney，應掃完整腹部找到真正的腎 — [123sonography: common mistakes kidney](https://123sonography.com/blog/common-mistakes-kidney)（教學部落格，低權威）
- 單側腎缺如時，colon carcinoma 可能成為 pseudokidney；新生兒中增大的 adrenal 可能被誤認為發育不全的腎；高位異位卵巢也可能類似發育不全的腎 — [Radiol Bras review (PMC4603221)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4603221)
- US 偵測失敗的常見原因包括高 BMI、腸氣阻擋、腫瘤小或 isoechoic；應掃完整的 parenchyma、perinephric space 與 sinus，color Doppler 可以輔助 — [Leão et al., Radiol Bras 2019 (SciELO)](https://www.scielo.br/j/rb/a/thWmZQ7SvskvRfWH7SyS9LP/?lang=en)

**Adrenal / diaphragmatic crus / psoas**
- 兒童研究（1987）：adrenal 呈帽狀並與上極同亮，因此常難以甚至無法與上極分開；adrenal 在 71% 檢查中與腎同亮、29% 較暗，從不比腎亮 — [Ultraschall Med 1987;8(6):271–277](https://www.thieme-connect.com/products/ejournals/pdf/10.1055/s-2007-1011711.pdf)（**舊研究、兒童**）
- 18 例空腎窩病童中，3 例的 adrenal 與 diaphragmatic crus 融合呈三角形；crus 與 adrenal 的超音波特徵不同，仔細看可避免此陷阱 — [PubMed 28688135](https://www.ncbi.nlm.nih.gov/pubmed/28688135)（兒童，搜尋摘要）
- 屍體研究：右 adrenal 85% 位於右 crus 上、15% 跨 crus 與 psoas；左 adrenal 40% 位於左 crus 上、60% 跨 crus 與 psoas — [PubMed 33071051](https://pubmed.ncbi.nlm.nih.gov/33071051/)
- 正常 adrenal 是小的低回音結構，位於腎的上內側、crus 前方；成人因體積小加上腸氣，常規不易看見，左側因沒有肝窗更難看到 — [articl.net adrenal US](https://articl.net/resource/adrenal-gland-ultrasound)（低權威）；EFSUMB 教材 — [EFSUMB ECB Adrenal](https://efsumb.org/wp-content/uploads/2023/07/ECB2nd_-Adrenal_FULL.pdf)（未讀全文）

**脾周圍的混淆**
- 常見誤判包括：把肝左葉當成脾的碎片；把充滿胃內容物的胰尾或腸圈當成脾門腫塊或積液；splenic flexure 腫瘤、左腎病灶、左 adrenal 病灶被當成脾病變 — [Walczyk & Walas, J Ultrasonogr 2013，經 articl.net 轉述](https://articl.net/ultrasound/splenic-ultrasound-introduction)
- Accessory spleen：脾門附近的圓形 isoechoic 結節，約 10–30%；Gamna-Gandy bodies 為微小亮點並帶陰影；腸氣與肋骨會遮蔽脾 — [articl.net](https://articl.net/ultrasound/splenic-ultrasound-introduction)（次級來源）
- 兒童正常脾可見低回音帶（未打顯影劑時 5%），可能類似腫塊 — [Kuint et al., AJR 2016，經 articl.net](https://articl.net/ultrasound/splenic-ultrasound-introduction)

**Sinus 內的混淆**
- 小的腎結石不易與亮的 sinus 分開；降低 TGC / gain 有助於顯示結石的後方陰影；sinus 與 medulla 交界的鈣化可能是鈣化的腎動脈分支而非結石 — [Radiopaedia: Renal sinus](https://radiopaedia.org/articles/26397)
- Color Doppler 可區分尿液（無血流）與 sinus 血管；sinus 內急性血塊為低回音、慢性血塊為高回音 — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)
- Sinus lipomatosis：sinus 脂肪過量取代，常伴隨老化、實質萎縮、發炎或結石 — [ESR EPOS poster C-2802](https://epos.myesr.org/poster/esr/ecr2018/C-2802/findings%20and%20procedure%20details)；**沒有找到描述其超音波外觀的權威來源**
- Sinus cyst（parapelvic / peripelvic）造成 pseudohydronephrosis、extrarenal pelvis（約 10%）、膀胱脹滿造成雙側 pelvicalyceal prominence — 前作 Q3 已整理（[Radiopaedia parapelvic cyst](https://radiopaedia.org/articles/parapelvic-cyst)、[extrarenal pelvis](https://radiopaedia.org/articles/extrarenal-pelvis)）

**腎實質變異（pseudotumor）**
- Column of Bertin 可像一個伸入 sinus 的實心腫塊；疤痕旁的正常組織可被誤讀為腫塊；CT / MRI 上其衰減與強化與 cortex 相同 — [Radiol Bras (rb.org.br 3180)](https://rb.org.br/details/3180/en-US)
- Column of Bertin、dromedary hump、fetal lobulation、junctional parenchymal defect：與 cortex 同亮、連續、輪廓平滑；scar 位於 pyramid 正上方，fetal lobulation 位於 pyramids 之間 — 前作 Q7 已整理（[Radiopaedia HCB](https://radiopaedia.org/articles/hypertrophied-column-of-bertin)、[UW PDF](https://radiology.wisc.edu/wp-content/uploads/2025/01/UW-Radiology-Summit-Non-neoplastic-renal-path-final.pdf)）
- 兒童明顯的 pyramids 可能被誤認為擴張的 calyces 或 cyst — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)

**Artifacts**（前作 Q5 已整理機制）
- 陰影（stone、肋骨、腸氣）、後方增強（cyst）、slice-thickness 讓 cyst 內出現假回音、side lobe、橫膈的 mirror image — [abnormalities_artifacts.md Q5](https://radiopaedia.org/articles/31989) 及其引文

### Inferences（規則化；文獻沒有直接給出門檻）
- **R12 腸道 pseudokidney / 腸氣**：亮的中心伴隨下方「髒」陰影（內部有雜訊、邊界模糊、隨時間變化），外圍包著低回音環，且不和肝 / 脾形成平滑界面 → 判為腸。真正的 sinus 下方不應出現連續陰影帶。
- **R13 肋骨陰影**：從近場延伸到畫面底部、邊界銳利的垂直暗帶，寬約一根肋骨，常成對週期出現。落在腎內的那段應標為「被遮蔽」而不是腎外，保持輪廓的形狀先驗插值（凸包或橢圓擬合）。
- **R14 stone**：腎內局部極亮點（接近畫面最大值）伴隨下方乾淨的暗帶 → 屬 stone，不併入 sinus 的平滑區；陰影帶需從 cortex ROI 剔除。
- **R15 cyst / 擴張的 pelvis**：腎內近 0 的區域 —— 圓形、伴後方增強 → cyst（從 parenchyma mask 挖除，並排除增強帶）；分支或管狀並連到 hilum → hydronephrosis（屬 sinus / collecting system，不是 cortex）。
- **R16 上極的 adrenal / crus**：接在上極內側、與腎相近或較暗、呈三角或 Y / V 形的小結構，或位於後方的條狀低回音 → 不併入腎。可用凸性約束切掉：腎輪廓上極應是平滑弧線，突出的尖角應被修掉。
- **R17 psoas**：腎深處（遠場）內側、沿長軸走向、呈條紋狀的低回音肌肉 → 排除。肌肉的纖維紋理（平行條紋）可與腎實質的均質 speckle 區分。
- **R18 pseudotumor 保留規則**：腎輪廓內的團塊若與鄰近 cortex 亮度差在雜訊範圍內、與 cortex 連續、內含 pyramid → 視為 parenchyma，保留在腎 mask 內。
- **R19 脾門 / 肝的大片實質**：與腎相鄰但亮度明顯較高（>cortex），且延伸到畫面邊緣的區域 → 肝或脾，不併入腎；邊界取兩者之間的亮線或暗線（perirenal fat 或 Morison's pouch 的界面）。

### Gaps
- 沒有找到成人 psoas、diaphragm / crus 在腎縱切面上被誤認的權威描述或量化資料；adrenal 的資料主要來自兒童與舊研究。
- Gallbladder 在右腎縱切中的位置與區分方式（anechoic、梨形、後方增強、位於肝下緣，而非腎輪廓內）本輪沒有找到引文；這是一般解剖知識，需以教科書確認。
- 脾 / 肝血管（splenic vein、hepatic / portal vein）被誤認為 hydronephrosis 或 cyst 的直接引文沒有取得；除 Faubel 的 Doppler 說法外沒有額外證據。
- Sinus lipomatosis 的超音波外觀（例如 sinus 擴大、亮度不均、實質變薄）沒有權威來源。

---

## Q5. 哪些線索可靠、哪些依操作者 / gain 而變

### Takeaway
**相對**關係（同畫面、同深度的器官對比、亮度排序、形狀與拓撲）比**絕對**灰階值可靠。絕對亮度、結石大小、陰影可見度都受 gain、TGC、深度、探頭頻率、harmonic、壓縮格式影響。尺寸量測在操作者之間的差異約為公分以下，但斜切會造成系統性低估。

### Cited Findings
- 腎 / 肝比較只有在肝與脾正常時才有效；脂肪肝使肝變亮 — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)
- 回音比較需要考量周邊器官可能同時有病變；不應完全依賴回音比較來判斷是否正常 — [open-exam-prep spleen guide](https://open-exam-prep.com/study-guides/arrt-sonography/abd-biliary-pancreas-spleen/spleen)（低權威）
- HRI 受主觀判讀、ROI 大小與位置影響；JPEG/PNG 壓縮改變強度 — HRI 搜尋彙整（見 Q2 來源）
- 降低 TGC / gain 有助顯示結石陰影，代表陰影的可見度依設定而變 — [Radiopaedia: Renal sinus](https://radiopaedia.org/articles/26397)；gain 與深度會放大結石尺寸 — [PMC5031098](https://pmc.ncbi.nlm.nih.gov/articles/PMC5031098)（前作）
- 長度受技術與觀察者間差異影響，但比厚度穩定；兩極或 column of Bertin 處 cortex 看起來較厚 — [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)
- 台灣 48 位操作者的右腎長 ANOVA 無顯著差異（p = 0.3451）— [Su 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)；單次 US 長度比 CT 短 1.5 ± 5.6 mm — [Larson AJR 2011 PubMed 21512050](https://pubmed.ncbi.nlm.nih.gov/21512050)（前作）
- Echogenicity 本身無法可靠區分 AKI 與 CKD（腎比肝暗：AKI 30% vs CKD 11%）— [Faubel 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3913238)

### Inferences（可靠度分級，供規則權重參考）
| 線索 | 可靠度 | 理由 |
|---|---|---|
| 腎輪廓為單一平滑橢圓、sinus 在內 | 高 | 解剖拓撲，不受 gain 影響 |
| sinus 為腎內最亮區 | 高 | 文獻一致；例外為 sinus 被 cyst / 擴張 pelvis 取代 |
| pyramid 比 cortex 暗 | 中 | 成人常不明顯，受探頭頻率與體型影響 |
| cortex ≤ 肝 / 脾（同深度比） | 中 | 文獻對「等亮或稍暗」有分歧；脂肪肝、CKD 時會反轉 |
| 脾 ≥ 肝 | 低到中 | 次級來源；脂肪肝時反轉 |
| 絕對灰階門檻 | 低 | gain、TGC、harmonic、壓縮都會改變 |
| 長度 7–14 cm 合理範圍 | 高（作為合理性檢查） | 多族群資料一致 |
| 厚度數值 | 中到低 | 定義不一、兩極偏厚、量測位置敏感 |
| 陰影 / 增強帶 | 中 | 形態穩定，但可見度依 gain 與聚焦位置而變 |

- 實作建議：以每張影像自身的分位數做亮度正規化（例如以肝 / 脾 ROI 的中位數作為 1.0），所有規則都用比值而不是 0–255 的絕對值；並記錄 gain、depth、頻率等 DICOM 標籤，作為後續分層驗證的依據。

### Gaps
- 沒有找到量化研究直接測量 gain / TGC 改變對 cortex / 肝比值的影響幅度。
- 沒有找到 AIUM/ACR practice parameter 對「應比較腎與肝 / 脾回音」的原文規定（搜尋未取回）。
