# 腎臟超音波影像判讀入門：基本方位與正常解剖 (Basics & Normal Sonographic Kidney Anatomy)

> 對象：沒有醫學背景的資訊工程學生。技術名詞保留英文。
> 每一筆 Cited Finding 均附來源 URL；沒有找到可靠來源的內容放在 Gaps 或 Inferences（標明為推論）。
> 研究限制：本輪約 15 次搜尋/擷取；Radiopaedia 的部分文章（protocol、echogenicity、hypertrophied column of Bertin 之外的 variant 文章）有 404 或未擷取；ultrasound.guide 憑證過期無法讀取全文；AIUM/ACR practice parameter 全文未讀到。

---

## Q1. 螢幕方位慣例 (Screen orientation conventions)：上下左右代表什麼？Probe marker？Radiology vs cardiac/POCUS 差異

### Takeaway
影像「上方」永遠是最靠近探頭表面（皮膚）的組織，「下方」是較深處；radiology/abdominal 慣例下，probe marker 那一側顯示在螢幕左邊——縱切 (sagittal/longitudinal) 時 marker 朝頭，所以螢幕左 = 頭側 (cranial)、右 = 腳側 (caudal)；橫切 (transverse) 時螢幕左 = 病人右側（如同看 CT，從腳往頭看）。Cardiac (echocardiography) 慣例則把 marker 顯示在螢幕右邊，兩者混用時會左右相反。各來源對 transverse 時 marker 該朝哪邊有不一致的描述，需依單位規範。

