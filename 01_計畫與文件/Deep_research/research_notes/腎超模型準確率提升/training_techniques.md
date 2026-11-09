# Training techniques for small ultrasound datasets (<1000 images, ~180 patients): ordinal echogenicity grading + kidney segmentation

Scope note: the project is kidney US; echogenicity Grade 0–3 (ordinal); brightness is the diagnostic signal; UNet/nnU-Net 2D segmentation; ResNet18 / EfficientNet-B3 / MLP-ResNet18 fusion with numeric features (cortex/liver gray ratio, kidney length); auxiliary eGFR<60. Hardware: one Windows PC, CPU or one consumer GPU.
Tags used below: **[US]** = evidence measured on ultrasound; **[Med]** = other medical imaging; **[Inferred]** = my reasoning, not measured.
Research was done 2026-10-23, with about 17 search/fetch calls. Several primary PDFs could not be fully read (UltraBench 2 body text, CORN results tables, SORD tables). Those are listed under Gaps.

## Q1. Initialization: ImageNet vs RadImageNet vs US foundation models vs in-domain SSL

### Takeaway
On small US datasets, US-specific or medical pretraining usually beats ImageNet for **classification**. The reported gains range from about 3 to 9 AUC points (RadImageNet) and about 3 to 6 accuracy points (USFM vs natural-image SimMIM). A 2026 benchmark (UltraBench 2) finds that the US-specific advantage holds for classification but has disappeared for **segmentation**, where general SOTA models have caught up. Most US foundation models are ViTs (ViT-B for USFM; ViT-Tiny for TinyUSFM), not the ResNet/EfficientNet CNNs the project currently uses. RadImageNet is the only option that drops straight into ResNet/EfficientNet-style CNN pipelines.

