# Kidney Ultrasound AI Case Studies: Techniques That Improved Accuracy and by How Much

Project context: about 180 patients. Tasks are kidney segmentation, ordinal cortical echogenicity Grade 0–3, and an auxiliary eGFR<60/CKD label.
Verification legend: [V-full] = checked against the full text (PMC or journal). [V-abs] = checked against the abstract or repository record only. [UNVERIFIED] = taken from a search snippet or secondary review, so check it before citing.

## Q1. Which CKD/eGFR-from-ultrasound studies exist, and which techniques improved accuracy (with ablations)?

### Takeaway
Two anchor studies matter most. Lee et al. 2022 (Korea, 909 patients) is the cleanest ablation for this project. Adding automatically extracted kidney length and kidney-to-liver echogenicity ratio to a ResNet18 raised AUROC from 0.81 to 0.88, and adding diabetes raised it to 0.91. Kuo et al. 2019 (Taiwan, 1,299 patients) used ImageNet-pretrained ResNet-101, a crop defined by the kidney-length markers, augmentation and 10× bagging to reach CKD accuracy 85.6% and AUC 0.904. Kuo did not publish with/without ablations for cropping, augmentation or bagging. Neither study ran an external validation.

### Cited Findings

**Kuo et al. 2019, npj Digital Medicine 2:29, DOI 10.1038/s41746-019-0104-2 [V-full]**
- **Data:** 1,299 patients (Table 1 says 1,297), 1,446 studies and 4,505 kidney images. Single center (China Medical University Hospital, Taiwan), GE LOGIQ E9/P3 scanners. Split by hashed patient ID: 4,010 images for training/validation and 495 for test. Labels are MDRD eGFR from creatinine within 4 weeks of the scan. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Architecture:** ResNet-101 pretrained on ImageNet with the first residual block frozen. Regression head of 512-512-256-1 neurons with dropout 0.5. CKD classification is done by XGBoost on the 256-dimensional FC3 features. Optimizer Adam (learning rate 1e-4, L2 1e-5), early stopping with patience 20. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **ROI cropping:** The two kidney-length caliper markers define a square crop, which is resized to 224×224. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Augmentation:** Shift ±10%, rotation ±40° and horizontal flip, each applied with 80% probability. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Bagging:** 10 bootstrap resamples, each training one ResNet and one XGBoost. Predictions are averaged. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Results:** eGFR regression Pearson r = 0.741, MAE = 17.6. CKD (eGFR<60) accuracy 85.6%, AUC 0.904, specificity 92.1%, sensitivity about 60.7%. At an eGFR 45 threshold, accuracy was 78% and AUC 0.83. Four nephrologists (more than 10 years' experience) scored 60.3–80.1% accuracy. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Partial ablations:**
  - Data size: correlation 0.53 with 10% of the data versus 0.66 with 50%.
  - VGG-19 improved MAE by only 3.1% at about 2.5× the compute.
  - Polynomial calibration reduced MAE by only 0.1.
  - HOG, LBP and ORB handcrafted features were all worse than ResNet-101.
  - The class weight of 0.25 changed the sensitivity/specificity tradeoff, not overall accuracy.
  - No numbers are given for cropping, augmentation or bagging on versus off.
  - Source: [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Failures and limitations:**
  - Regression is biased at low eGFR (mean bias −7.74, which grows as eGFR falls).
  - The eGFR distribution is skewed: only about 15% of studies had eGFR>60.
  - Sensitivity is moderate.
  - Single center, with no external validation.
  - Source: [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)

**Lee S, Kang M, Byeon K, … Park JT. "Machine Learning-Aided Chronic Kidney Disease Diagnosis Based on Ultrasound Imaging Integrated with Computer-Extracted Measurable Features." J Digit Imaging 2022;35(5):1091–1100. DOI 10.1007/s10278-022-00625-8, PMID 35411524, PMCID PMC9582094 [V-full]**
- **Data:**
  - Segmentation set: 9,407 images from 456 patients.
  - Classification set: 3,495 images from 909 patients.
  - Sites: Severance and Gangnam Severance hospitals (Yonsei), 2011–2018.
  - Scanners: Philips, Siemens and GE.
  - Source: [PMC9582094](https://pmc.ncbi.nlm.nih.gov/articles/PMC9582094/); [Yonsei repository](https://ir.ymlib.yonsei.ac.kr/handle/22282913/193103?mode=full)
- **Split:** Patient-level, with 839 patients (3,001 images) for training and 70 patients (247 images) for test. Training used 10-fold CV × 10 seeds. Random and ImageNet initialization were both tested, for 600 runs in total. — [PMC9582094](https://pmc.ncbi.nlm.nih.gov/articles/PMC9582094/)
- **Pipeline:**
  1. Mask R-CNN segments the kidney and liver (validation mIoU 81.62, frequency-weighted IoU 89.35).
  2. Kidney length and kidney-to-liver echogenicity ratio are extracted automatically.
  3. The features are z-scored and concatenated to ResNet18's penultimate layer, then passed to the final FC layer (late fusion).
  - Source: [PMC9582094](https://pmc.ncbi.nlm.nih.gov/articles/PMC9582094/)
- **Ablation (test set):**

| Configuration | AUROC | Sensitivity | Specificity | Accuracy |
|---|---|---|---|---|
| Image only | 0.81 | 78.2% | 71.5% | 74.4% |
| + kidney length + echogenicity ratio | 0.88 | 86.1% | 77.5% | 81.2% |
| + diabetes | 0.91 | 89.4% | 82.9% | 85.9% |

  The effect of length and echogenicity ratio separately was not reported. — [PMC9582094](https://pmc.ncbi.nlm.nih.gov/articles/PMC9582094/)
- **Label design:**
  - CKD was defined as eGFR<60 sustained over 3 months (CKD-EPI).
  - Non-CKD was defined as eGFR≥90.
  - eGFR 60–90 was excluded. This extreme-group design inflates separability.
  - Images with large cysts, masses or hydronephrosis were excluded.
  - Source: [PMC9582094](https://pmc.ncbi.nlm.nih.gov/articles/PMC9582094/)
- **Self-reported risks:**
  - Echogenicity normalization was done per dataset, which risks leakage.
  - Segmentation and classification validation sets were not the same.
  - No external validation was done.
  - Operator and angle variability.
  - Source: [PMC9582094](https://pmc.ncbi.nlm.nih.gov/articles/PMC9582094/)

**Other CKD/function studies (from the reviews, numbers not individually verified)**
- **Tian 2024:** ResNet34 deep features fused with GLCM/HOG texture, 1,049 patients, AUC 0.781–0.931. Single center. — [Zhang et al. 2026 review, Front Oncol, PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/) [UNVERIFIED primary]
- **Applied Sciences 2022:** GAN augmentation plus MobileNetV2 for 4-stage CKD. Accuracy 81.9%, rising to 90.1% when a ±1-stage tolerance is allowed. — [MDPI applsci-12-00352](https://mdpi-res.com/d_attachment/applsci/applsci-12-00352/article_deploy/applsci-12-00352.pdf) [V-abs via snippet]
- **Multimodal fibrosis model (Renal Failure 2024):** Grayscale + SMI + strain elastography gave AUC 0.86, versus 0.648–0.745 for single-mode models. — [PMC11497579](https://pmc.ncbi.nlm.nih.gov/articles/PMC11497579/) [UNVERIFIED, snippet only]
- **Molina-Moreno 2024 (URI-CADS):** Multitask ResNet-50 + Mask R-CNN, 1,985 images, AUC 0.819. — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/) [UNVERIFIED primary]

### Inferences
- For a 180-patient project, Lee et al. is the direct template. Feed segmentation-derived kidney length and cortex/liver echogenicity ratio into the CNN head. The gain was +0.07 AUROC with the measurable features and +0.10 with diabetes, at N=909. The relative gain from handcrafted priors is plausibly larger at N=180, but that is untested.
- Both anchor studies exclude or under-represent the middle eGFR range (Lee drops 60–90, Kuo is skewed). Reported AUCs of 0.88–0.91 are therefore optimistic for an all-comers eGFR<60 auxiliary label.
- Kuo's crop from the caliper markers is an ROI technique the project can copy if images carry length calipers. Its isolated gain is unknown.

### Gaps
- There is no published with/without number for ROI cropping, bagging or augmentation in Kuo.
- There is no separate ablation of kidney length versus echogenicity ratio in Lee.
- Neither study did external validation, so the cross-hospital drop for CKD-from-ultrasound is unquantified in these two papers.

## Q2. What exists for segmentation (including the Open Kidney Ultrasound Data Set) and echogenicity grading?

### Takeaway
The Open Kidney Ultrasound Data Set has more than 500 patients and two expert annotators, with a baseline capsule Dice of 0.85. Segmentation Dice in the literature ranges from 0.77 to 0.97, but almost all of it comes from single-center data. No validated deep-learning ordinal grader for cortical echogenicity (Grade 0–3) was found. Kidney/liver echogenicity ratio is supported as a quantitative feature.

### Cited Findings
- **Open Kidney Ultrasound Data Set:** Singla, Ringstrom, Hu, Lessoway, Reid, Nguan, Rohling. arXiv:2206.06657, v2 dated December 2022. More than 500 patients over 5 years, native and transplant kidneys. Multi-class segmentation and view labels from two expert sonographers. A baseline state-of-the-art model reached capsule Dice 0.85. The abstract does not give the image count or the class list. — [arXiv 2206.06657](https://arxiv.org/abs/2206.06657) [V-abs]
- **Segmentation results summarized in the 2026 review (Table 2):**
  - CycleGAN CT→US: Dice 85.3%.
  - Seg-CycleGAN: Dice 85.48%.
  - MLAU-Net: Dice 90.21% on 44,880 images.
  - YSegNet: Dice 97% on 700 images.
  - Multiscale CNN: Dice 95.86% on 7,350 images.
  - 2D U-Net + transfer learning for ADPKD: Dice 80% on 22 patients.
  - Fast-UNet++ across 3 centers: Dice 95% on 744 images, the only multicenter segmentation study.
  - U-Net + active contour for volume: ICC 0.925 versus CT in 331 children.
  - Source: [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/) [UNVERIFIED primary; the review has citation-numbering errors]
- **Noise sensitivity:** A 30% drop in SNR reduced Dice by 8–12% (Guo). Operator variability shifts Dice by 5–7%. — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/) [UNVERIFIED primary]
- **Echogenicity ratio as a feature:**
  - Kidney/liver pixel-density ratio was inversely correlated with follow-up eGFR, r = −0.684 (Kidney Blood Press Res 2017). — [DOAJ](https://doaj.org/article/da03193e070c494689d7fbbb8ed876df) [V-abs via snippet]
  - Renal-to-liver echogenicity ratio was correlated with IFTA, AUC 0.83 for IFTA>50% (Thai glomerulopathy cohort). — [GMSMJ](https://he02.tci-thaijo.org/index.php/gmsmj/article/view/262871) [UNVERIFIED, snippet]

### Inferences
- With 180 patients, pretraining or fine-tuning the segmenter on the Open Kidney dataset (Canadian, includes transplant kidneys) is the most direct external-data lever. Expect a domain-shift penalty and use it only as initialization.
- An ordinal echogenicity grader would be novel. The cortex/liver ratio computed from the segmentation masks is the best-supported explicit feature to add.

### Gaps
- Specific follow-up papers using the Open Kidney dataset, with their Dice gains from pretraining, were not retrieved because of the tool-call budget.
- No study was found that reports an inter-rater kappa for the 0–3 echogenicity grade alongside an AI model.

## Q3. Pediatric hydronephrosis/CAKUT, multi-view aggregation, and external validation drops

### Takeaway
Multi-view and multi-instance aggregation is the largest single measured gain in this catalogue. In Yin et al. 2020, single-image AUC was about 0.80–0.82 and per-patient mean-pooled MIL AUC was 0.95–0.96, a gain of about +0.15. External validation in the hydronephrosis work (Erdman/SickKids) held AUROC around 0.9 at other hospitals, while specificity dropped. Across the field, the reported external drops are modest but real, for example r from above 0.9 to about 0.8 in Akbari.

### Cited Findings
- **Yin et al. 2020, Urology 142:183–189, DOI 10.1016/j.urology.2020.05.019 [V-full]:** 157 children (86 with posterior urethral valves vs 71 with mild unilateral hydronephrosis), 3,504 sagittal and 2,558 transverse images. Backbone was VGG16 pretrained on ImageNet and fine-tuned (Inception-ResNet v2 was best in a supplementary table, an inconsistency within the paper). Validation was 5-fold CV at a single institution with no external test. — [PMC7387180](https://pmc.ncbi.nlm.nih.gov/articles/PMC7387180/)

| Model | Sagittal AUC | Transverse AUC | Combined AUC |
|---|---|---|---|
| Single-image | 0.796±0.064 | 0.815±0.071 | — |
| MIL mean-pool | 0.949±0.035 | 0.954±0.033 | 0.961±0.026 |

  The combined model had accuracy 0.925, sensitivity 0.873 and specificity 0.986. Mean pooling beat max pooling (values are in the supplement). — [PMC7387180](https://pmc.ncbi.nlm.nih.gov/articles/PMC7387180/)
- **Erdman et al., Scientific Reports 2024, Hydronephrosis Severity Index:**
  - Internal prospective test, 202 patients: AUROC >90%, sensitivity >90%, specificity >70%.
  - Three external institutions: AUROC ≥90%, sensitivity ≥80%, specificity >50%.
  - The Cincinnati Children's press release reports different external figures (sensitivity ≥90%, specificity >70%), so the sources conflict.
  - Sources: [DOAJ, Sci Rep Oct 2024](https://doaj.org/article/8aa35c14841242259eba98cfaf0f7df3); [Cincinnati Children's blog](https://scienceblog.cincinnatichildrens.org/ai-tool-transforms-hydronephrosis-diagnosis/) [UNVERIFIED, snippets only]
- **Khondker et al., PLOS Digital Health 2025;4(8):e0000939, DOI 10.1371/journal.pdig.0000939, PMID 40758672 [V-full text, figures not read]:**
  - Data: SickKids training set of 401 patients and 753 visits, plus a silent-trial cohort of 202 patients. Stanford external set of 102 patients with a 5% pyeloplasty rate. CHOP external set of 89 patients with a 67% pyeloplasty rate.
  - Model: Siamese CNN taking two views (sagittal and transverse), with CLAHE, center crop and 256×256 input, and no augmentation.
  - Comparison: multi-visit fusion (averaging, conv pooling, TSM, LSTM) did **not** significantly beat the single-visit baseline. Averaging and TSM were numerically lower.
  - Limitation: the large differences in prevalence across sites show selection and label shift.
  - Source: [PMC12321052](https://pmc.ncbi.nlm.nih.gov/articles/PMC12321052/)
- **Hai 2021, CD-ConcatNet:** 2D+3D multiview fusion, 76 patients, AUC 0.867. — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/) [UNVERIFIED primary]
- **Sudharson 2020:** Ensemble of ResNet-101, ShuffleNet and MobileNet-v2, 96.54% accuracy for 4-class (cyst/stone/tumor/normal) on 4,940 public images. — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/) [UNVERIFIED primary]
- **External-validation drops and robustness:**
  - Akbari: correlation fell from >0.9 at a single center to about 0.8 on external multicenter data.
  - Adult-trained models dropped about 22% on pediatric data.
  - The review flags AUC 1.0 and 99.8% accuracy reports as likely overfit.
  - Source: [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/) [UNVERIFIED primary]

### Inferences
- For this project, patient-level aggregation (mean-pooling predictions across all images and views per kidney or patient) is the best-evidenced cheap win, about +0.15 AUC in Yin's small cohort of 157. Temporal multi-visit fusion did not help (Khondker 2025).
- External performance holds best for strong anatomical signals such as hydronephrosis. For subtle signals such as echogenicity and CKD, expect larger drops, but no CKD-from-ultrasound study with external validation was retrieved.

### Gaps
- Erdman 2024 numbers were not checked against the full text, and the two sources disagree.
- Per-site AUROC numbers in Khondker 2025 appear only in its figures and supplement, which were not read.
- The 2023 narrative review (PMC10943690, Front Oncol) and the QIMS systematic review ([qims.amegroups.org/112984](https://qims.amegroups.org/article/view/112984/html)) were identified but not read. The primary review used here is Zhang Y et al., "Deep learning in renal ultrasound: applications, challenges, and future outlook," Front Oncol 2026;15:1730628, DOI 10.3389/fonc.2025.1730628 ([PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)). That review has reference-numbering errors and unsourced figures (23%, 82%, 40%, 90.2%), so treat its numbers as leads, not facts.