### Cited Findings
- 螢幕最上方是最靠近探頭面的結構，越往下越深 — [ultrasound.guide (via search snippet)](https://ultrasound.guide/46/ultrasound-image-orientation-and-conventions)
- Radiology/general 慣例：probe 上的 marker 那一側顯示在螢幕左方；作者強調這「只是慣例」，abdominal 與 cardiac 兩套慣例各自內部一致，但兩個世界碰在一起時會出問題 — [ultrasound.guide](https://ultrasound.guide/46/ultrasound-image-orientation-and-conventions)
- 一個教學影片說 transverse 平面 marker 朝病人左側；轉 90° 讓 marker 朝頭即為 sagittal — [UVM ultrasound series](https://www.uvm.edu/~rchawla/series_home/ultrasound/ada_files/ada_media71.html)；但另一來源說 transverse 時 indicator 通常朝病人右側 — [CanadiEM PoCUS Previews 02](https://canadiem.org/pocus-previews-02-intro-to-image-generation)（**兩者矛盾**，見 Inferences）
- Cardiac 是另一套獨立慣例（workshop 講義列「probe indicator toward patient's right or head」）— [Loyola POCUS cardiac lab PDF](https://www.meddean.luc.edu/lumen/meded/vc/point_of_care_ultrasound_vc/2024-2025%20labs/pcm2%20cardiac%20us%202024-2025%20student%20version.pdf)
- Transducer marker orientation 教學頁 — [SonoSite Institute](https://www.sonositeinstitute.com/course-lessons/instrumentation-section-3-chapter-3-lesson-5-transducer-marker-orientation)
- POCUS 101 腎臟流程：右腎與左腎 longitudinal 時 indicator 都朝病人頭側；transverse 由 longitudinal 逆時針轉 90°（右腎 indicator 因此朝 posterior，左腎朝 anterior）— [POCUS 101 Renal Ultrasound](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)

### Inferences
- 對 CS 學生的簡化模型：超音波影像是一個 2D 扇形切面 (sector)，原點在螢幕上方中央（探頭）；y 軸 = 深度 (depth / time-of-flight)，x 軸 = 沿探頭陣列的側向位置。「marker 在螢幕左」= 一個固定的左右鏡像約定。
- 「transverse 時 marker 朝病人右」才會讓螢幕左 = 病人右（與 CT 相同的 radiological convention）；說「朝病人左」的來源可能是 cardiac/其他約定或描述錯誤——標記為**無共識/需依單位規範**。
- 腎臟側臥/冠狀 (coronal, flank) 掃描時，螢幕左仍是頭側；但上方變成「外側/後側皮膚」而非前腹壁，所以「上 = anterior」在腎超並不一定成立，要以探頭位置推回。
- 對資料集 (dataset) 而言：不同機器/操作者可能把影像左右翻轉；若要訓練模型辨識左右腎，不能只依賴影像方位，應依賴相鄰器官（liver vs spleen）或 DICOM metadata/標註文字。

### Gaps
- 未讀到 ACR–AIUM–SPR–SRU practice parameter 原文中對方位標記的確切規定 (https://www.acr.org/-/media/ACR/Files/Practice-Parameters/US-Abd-Retro.pdf)。
- ultrasound.guide 全文因 SSL 憑證過期無法擷取，僅有搜尋摘要。Cardiac 慣例（marker 顯示於螢幕右側）未找到可直接引用的 ASE 原文。

---

## Q2. 探頭位置 / acoustic windows；如何判斷左右腎；如何分辨 long-axis vs short-axis

### Takeaway
右腎透過肝臟 (liver as acoustic window) 從右側 mid-axillary line 約第 10–11 肋間掃；左腎位置較高、較後，從左側 posterior axillary line 約第 8–10 肋間、經脾臟掃。影像上「腎旁是肝 → 右腎；腎上方是脾 → 左腎」。縱切 (long axis) 呈橢圓/豆形，中央有高回音的 renal sinus；橫切 (short axis) 呈圓形或在 hilum 層面呈 "C" 形開口朝內側。

### Cited Findings
- 探頭：curvilinear 或 phased array；Abdominal/Renal preset；病人仰臥 (supine)，困難時可坐起由背側掃或側臥 (lateral decubitus) — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- 右腎 longitudinal：右 mid-axillary line，約第 10–11 肋間；逆時針轉 10–20° 可順著肋間避開肋骨 — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- 左腎 longitudinal：左 posterior axillary line，約第 8–10 肋間，「操作者的指節要碰到床」才夠後面；請病人吸氣可帶下腎臟 — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- 右 longitudinal 影像可見肝臟；左 longitudinal 可見脾臟位於腎上方 — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- 腎臟位於後腹腔 (retroperitoneal)、脊椎兩側約 T12–L3；右腎因肝臟而位置稍低 — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)；[Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- Transverse 由 longitudinal 置中後轉 90°，再上下 tilt 掃完整個腎臟；transverse 中可辨識 cortex、medullary pyramid、renal pelvis — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- 台灣 Chang Gung 大型研究採俯臥 (prone) 姿勢、3.5 MHz curvilinear、tissue harmonic imaging — [Su et al., PLoS One 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)

### Inferences
- 判斷左右的特徵優先順序（給 CV 模型/學生）：(1) 相鄰實質器官——肝（較大、均質、常佔畫面大片）vs 脾（較小、在左腎上極上方）；(2) 影像上標註文字 (RT/LT/"R KID")；(3) 方位慣例（不可靠）。
- 縱切 vs 橫切形狀特徵：縱切 = 長橢圓（長寬比約 2:1 以上，依台灣資料長 ~10.7 cm、寬 ~4.8–5.1 cm）且中央有一條長形高回音 sinus 帶；橫切 = 近圓形，在 hilum 層面 sinus 從內側開口呈 "C" 或馬蹄形，上下極層面則是實心圓/橢圓（無 sinus）。此描述基於一般解剖推論，未找到逐字對應的權威來源。

### Gaps
- 未取得 Radiopaedia 腎臟超音波 protocol 頁（URL 404）；Core Ultrasound、SonoWorld 圖像頁未擷取。
- 未找到專門描述「transverse 圖呈 C-shape」的權威引文。

---

## Q3. 如何取得真正最大長軸 (maximal bipolar length) 與量測方式；斜切 (oblique) 低估

### Takeaway
長度 = 在 longitudinal 影像上用 electronic caliper 量上極到下極的最長距離；操作者需前後 fan/tilt 並旋轉，找出兩極都清楚且長度最大的切面。超音波平均比 CT 略短（數 mm 等級），單次量測誤差大，取多次量測最大值可降低變異。

### Cited Findings
- 台灣研究定義：在 longitudinal scan 標記上、下極，以 electronic caliper 量最長 pole-to-pole 距離；寬度 = transverse scan 於 hilum 的最大橫徑 — [Su et al. 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)
- Radiopaedia：adult kidney 平均 pole-to-pole length 10–13 cm — [Radiopaedia: Normal kidney size in adults](https://radiopaedia.org/articles/normal-kidneys-size-in-adults)
- POCUS 101 建議在 longitudinal view 緩慢向前/後 fan 以評估整個腎臟（未給專門「找最長軸」技巧）— [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- Larson et al. (AJR 2011)，76 人 US vs CT：單次 US 量測平均比 CT 短 1.5 ± 5.6 mm (95% 範圍 −12.5 至 +9.5 mm)；取三次 US 量測的最大值 SD 降至 4.7 mm — [PubMed 21512050](https://pubmed.ncbi.nlm.nih.gov/21512050)
- 腎捐贈者研究 (n=139)：相對於摘除後直接量測，US 誤差約 −1.1 cm，CT 約 −0.7 cm，CT 較準 — [Noninvasive and direct measures of kidney size in kidney donors](https://cuk.elsevierpure.com/en/publications/noninvasive-and-direct-measures-of-kidney-size-in-kidney-donors/)
- 2016 年 33 名成人研究（vs MR reconstruction）：lateral decubitus 姿勢量得長度與真實長度相關最好；建議在所有可行姿勢中取最大縱長 — [INIS/IAEA record](https://inis.iaea.org/records/ptet4-3md02)
- CKD 病人中 US 長度與 MRI 相當（2019）— [Acta Radiologica 2019 (doi 10.1177/0284185119847680)](https://https-sage-cnpereading-com-443.webvpn1.xju.edu.cn/doi/10.1177/0284185119847680)（**與捐贈者研究結論不完全一致**）
- 手動量測存在 intra-/inter-rater variability，已有自動化量測研究 — [SPIE (Hu et al.)](https://journals.spiedigitallibrary.org/profile/Ricky.Hu-4357532)

### Inferences
- 幾何直覺：若切面與真正長軸夾角 θ，量到的長度約 L·cosθ（並且若切面偏離中心，會切到腎的「弦」而非直徑）；因此誤差幾乎永遠是**低估**，故臨床習慣是「多次量測取最大值」。
- 「真正最大長軸」影像的判準（可作為標註規則）：上下兩極的 capsule 都銳利可見、中央 sinus 呈連續長條且大致與長軸平行、腎輪廓呈對稱豆形；若一極模糊或 sinus 偏一側，多半是 oblique/off-center。
- 腎臟長軸本身相對身體是斜的（上極較內、較後），所以「縱切」實際上常是 coronal-oblique，需旋轉探頭對齊——此為一般解剖知識推論。

### Gaps
- 未找到量化「oblique 角度 vs 低估多少」的權威數據；未讀到 AIUM/ACR 文件對長度量測的明確規定。

---

## Q4. Echogenicity 術語與灰階影像的工程解釋

### Takeaway
Echogenicity 是「相對」概念：anechoic = 無回音（全黑，例如尿液/單純囊腫）；hypoechoic = 比參考組織暗；isoechoic = 與參考組織同亮度；hyperechoic (echogenic) = 比參考組織亮（例如 sinus fat、結石）。灰階亮度 ≈ 回波振幅經 time-gain compensation 與 log compression 後映射到 0–255。

### Cited Findings
- 成人腎臟：cortex 比肝臟暗 (less echogenic)；medullary pyramids 比 cortex 稍暗；中央 sinus fat 與 calyces 比 cortex 亮；renal pelvis 可呈 hilum 處中央 anechoic 裂隙 — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- 新生兒 cortex 回音與肝臟相等（早產兒甚至更亮），作者歸因於 cortex 內大量組織介面 — [Hricak et al., Radiology 1983 "Neonatal kidneys: sonographic anatomic correlation"](https://pubs.rsna.org/doi/10.1148/radiology.147.3.6844606)；[Thieme review](https://www.thieme-connect.de/products/ejournals/html/10.1055/s-0042-1757117)
- Hypertrophied column of Bertin 與周圍實質 isoechoic — [Radiopaedia: Hypertrophied column of Bertin](https://radiopaedia.org/articles/hypertrophied-column-of-bertin)

### Inferences（工程解釋，未有單一引用來源，屬一般超音波物理知識）
- 回波來自聲阻抗 (acoustic impedance Z = ρc) 不連續處的反射，反射係數 R = ((Z2−Z1)/(Z2+Z1))²；脂肪與周圍組織介面多 → sinus fat 亮；均勻液體內部無介面 → anechoic（黑）且後方因衰減少而出現 posterior acoustic enhancement。
- 原始 RF 訊號 → envelope detection → TGC（補償深度衰減）→ log compression（把 ~60–100 dB 動態範圍壓到 8-bit 灰階）→ scan conversion（極座標轉直角座標）。因此像素值不是物理量的線性表示，且受 gain、dynamic range、harmonic imaging 等設定影響；比較 echogenicity 時應在同一畫面、同一深度比較（例如 cortex vs 相鄰肝臟）。
- Speckle 是次解析度散射體干涉造成的顆粒紋理，不代表實際組織構造。

### Gaps
- Radiopaedia "echogenicity" 文章 URL 404，未擷取到權威術語定義頁；建議補引超音波物理教科書（如 Hedrick, Kremkau）。

---

## Q5. 正常外觀：cortex / medulla / sinus / pelvis；如何定義 cortex 邊界；"cortex" vs "parenchyma"

### Takeaway
由外而內：高回音細線 capsule → 中等回音 cortex → 較暗的三角形 medullary pyramids（底朝外、尖朝 sinus）→ 高回音的 renal sinus（脂肪、血管、collecting system）→ 中央可能有 anechoic 的 renal pelvis。Parenchyma = cortex + medulla（即 sinus 以外的腎組織）；文獻中 "cortical thickness" 的定義不一致，有時其實量的是 parenchyma。

### Cited Findings
- Medulla 含 10–14 個 pyramids，被 renal columns（cortex 向內延伸）分隔；每個 lobe = 一個 pyramid + 覆蓋 cortex + 相鄰 columns；papilla 引流到 minor calyx，4–5 個 minor → major calyx，2–3 個 major → renal pelvis — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- Renal sinus 內含 renal pelvis、calyces、血管、神經、淋巴、脂肪 — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- 正常 cortical thickness ≥ 6 mm；若 pyramids 難以分辨，改用 parenchymal thickness 15–20 mm — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- 台灣研究的 "cortical thickness" 定義 = longitudinal image 上從 cortex–perirenal fat 介面到 cortex–pyramid base 介面的最大垂直距離；平均約 1.46–1.49 cm — [Su et al. 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)
- 巴基斯坦 4,035 名成人：parenchymal thickness 14.4 ± 2.9 mm（右腎）— [Aga Khan University: Sonographic measurement of renal dimensions in adults](https://scholars.aku.edu/en/publications/sonographic-measurement-of-renal-dimensions-in-adults-and-its-cor/)
- 正常 ureter 通常看不到 — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)

### Inferences
- **定義衝突（重要）**：Radiopaedia 的 cortical thickness ≥ 6 mm（capsule 到 pyramid base）與台灣研究「cortical thickness」~14.6 mm 數值相差兩倍以上；台灣數值大小更接近其他文獻的 parenchymal thickness (15–20 mm)。推測不同研究對 pyramid base 的辨識或量測方向不同。標註資料時必須明確寫出量測定義：
  - Cortical thickness：capsule → pyramid base（arcuate 血管所在處）。
  - Parenchymal thickness：capsule → renal sinus 邊緣（sinus fat 起點），包含 pyramid。
- 「Cortex 邊界」做 segmentation 時：外界 = capsule/perirenal fat 的高回音邊；內界 = 若要 parenchyma，則為 sinus fat 的高回音邊；若要 cortex，則需繞過每個低回音 pyramid，並包含伸入 sinus 之間的 columns of Bertin。
- Corticomedullary differentiation（cortex 與 pyramids 的亮度差）在成人可能不明顯（尤其 harmonic/低頻探頭或肥胖病人），在兒童較明顯。

### Gaps
- 未取得 Rumack / Requisites 教科書原文；未找到權威來源系統性比較 cortex vs parenchyma 定義的文獻。

---

## Q6. 正常值：成人長度、厚度、左右差、年齡、性別/身高/BMI；兒童；台灣/亞洲資料

### Takeaway
成人腎長約 10–13 cm（男 10–14、女 9–13）；台灣健檢族群平均右 10.62 cm、左 10.76 cm，左大於右、男大於女，長度與體重/身高/BMI 正相關，與年齡呈倒 U 形（約 40 歲左右最大後下降）。左右差 > 2 cm 視為異常。兒童需用 age/height-based nomograms，新生兒 cortex 較亮、pyramids 明顯。

### Cited Findings
**成人**
- 長 10–14 cm（男）、9–13 cm（女）；寬 3–5 cm；前後厚 ~3 cm；重 150–260 g；兩腎長度差 > 2 cm 視為異常；左腎通常稍大 — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- 平均 pole-to-pole 10–13 cm；大小與身高密切相關，體重、BMI、年齡、種族亦影響；單側功能喪失時對側可代償性增大 — [Radiopaedia: Normal kidney size in adults](https://radiopaedia.org/articles/normal-kidneys-size-in-adults)
- 以 ellipsoid 公式估體積約低估 10–25% — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- POCUS 101：成人縱切約 10–11 cm — [POCUS 101](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- Emamian et al. (AJR 1993) 665 名丹麥成人志願者，探討年齡、性別、體型 — 引用見 [Radiopaedia: Normal kidney size in adults](https://radiopaedia.org/articles/normal-kidneys-size-in-adults)（**數值未取得**）

**台灣 (Su et al., PLoS One 2019; n = 3,707, Chang Gung Kaohsiung & Linkou 健檢中心, 2010–2017)** — [PMC6837751](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837751/)

| 量測 (cm) | 全體 | 男 | 女 |
|---|---|---|---|
| 右腎長 | 10.62 ± 0.69 | 10.76 ± 0.66 | 10.41 ± 0.67 |
| 左腎長 | 10.76 ± 0.70 | 10.87 ± 0.69 | 10.59 ± 0.68 |
| 右腎寬 | 4.78 ± 0.75 | 4.99 ± 0.73 | 4.46 ± 0.66 |
| 左腎寬 | 5.10 ± 0.64 | 5.29 ± 0.60 | 4.82 ± 0.59 |
| 右 "cortical" thickness | 1.46 ± 0.32 | 1.51 ± 0.31 | 1.39 ± 0.31 |
| 左 "cortical" thickness | 1.49 ± 0.30 | 1.52 ± 0.29 | 1.45 ± 0.29 |

- 男女差異皆 p < 0.001；所有量測左 > 右 — 同上
- 長、寬與年齡呈二次（倒 U）關係，約第四個十年達高峰後下降；cortical thickness 隨年齡線性下降；但校正身高、體重後年齡解釋力消失 — 同上
- 與右腎長相關係數：體重 r = 0.422、身高 0.363、BMI 0.300、年齡 −0.155；多變量模型 adjusted r² 僅 0.192 — 同上
- 台灣平均右腎長在 15 個國際研究中屬偏高（Serbia 11.44 cm 最大，India 9.6 cm 最小），作者主張各族群需自有參考值 — 同上
- 48 位高量操作者間右腎長 ANOVA 無顯著差異 (p = 0.3451) — 同上
- 其他研究：男性腎較大；年齡相關縮小主要在 70 歲以後 — [Aga Khan University study](https://scholars.aku.edu/en/publications/ultrasonographic-renal-size-in-individuals-without-known-renal-di-3/)；另一研究顯示 60 歲後下降加速，且校正身高、年齡後性別差異不顯著，建議用 relative renal length — [CROSBI 148187](https://www.bib.irb.hr/385041)
- 巴基斯坦 4,035 人：右腎長 101.6 ± 8.9 mm、寬 42.7 ± 7.1 mm — [Aga Khan](https://scholars.aku.edu/en/publications/sonographic-measurement-of-renal-dimensions-in-adults-and-its-cor/)

**兒童**
- Rosenbaum et al. 1984：首個超音波兒童腎長 normative data（203 名 0–19 歲），至今仍廣泛使用；例：8 天–4 個月平均約 5.28 cm，8–9 歲約 9.00 cm — 引述於 [Clinics 2009 (PMC2671979)](https://pmc.ncbi.nlm.nih.gov/articles/PMC2671979)
- Rosenbaum 樣本含部分有 UTI/泌尿病史者（限制）— [PMC9023417](https://pmc.ncbi.nlm.nih.gov/articles/PMC9023417)
- 馬來西亞研究指出以白人資料建立的 nomogram 不適用馬來西亞兒童 — [Med J Malaysia 2020](https://mail.e-mjm.org/2020/v75n2/paediatric-renal-size.pdf)
- 日本 2022 研究：平均腎長 (cm) ≈ 身高 (m) × 5 + 2 — [Clin Exp Nephrol 2022](https://link.springer.com/article/10.1007/s10157-022-02205-0)
- 新生兒：cortex 回音 ≈ 肝（早產兒更亮）；pyramids 明顯且低回音；cortex:medulla 比 1.64:1（成人 2.59:1）；renal sinus 回音較少（脂肪少）— [Hricak et al. Radiology 1983](https://pubs.rsna.org/doi/10.1148/radiology.147.3.6844606)；[Thieme review](https://www.thieme-connect.de/products/ejournals/html/10.1055/s-0042-1757117)
- 新生兒 echogenic medullary pyramids（如脫水）屬另一種、可能短暫的發現，需配合臨床 — [Radiopaedia case: Echogenic medullary pyramids](https://radiopaedia.org/cases/echogenic-medullary-pyramids-1)

### Inferences
- 對學生的速記：成人 ~10–12 cm（亞洲/台灣中位 ~10.7 cm）；< 9 cm 或兩側差 > 2 cm 值得注意；但個體差異大，最好以身高/體重校正。
- 新生兒「pyramids 很黑很大」容易被初學者誤認為 hydronephrosis 或囊腫——辨識要點是它們呈規則排列的三角形、位於 cortex 下方，並未與中央 collecting system 相通。（推論，基於上述 Hricak 描述）

### Gaps
- 未取得 Emamian 1993 與 Rosenbaum 1984 原文數值/回歸公式。
- 未找到台灣兒童腎長 nomogram。
- Taiwan 研究的 "cortical thickness" 定義與數值和其他文獻不一致（見 Q5）。

---

## Q7. 類似病灶的正常變異 (Normal variants / pseudotumors)

### Takeaway
多數 pseudotumor 的共通辨識原則：與正常實質 **isoechoic**、與 cortex **連續**、腎輪廓平滑、Color Doppler 血流與周圍實質相同；不確定時以對比 CT/MRI/CEUS 證實其強化與 cortex 相同。

### Cited Findings
- **Hypertrophied column of Bertin**：cortex 向內延伸、壓迫 renal sinus；與相鄰 cortex 連續、內含 pyramids、Doppler 血流與周圍相同、通常 < 3 cm；常在上/中三分之一交界，左側較常見；columns of Bertin 約見於 50% 健康人 — [Radiopaedia](https://radiopaedia.org/articles/hypertrophied-column-of-bertin)；超音波上與實質同回音、輪廓平滑、無 posterior enhancement — [UroToday case](https://urotoday.com/current-issue/hypertrophied-column-of-bertin-a-mimicker-of-a-renal-mass/download.html)
- **Dromedary (splenic) hump**：左腎外側中段的皮質隆起，發育期受脾臟壓迫所致；Color Doppler 血流正常 — [Radiopaedia case 26152](https://radiopaedia.org/cases/26152)
- **Junctional parenchymal defect**：lobe 融合不完全；上極與中段交界的三角形 echogenic cortical defect，是 sinus fat 延伸入 cortex；鑑別 angiomyolipoma（通常較圓）、duplex kidney、fetal lobulation — [Radiopaedia article 16286](https://radiopaedia.org/articles/16286)；cases: [1](https://radiopaedia.org/cases/junctional-parenchymal-defect-of-kidney), [2](https://radiopaedia.org/cases/junctional-parenchymal-defect-of-the-kidney)；最適合在 longitudinal 評估 — [UW Radiology teaching PDF](https://radiology.wisc.edu/wp-content/uploads/2025/01/UW-Radiology-Summit-Non-neoplastic-renal-path-final.pdf)
- **Persistent fetal lobulation**：位於 pyramids **之間**的平滑凹陷 — [Radiopaedia article 6237](https://radiopaedia.org/articles/6237)；與 scar 的區別：scar 位於 pyramid **正上方**、fetal lobulation 位於 pyramids 之間 — [UW Radiology PDF](https://radiology.wisc.edu/wp-content/uploads/2025/01/UW-Radiology-Summit-Non-neoplastic-renal-path-final.pdf)
- 對比 CT/MRI/US 顯示與周圍實質相同強化模式即可與浸潤性腫瘤區分 — [Radiology of Kidney Pseudotumors (articl.net)](https://articl.net/diagnostic-radiology/radiology-of-kidney-pseudotumors)
- **Renal sinus lipomatosis / Extrarenal pelvis**：僅找到低品質來源（flashcards）：sinus lipomatosis = sinus 脂肪增多伴實質萎縮；extrarenal pelvis = 部分/完全在腎外的中央囊狀區，可能誤認為 hydronephrosis — [Brainscape flashcards](https://brainscape.com/flashcards/renal-retro-test-review-3006641/packs/4792456)（**低可信度，需以教科書驗證**）
- Radiopaedia variants 清單包含 persistent fetal lobulation、hypertrophied column of Bertin、dromedary hump、horseshoe、ectopic、supernumerary kidney 等 — [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)

### Inferences
- **Duplex collecting system**：一般認知為腎臟偏長、sinus 被一條實質帶（"bridging parenchyma"，形似 column of Bertin）分成上下兩團；此描述未在本輪取得權威引文。
- **Extrarenal pelvis vs hydronephrosis**：關鍵在 calyces 是否擴張——extrarenal pelvis 的 calyces 不擴張、pelvis 位於腎輪廓外（推論）。
- 給模型/學生的通則：「看起來像腫塊，但亮度、紋理、血流與 cortex 一樣，且有 pyramid 在裡面」→ 多半是正常變異。

### Gaps
- Duplex system、extrarenal pelvis、sinus lipomatosis 的 Radiopaedia/RadioGraphics 權威頁未擷取。
- Dromedary hump、fetal lobulation 的盛行率數字僅見於次級聚合網站，未採用。

---

## Q8. 圖像資源連結 (Image-rich links)

### Takeaway
以下為已確認存在、含圖像的教學頁；可直接用於教學投影片的參考（注意版權）。

### Cited Findings
- 正常腎臟解剖與超音波外觀（含 variants 連結樹）— [Radiopaedia: Kidneys](https://radiopaedia.org/articles/kidneys)
- 成人正常大小 — [Radiopaedia: Normal kidney size in adults](https://radiopaedia.org/articles/normal-kidneys-size-in-adults)
- POCUS 101 step-by-step（含探頭位置照片、標註的 longitudinal/transverse 圖、fan 與旋轉 GIF）— [POCUS 101 Renal](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)
- Hypertrophied column of Bertin — [Radiopaedia](https://radiopaedia.org/articles/hypertrophied-column-of-bertin)
- Junctional parenchymal defect — [Radiopaedia article](https://radiopaedia.org/articles/16286)、[case 1](https://radiopaedia.org/cases/junctional-parenchymal-defect-of-kidney)、[case 2](https://radiopaedia.org/cases/junctional-parenchymal-defect-of-the-kidney)
- Persistent fetal lobulation — [Radiopaedia](https://radiopaedia.org/articles/6237)
- Dromedary hump — [Radiopaedia case 26152](https://radiopaedia.org/cases/26152)
- Echogenic medullary pyramids（新生兒）— [Radiopaedia case](https://radiopaedia.org/cases/echogenic-medullary-pyramids-1)
- 方位/marker 慣例 — [SonoSite Institute](https://www.sonositeinstitute.com/course-lessons/instrumentation-section-3-chapter-3-lesson-5-transducer-marker-orientation)、[CanadiEM PoCUS Previews 02](https://canadiem.org/pocus-previews-02-intro-to-image-generation)、[ultrasound.guide](https://ultrasound.guide/46/ultrasound-image-orientation-and-conventions)
- 非腫瘤腎病理 teaching slides（含 fetal lobulation vs scar）— [UW Radiology PDF](https://radiology.wisc.edu/wp-content/uploads/2025/01/UW-Radiology-Summit-Non-neoplastic-renal-path-final.pdf)
- 腎臟超音波報告/protocol 範例 — [UW Radiology wiki Final_Renal.pdf](https://wiki.radiology.wisc.edu/images/8/8a/Final_Renal.pdf)

### Inferences
- Core Ultrasound (coreultrasound.com) 與 SonoWorld 應有腎臟 normal anatomy 影片，但本輪未驗證具體 URL，故不列出。

### Gaps
- Radiopaedia renal ultrasound protocol 頁 URL 已失效 (404)；duplex kidney、extrarenal pelvis、renal sinus lipomatosis 的影像頁未驗證。