### Cited Findings
- **RadImageNet [US]:** On small datasets, RadImageNet-pretrained CNNs beat ImageNet on AUC by **+9.4% (thyroid nodule US)** and **+4.0% (breast mass US)**, both P<.001. Gains on larger CXR/CT datasets were 0.9–6.1%. Lesion localization improved 64.6% (thyroid US) and 16.4% (breast US). The database has 1.35M images (CT/MRI/US) from 131,872 patients. — [Mei et al., Radiology: AI 2022, PMC9530758](https://pmc.ncbi.nlm.nih.gov/articles/PMC9530758); [RSNA PDF](https://pubs.rsna.org/doi/pdf/10.1148/ryai.220126)
- **Contradicting evidence [Med]:** An independent arXiv comparison across 7 medical classification tasks found ImageNet-pretrained models outperform RadImageNet overall. — [arXiv 2302.08272](https://arxiv.org/abs/2302.08272v1). A 2025 follow-up compared fine-tuned AUCs on breast lesion and ACL tasks with DeLong tests; its US numbers were not extracted. — [arXiv 2508.17567](https://arxiv.org/html/2508.17567v2)
- **RadImageNet weight availability:** Pretrained CNN weights are listed in the RSNA AI model catalog. — [RSNA Atlas card](https://atlas.rsna.org/cards/61caf4ba-8941-4699-9824-9e341d9661b9)
- **USFM [US]:** Pretrained by spatial-frequency dual masked image modeling on about 2.19M US images (3M-US database) covering 12 organs, multi-center and multi-device. Backbone is ViT-B scale. Published in Medical Image Analysis 96 (2024), doi 10.1016/j.media.2024.103202. — [arXiv 2401.00153](https://arxiv.org/html/2401.00153v1)
  - Segmentation DSC, USFM vs natural-image SimMIM: neck 80.6 vs 79.4; thyroid 85.9 vs 83.1; breast 84.3 vs 80.9; fetus 85.8 vs 83.7 (+1.2 to +3.4). — [same](https://arxiv.org/html/2401.00153v1)
  - Classification accuracy: breast 87.7 vs 81.2; abdomen 93.3 vs 90.0; fetus 93.6 vs 89.7 (+3.3 to +6.5). — [same](https://arxiv.org/html/2401.00153v1)
  - With 20% of labels: segmentation DSC 72–76%, classification F1 74–81%. The authors say other methods "failed to achieve acceptable" results at 20%, but exact baseline numbers appear only in a figure. — [same](https://arxiv.org/html/2401.00153v1)
  - The paper does not compare against ImageNet-supervised initialization or MAE, and the HTML page states no repo or weight license. — [same](https://arxiv.org/html/2401.00153v1)
- **TinyUSFM [US]:** Distilled from USFM into a **ViT-Tiny (~5.5M params)** using a 200K-image coreset. It matches USFM with 6.36% of the parameters and 6.40% of the GFLOPs. It reports +9.45% classification and +7.72% segmentation over a "vanilla" model (self-reported). Evaluated on UniUS-Bench (8 classification and 10 segmentation datasets, 15 organs). — [arXiv 2510.19239](https://arxiv.org/html/2510.19239v1)
- **USF-MAE [US]:** A ViT MAE pretrained on OpenUS-46, about 370K 2D/3D US images from 46 open datasets. The dataset is released publicly. Fine-tuned F1: BUS-BRA 81.6, MMOTU-2D 79.6, GIST514-DB 82.4. **UltraSam scored higher on BUS-BRA (F1 87.5).** — [arXiv 2510.22990](https://arxiv.org/pdf/2510.22990)
  - Follow-on use includes **fetal renal anomaly classification** vs a DenseNet-169 baseline, reported as gains in AUC and F1 (exact numbers not extracted). — [arXiv 2512.13434](https://arxiv.org/html/2512.13434v1)
- **UltraSam [US]:** A SAM-style model trained on US-43d, which has about 282K images with masks covering 58 structures from 43 open datasets. The authors report that its encoder also helps downstream classification and instance segmentation. Code and pretrained models are at github.com/CAMMA-public/UltraSam. — [arXiv 2411.16222](https://arxiv.org/html/2411.16222v2)
- **UltraDINO [US, fetal only]:** DINOv2-style self-distillation on FUS2M (about 2M Danish fetal US images). Reported SOTA on 3 fetal datasets. **Scaling natural-image pretraining did not help on US.** Code is at github.com/jakobamb/UltraDINO, but **weights are available only with permission tied to the pretraining data**. A MICCAI 2025 review criticized the lack of statistical repetitions. — [arXiv 2506.19552](https://arxiv.org/pdf/2506.19552); [MICCAI 2025 review page](https://papers.miccai.org/miccai-2025/0370-Paper4487.html)
- **UltraBench 2 (2026) [US]:** "Ultrasound-specific pretraining still leads on classification," while on segmentation "state-of-the-art general-purpose models have caught up." The full results tables could not be read. — [arXiv 2609.28610](https://arxiv.org/abs/2609.28610)
- **Other lightweight option [US]:** DINOv3 distilled into a ResNet-50 student for point-of-care US, about 3.4× compression (MIDL 2026). This gives a CNN-compatible US-adapted backbone if weights are released. — [PMLR v315](https://proceedings.mlr.press/v315/nahian26a.html)
- **SSL on own/in-domain data [US]:**
  - Breast US video contrastive pretraining beat ImageNet-pretrained MoCo-v2/BYOL/SwAV by about 0.2 in AUC, sensitivity, and specificity. It kept AUC about 0.90 with only 96 labeled training images. — [arXiv 2408.10600](https://arxiv.org/pdf/2408.10600)
  - SimCLR, MoCo, and SimSiam pretraining improved breast tumour segmentation (BUS) over the fully supervised baseline. Multi-organ US pretraining beat target-organ-only pretraining. — [arXiv 2402.14114](https://arxiv.org/html/2402.14114v1)
  - In a fetal-plane study, SimCLR helped mainly when the dataset was small with low inter-class variability. — [VanBerlo/related CVPRW 2023 & search summary; see](https://openaccess.thecvf.com/content/CVPR2023W/DL-UIA/papers/VanBerlo_Exploring_the_Utility_of_Self-Supervised_Pretraining_Strategies_for_the_Detection_CVPRW_2023_paper.pdf)
  - In pneumothorax M-mode US, adding a large volume of unlabeled data improved external-validation performance. — [VanBerlo et al., CVPRW 2023](https://openaccess.thecvf.com/content/CVPR2023W/DL-UIA/papers/VanBerlo_Exploring_the_Utility_of_Self-Supervised_Pretraining_Strategies_for_the_Detection_CVPRW_2023_paper.pdf)
  - A review of contrastive vs MAE SSL for small medical datasets is available. — [arXiv 2308.06534](https://arxiv.org/pdf/2308.06534)

### Inferences
- **[Inferred] Recommended order for this project:**
  1. ImageNet baseline (already in use).
  2. RadImageNet ResNet/DenseNet init. This needs no architecture change, runs on CPU or one GPU, and has the best US small-data evidence for CNNs.
  3. US foundation model encoders (USF-MAE ViT, TinyUSFM ViT-T, UltraSam encoder) as an alternate image branch. TinyUSFM/ViT-T is the most compute-feasible; ViT-B fine-tuning at 224 px is feasible on a consumer GPU with small batches.
- **[Inferred]** SSL on only ~1000 of your own images is unlikely to beat a 300K–2M-image US foundation model. In-domain SSL helps most when there are many unlabeled images (videos/cine, other patients). Continued pretraining (domain-adaptive MAE/DINO) of a public US model on your unlabeled kidney frames is the more realistic route. On a consumer GPU, MAE ViT-B for about 100 epochs on ~10K images takes hours to a day.
- **[Inferred] Caution:** Most US foundation-model pretraining pipelines use intensity augmentations or normalization. Because echogenicity depends on absolute brightness relative to the liver, verify that frozen features preserve brightness ordering (for example, a linear probe on the gray ratio) before relying on them.
- **[Inferred]** For segmentation, given the UltraBench 2 finding, nnU-Net from scratch or with an ImageNet encoder is likely already competitive. US foundation-model init is a lower priority there.

### Gaps
- UltraBench 2 tables (per-model numbers, low-data regime) could not be read; the PDF was binary-only in fetch.
- No kidney-echogenicity-specific comparison of initializations was found.
- Licenses: USFM repo/weights license not confirmed; UltraSam and USF-MAE license terms not confirmed; UltraDINO weights are gated. Check each repo's LICENSE before use.
- No compute numbers (GPU-hours) were extracted for fine-tuning any of these on consumer hardware.

## Q2. Augmentation when intensity is the label

### Takeaway
The only large systematic US augmentation benchmark (14 tasks, 30 seeds each) finds that **geometric augmentations (rotate, zoom, random crop, translate) help classification most (+3.7 to +5.5% mAP)**. Several US-specific ones also help classification: speckle reduction (+4.1%), depth attenuation (+3.0%), and haze (+3.0%). Vertical flip hurts both tasks. TrivialAugment with the top 4–5 augmentations gave about +10% mAP. **The benchmark's tasks did not have intensity-defined labels**, so its brightness, contrast, and gamma gains do **not** transfer to echogenicity grading. For this project, global intensity transforms should be excluded from the grading model, or applied identically to kidney and liver (ratio-preserving).

### Cited Findings
- **Benchmark design [US]:** Tupper & Gagné, "Revisiting Data Augmentation for Ultrasound Images." 14 classification and segmentation tasks from 10 sources and 11 body regions. Compares 10 standard and 4 US-specific augmentations (depth attenuation, haze, Gaussian shadow, speckle reduction). EfficientNet-B0 / UNet-EffB0, 224×224, p=0.5, 30 seeds per augmentation. Hyperparameters tuned with Optuna TPE, 100 trials. — [arXiv 2501.13193](https://arxiv.org/html/2501.13193v2)
- **Classification [US]** (average Δ% mAP vs no augmentation over 7 tasks): rotate +5.48, zoom +5.47, random crop +5.39, speckle reduction +4.12, translate +3.72, Gaussian noise +3.38, brightness +3.08, depth attenuation +3.02, haze +2.99, horizontal flip +1.68, gamma +1.49, shadow +1.49, contrast +0.24, **vertical flip −0.38**. Depth attenuation gave +8.74% on its best task (**Fatty Liver**, an echogenicity-related task). — [same](https://arxiv.org/html/2501.13193v2)
- **Segmentation [US]** (average Δ% Dice): brightness +2.03, crop +0.46, translate +0.37. Most others were slightly negative. **Gaussian noise −4.98** (with one task dropping 40%), depth attenuation −1.40, **vertical flip −1.10**, speckle reduction −0.80. — [same](https://arxiv.org/html/2501.13193v2)
- **Kidney segmentation task [US]** (Open Kidney, 514 images, baseline Dice 0.830): Gaussian noise +1.59%, horizontal flip +0.72%, brightness +0.42%, depth attenuation +0.37%. Several were harmful: **speckle reduction −4.45%, rotate −3.06%, zoom −2.80%, translate −2.62%**, contrast −1.71%, shadow −1.30%. — [same](https://arxiv.org/html/2501.13193v2)
- **TrivialAugment [US]:** Classification gains over no augmentation were +7.9% (N=1), +9.3% (N=2), +10.2% (N=4), +10.23% (N=5), and **+7.6% with all 14** (adding harmful augmentations hurts). Segmentation gains: +2.6% (N=1) to +3.3% (N=4). — [same](https://arxiv.org/html/2501.13193v2)
- **Compute [US]:** Speckle reduction added 1.5–2× training time, but only for smaller models. — [same](https://arxiv.org/html/2501.13193v2)
- **Physics-inspired augmentations in SSL [US]:** A liver US view classifier with SimCLR and physics-inspired augmentations reached 95.1% accuracy with limited labels. — [MGH research spotlight](https://www.massgeneral.org/news/research-spotlight/self-supervised-learning-analysis-liver-ultrasound)

### Inferences
- **[Inferred] Safe for echogenicity grading:**
  - small rotation (±10–15°)
  - scale/zoom (0.9–1.1)
  - random crop/translate that keeps the kidney and liver in view
  - mild elastic deformation
  - horizontal flip (only if left/right kidney orientation is not a label cue)
  - speckle-like multiplicative noise at low strength
  - depth attenuation **only if applied to the whole image, so the kidney/liver ratio at similar depth is preserved**
- **[Inferred] Harmful or risky for grading:**
  - global brightness, contrast, gamma, histogram equalization, CLAHE: these change the label-defining signal, and the benchmark's positive brightness results come from tasks whose labels are not brightness-defined
  - vertical flip: it moves the near and far fields, and the benchmark shows it is negative for both tasks
  - speckle reduction/denoising, which may change texture-based echogenicity cues
- **[Inferred]** For segmentation (kidney mask), brightness/contrast augmentation is fine and helped in the benchmark. Use different augmentation pipelines for the segmentation and grading heads, or at least turn off intensity augmentation on the grading branch when doing multi-task training.
- **[Inferred]** A ratio-preserving intensity augmentation (the same gamma applied to the whole image, with the label tied to the cortex/liver ratio) may be acceptable but is untested. Ablate it.

### Gaps
- No US paper was found that measures augmentation effects when the label itself is echogenicity or brightness. The Fatty Liver task in the Tupper benchmark is the closest, and only its depth attenuation number (+8.74%) was extracted.
- The elastic-deformation effect in US was not separately quantified in the sources read.

## Q3. Ordinal losses: CORAL vs CORN vs cumulative link vs SORD vs CE

### Takeaway
On a medical 4-class ordinal task (LIMUC ulcerative colitis, MES 0–3, imbalanced like this project), **CORN gave only marginal gains over plain CE** (QWK 0.837 vs 0.830 on ResNet18). **Class-distance-weighted CE (CDW-CE) and even MSE regression did better** (QWK 0.857 and 0.854). Differences between methods are small (about 0.01–0.03 QWK) relative to seed variance (±0.01). No head-to-head CORAL vs CORN vs SORD study on a medical dataset was found.

### Cited Findings
- **LIMUC benchmark [Med, endoscopy, 4 ordinal grades]:** 11,276 images, 564 patients. Classes 54.1% / 27.1% / 11.1% / 7.7%. Results with ResNet18 (mean ± std): — [arXiv 2412.01246](https://arxiv.org/html/2412.01246v1)

  | Loss | QWK | MAE | Acc | F1 |
  |---|---|---|---|---|
  | CE | 0.830±0.014 | 0.258 | 0.757 | 0.672 |
  | MSE | 0.854±0.007 | 0.235 | 0.770 | 0.693 |
  | CORN | 0.837±0.007 | 0.252 | 0.759 | 0.681 |
  | CO2 | 0.839 | 0.250 | 0.760 | 0.678 |
  | HO2 | 0.845 | 0.246 | 0.763 | 0.686 |
  | **CDW-CE** | **0.857±0.010** | **0.230** | **0.774** | **0.706** |

  The same ranking holds for Inception-v3 (CDW-CE QWK 0.868 vs CE 0.836) and MobileNet-v3 (0.859 vs 0.830). CORAL was not benchmarked. — [same](https://arxiv.org/html/2412.01246v1)
- **CDW-CE original [Med]:** Class Distance Weighted CE for UC severity. — [arXiv 2202.05167](https://arxiv.org/pdf/2202.05167)
- **CORN vs CORAL:** CORN removes CORAL's weight-sharing constraint by using conditional training sets and the chain rule, and works with any architecture. The authors claim it "improves the performance substantially compared to the CORAL reference approach" (numbers not extracted). Published in Pattern Analysis & Applications 2023. — [arXiv 2111.08851](https://arxiv.org/abs/2111.08851v5)
- **SORD:** Soft labels from ordinal distance, used with plain CE/KL. No architecture change is needed. Competitive with task-specific methods on 4 non-medical tasks (CVPR 2019). — [Diaz & Marathe CVPR 2019](https://openaccess.thecvf.com/content_CVPR_2019/html/Diaz_Soft_Labels_for_Ordinal_Regression_CVPR_2019_paper.html). An implementation exists as `dlordinal.losses.SORDLoss`, with `alpha` controlling smoothness. — [dlordinal docs](https://dlordinal.readthedocs.io/en/stable/_modules/dlordinal/losses/sord.html)
- **Other [Med]:** CE plus an ordinal residual loss beat CE alone for lumbar vertebra level classification. — [MDPI Diagnostics 15(23):2949](https://www.mdpi.com/2075-4418/15/23/2949). A 2026 "Ordinal CE" preprint (a cost matrix added to CE) claims lower misclassification cost and better calibration. — [arXiv 2606.25769](https://arxiv.org/pdf/2606.25769)

### Inferences
- **[Inferred]** With about 180 patients, differences of about 0.01–0.02 QWK between ordinal losses will be within cross-validation noise. Choose the loss on robustness, and report QWK/MAE with patient-level CV and several seeds.
- **[Inferred] Practical ranking to try:**
  1. CE with SORD soft labels or CDW-CE: loss-only changes that keep one softmax head, so they are easy to combine with class weights and the eGFR auxiliary head.
  2. CORN.
  3. CORAL.
  4. Regression (MSE on grade) plus threshold tuning, which is a strong and simple baseline per LIMUC.
- **[Inferred]** With an imbalanced top grade (Grade 3), CORN/CORAL's per-threshold binary tasks can starve the last threshold. Monitor per-threshold positives.

### Gaps
- No medical/US benchmark with CORAL, CORN, SORD, a cumulative-link (logistic POM) head, and CE on the same data was found.
- The CORN paper's MAE tables and SORD's tables were not extracted.

## Q4. Class imbalance: class weights vs resampling vs focal loss

### Takeaway
Evidence on small medical datasets is thin and mixed. Oversampling and focal loss sometimes give the best AUPRC, but gains over a no-handling baseline are often minimal and trade precision for recall. With extremely small data, resampling and reweighting can't fix insufficient data volume.

### Cited Findings
- **[Med]** A comparison of oversampling, undersampling, focal loss, two-phase learning, and dynamic sampling found oversampling and focal loss best on AUPRC. **AUPRC improvements over baseline were minimal**, and the methods generally raised recall while lowering precision and accuracy. — [AAPM 2022 abstract](https://w4.aapm.org/meetings/2022AM/programInfo/programAbs.php?aid=65561)
- **[Med]** Resampling and cost-sensitive training are "limited in their effectiveness when the original dataset is extremely small." — [arXiv 2602.14365](https://arxiv.org/pdf/2602.14365)
- **[Med]** LMF loss (label-distribution-aware margin plus focal) reports +2–9% macro-F1 across 4 medical datasets and 3 architectures (proposer's own results). — [arXiv 2212.12741](https://arxiv.org/html/2212.12741v2)
- **[Med]** Balanced-MixUp outperformed conventional sampling and imbalance-specific losses on retinal (55K images) and GI long-tail datasets. — [Balanced-MixUp record](https://dsp.tecnalia.com/items/c2e67593-0b71-4cc8-bb38-139f633c1344)
- **[Med]** Imbalance handling with transfer learning in brain tumor MRI (focal vs CE). — [arXiv 2308.06821](https://arxiv.org/pdf/2308.06821)

### Inferences
- **[Inferred]** For about 1000 images with 4 grades: start with sqrt-inverse-frequency class weights, or a patient-balanced sampler, but not both. Choose the operating point by threshold tuning on validation instead of heavy resampling. Focal loss adds a hyperparameter (γ) that is hard to tune reliably on ~180 patients.
- **[Inferred]** Oversampling duplicates the few Grade-3 patients, which increases overfitting risk. Sample at the **patient** level so one patient's many frames don't dominate.

### Gaps
- No US-specific imbalance comparison was found, and no study combines imbalance methods with ordinal losses.

## Q5. Fusing image features with tabular features (early vs late vs FiLM/DAFT/attention)

### Takeaway
For small datasets, systematic reviews recommend **late fusion** (or early fusion with classical ML) over complex joint fusion networks. DAFT (a FiLM-style variant) beat image-only and tabular-only models and earlier fusion methods in a 3D MRI Alzheimer setting, but that dataset was larger. No evidence was found for FiLM/attention stability at ~180 patients.

### Cited Findings
- **[Med]** A systematic review of EHR plus imaging fusion: for small datasets, early or late fusion using classical ML "is generally preferred." Late fusion "does not impose the requirement of a huge amount of training data." — [arXiv 2210.13462](https://arxiv.org/pdf/2210.13462)
- **[Med]** DAFT conditionally scales and shifts CNN feature maps using tabular data. It outperformed image-only, tabular-only, and prior single-network fusion (including FiLM) on Alzheimer's diagnosis and time-to-dementia. Its parameters spanned a wider range and were more robust to noise than FiLM's. — [Pölsterl et al., arXiv 2107.05990](https://arxiv.org/pdf/2107.05990)
- **[Med]** A review argues late fusion "fail[s] to foster mutual learning" while joint fusion permits end-to-end conditioning. — [arXiv 2403.13319](https://arxiv.org/html/2403.13319v3)

### Inferences
- **[Inferred]** The numeric features (cortex/liver gray ratio, kidney length) are low-dimensional and directly diagnostic. A strong baseline is logistic or ordinal regression on the tabular features alone. Then add a stacked or late-fusion model (image-model out-of-fold logits plus tabular features into an ordinal logistic model). This is the most stable choice at n≈180 patients and is CPU-cheap.
- **[Inferred]** The current MLP-ResNet18 (concatenation, i.e. intermediate fusion) risks the network ignoring weak image features or overfitting the MLP. Mitigations: modality dropout, a low-capacity fusion head, and standardizing the tabular inputs. FiLM/DAFT adds parameters; try it only if late fusion plateaus, and compare with repeated patient-level CV.

### Gaps
- No US study comparing fusion strategies was found, and no FiLM vs concatenation comparison at <500 patients.

## Q6. Multi-task learning (segmentation + classification) effect on classification in US

### Takeaway
US multi-task papers mostly report **small classification gains (<1 percentage point in accuracy)** from adding segmentation-aware modules. One survey-cited study reported about 15% gains on BUSI. Effects are inconsistent, and the papers are typically by the proposing authors.

### Cited Findings
- **[US]** Carotid plaque RCCM-Net: adding a region-confidence module (segmentation-guided) raised accuracy +0.31%, precision +0.51%, and Kappa +0.40%. Overall accuracy was 85.82%. — [arXiv 2307.00583](https://arxiv.org/pdf/2307.00583)
- **[US]** Breast US CNN-Transformer multi-task on BUSI: classification accuracy 93.86% → 94.04% (+0.18), Dice 81.94 → 83.42. — [VCIBA 2024 Table 3](https://vciba.springeropen.com/articles/10.1186/s42492-024-00155-w/tables/3)
- **[US]** RMTL-Net uses predicted segmentation probability maps to guide the classifier (regional attention), with ablations on 2 public datasets. — [Kean University record](https://researchers.kean.edu/en/publications/a-regional-attentive-multi-task-learning-framework-for-breast-ult/)
- **[US]** A survey-cited study (Aumente-Maestro et al.) reported about 15% improvements in both tasks over single-task models on BUSI (secondary citation). — [via HyFormer-Net related work, arXiv 2511.01013](https://arxiv.org/pdf/2511.01013)

### Inferences
- **[Inferred]** For echogenicity, the bigger benefit of segmentation is probably **using the mask to compute features or ROI-crop/mask-pool image features** (cortex and liver ROI intensity), not joint loss sharing. A two-stage pipeline (segment, then compute ratio and features, then grade) is simpler and more stable on small data than end-to-end multi-task training.
- **[Inferred]** If training jointly, keep intensity augmentation off for the grading loss (see Q2) and weight the segmentation loss low to avoid gradient conflict.

### Gaps
- No kidney US multi-task study was found. No US study isolates the effect of the eGFR auxiliary task.

## Q7. Input resolution (224 vs 384 vs 512) for US texture classification

### Takeaway
No US study directly comparing 224/384/512 was found. Medical (CXR, endoscopy) evidence shows the best resolution is task-dependent. Subtle findings benefit from higher resolution, many others do not, and multi-resolution ensembles beat single-resolution models. The main US augmentation benchmark used 224×224.

### Cited Findings
- **[Med]** MIMIC-CXR at 256/512/1024/2048 px with DenseNet121 and EfficientNet-B4: some findings were better at high resolution, but "many other findings are actually labeled better using downscaled inputs." The resolution ensemble beat any single resolution. — [Haque et al., J Med Imaging 2023](https://www.spiedigitallibrary.org/journals/journal-of-medical-imaging/volume-10/issue-04/044503/Effect-of-image-resolution-on-automated-classification-of-chest-X/10.1117/1.JMI.10.4.044503.full); [medRxiv](https://www.medrxiv.org/content/10.1101/2021.07.30.21261225.full.pdf)
- **[Med]** HyperKvasir endoscopy (23 findings): heavy downscaling eventually removes important information. Prior CXR work found lower resolutions sometimes better. — [Thambawita et al., Diagnostics 2021, PMC8700246](https://pmc.ncbi.nlm.nih.gov/articles/PMC8700246)
- **[US]** The Tupper & Gagné benchmark used 224×224 for all 14 US tasks. — [arXiv 2501.13193](https://arxiv.org/html/2501.13193v2)

### Inferences
- **[Inferred]** Echogenicity is a regional mean-intensity property rather than fine texture, so 224–320 px on an **ROI crop** (kidney plus adjacent liver) is likely sufficient. Resizing the whole frame to 512 mainly adds compute. ROI cropping preserves effective resolution at low cost.
- **[Inferred] Compute:** ResNet18 at 384 is about 3× the FLOPs of 224. EfficientNet-B3's native size is 300. On a consumer GPU all are feasible; on CPU, stay at 224–256.

### Gaps
- No US-specific resolution ablation was found.

## Q8. Hyperparameter search budgets for small data

### Takeaway
The only concrete US reference point is the Tupper & Gagné benchmark: **Optuna TPE, 100 trials**, tuned once without augmentation, with each configuration then repeated over **30 seeds** because seed variance is large on small US datasets.

### Cited Findings
- **[US]** Hyperparameters were tuned with Optuna (100 TPE trials, no augmentation), trained ≥100 epochs, and each augmentation was evaluated over 30 random seeds per task. — [arXiv 2501.13193](https://arxiv.org/html/2501.13193v2)
- **[Med]** Seed variance on the 4-grade ordinal task: QWK std about ±0.006–0.015 across losses, comparable to the between-loss differences. — [arXiv 2412.01246](https://arxiv.org/html/2412.01246v1)

### Inferences
- **[Inferred]** With ~180 patients, the bigger risk is overfitting the validation folds through search. Suggested approach:
  - Tune only a few parameters (learning rate, weight decay, augmentation strength, loss-specific α).
  - Use about 20–50 TPE trials on inner folds, nested inside patient-level outer CV, or with one fixed held-out test set never touched.
  - Report the mean ± std over at least 5 seeds.
- **[Inferred]** nnU-Net's self-configuring defaults remove most tuning for segmentation, so spend the budget on the grading model.

### Gaps
- No US paper was found that studies HPO budget size vs overfitting on small data.
