# Model options for kidney ultrasound: echogenicity grading, patient-level aggregation, video frame selection, lesion detection

Scope note: research done 2026-10-23 with ~15 web tool calls. Items marked **[classic, not re-fetched]** are well-known references cited from prior knowledge with their canonical URL; they were not re-opened in this session. Items marked **[unverified]** need checking before being cited in a paper.

Project context assumed: ~975 B-mode images / ~181 patients (mostly 6 images/patient), single site in Taiwan, CPU or single consumer GPU, Windows. Existing models: ResNet18 / MobileNetV2 / EfficientNet-B3 (ImageNet, 224x224), MLP-ResNet18 (image + age, kidney length, contrast ratio, diabetes), optional CORAL head, K-fold; task = 5-class eGFR.

---

## Q1. Published kidney ultrasound deep learning for CKD/eGFR — architectures, data size, performance, was echogenicity modeled?

### Takeaway
The reference work (Kuo et al. 2019, Taiwan) needed ~4,500 images / ~1,300 patients to reach only r=0.741 for eGFR regression and AUC 0.904 for a **binary** CKD cutoff (eGFR<60); it did not model echogenicity explicitly. The most relevant design for this project is a Korean hybrid pipeline (Mask R-CNN segmentation -> kidney length + kidney/liver echogenicity ratio -> combined with ResNet18), where adding the hand-measured features raised AUROC from 0.81 to ~0.88 and diabetes to ~0.91. With ~181 patients, a 5-class eGFR task is very unlikely to be learnable reliably; eGFR is best demoted to an auxiliary/binary target.

### Cited Findings
- Kuo et al., *npj Digital Medicine* 2019 (China Medical University Hospital, Taichung, Taiwan): 4,505 kidney US images from 1,446 sonographic studies, 1,299 patients (Table 1 says 1,297 — internal inconsistency). — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224)
- Kuo 2019 architecture: ImageNet-pretrained ResNet (Methods say ResNet-101; figure legend inconsistent), regression head 512-512-256 FC, MSE loss, bagging of 10 models; CKD classification by XGBoost on 256-d FC features. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224)
- Kuo 2019 performance: eGFR Pearson r=0.741, MAE 17.6 mL/min/1.73m²; CKD (eGFR<60) accuracy 85.6%, AUC 0.904, specificity up to 92.1% but sensitivity ~60.7%; at a cutoff of 45, accuracy 78%, AUC 0.83. Nephrologists' accuracy was 60.3–80.1%. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224)
- Kuo 2019 used kidney-length annotations only to crop/filter images; for each study the test used the image with the longest kidney-length annotation (a "longest long-axis" rule, same as the clinicians' new request). Echogenicity / cortex-liver comparison was **not** a model input. Test set = 10% of patients split by hashed patient ID. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224)
- Korean study (Severance + Gangnam Severance Hospitals, 2011–2018, 909 patients): Mask R-CNN organ segmentation extracting kidney length and kidney-to-liver echogenicity ratio; ResNet18 CKD vs non-CKD classifier. Image-only AUROC 0.81; + extracted length & echogenicity ~0.88; + diabetes ~0.91. — [Yonsei repository record](https://ir.ymlib.yonsei.ac.kr/handle/22282913/193103) **[the 0.88/0.91 numbers came from a search-engine summary of the abstract; the repository page did not load on direct fetch; journal (reportedly J Digit Imaging) and DOI not verified]**
- A 2025/2026 review of DL in renal ultrasound tabulates CKD/renal-function studies; almost all are single-center, many small: e.g., Tian et al. 2024 (1,049 pts, ResNet34 + GLCM/HOG texture, AUC 0.781–0.931), Chen et al. 2023 (160 pts, radiomics + clinical, fibrosis AUC 0.85), Zhu et al. 2024 (117 pts, SVM on SWE/B-mode/CDFI, IFTA>50% AUC 0.943). The review flagged one study reporting AUC 1.0 (400 pts) as likely overfit. The review reports Kuo 2019 as "AUC 0.904". — [Deep learning in renal ultrasound: applications, challenges, and future outlook (PMC12832298)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- Classic quantitative echogenicity evidence: 197 patients with suspected glomerular disease; kidney/liver echogenicity computed from mean pixel density of renal cortex vs adjacent liver; mean ratio 1.06±0.19, inversely correlated with eGFR at follow-up (r=−0.684, p<0.001). — [Kidney & Blood Pressure Research 2017 (DOAJ)](https://doaj.org/article/da03193e070c494689d7fbbb8ed876df)
- Sonographic kidney measurements predicted histological change and low CKD-EPI eGFR better when weighted toward cortical echogenicity. — [BMC Nephrology 2020 (PMC7137523)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7137523/)
- Computer-based renal/liver echogenicity ratio correlated with IFTA in chronic glomerulopathies; AUC 0.83 for IFTA>50%, 0.95 combined with other findings. — [Siriraj Med J / GMSMJ](https://he02.tci-thaijo.org/index.php/gmsmj/article/view/262871)

### Inferences
- Data scale gap: Kuo used ~25x more images and ~7x more patients than this project and still only reached moderate regression performance and low sensitivity. A 5-class eGFR head on ~181 patients (with likely few patients in <15 and 15–29 classes) will have very wide confidence intervals; per-class metrics will be unstable across folds.
- Echogenicity grade (0–3, relative to liver/spleen) is a better-posed visual target than eGFR because it is defined directly on the image; eGFR is a systemic lab value only partially reflected in B-mode morphology.
- Recommendation on eGFR 5-class: **demote to auxiliary** — keep as (a) a binary eGFR<60 (or <45) secondary endpoint or (b) an auxiliary multi-task head / correlation analysis between predicted echogenicity grade and eGFR; do not make it the primary deliverable. Drop the 5-class head unless the dataset grows to many hundreds of patients with adequate counts per stage.
- The existing MLP-ResNet18 (image + age, length, contrast ratio, diabetes) is conceptually the same as the Korean hybrid — strong evidence to **keep** this design pattern and reuse it for echogenicity grading (with an automatically measured cortex/liver ratio).

### Gaps
- Could not verify full text/journal/DOI of the Korean Mask R-CNN + ResNet18 study.
- Found no published DL study that predicts a clinician-defined 4-level (Grade 0–3) cortical echogenicity score with per-grade probabilities; this appears to be a novel target (no consensus benchmark).
- Inter-observer agreement (kappa) for manual Grade 0–3 echogenicity scoring was not researched here; it bounds achievable model accuracy and should be measured in-house.

---

## Q2. Backbones under small data: ResNet18/EfficientNet vs ConvNeXt, EfficientNetV2, ViT/DINOv2, medical/ultrasound-pretrained (RadImageNet, USFM, etc.)

### Takeaway
Evidence suggests domain-specific pretraining (RadImageNet; ultrasound foundation models such as USFM, TinyUSFM, USF-MAE, UltraDINO) helps on small ultrasound datasets, but no head-to-head on kidney ultrasound with <1,000 images exists. Practical path: keep ResNet18/EfficientNet as baseline, add **one** domain-pretrained candidate (RadImageNet ResNet50/DenseNet, or a frozen DINOv2/ultrasound-FM encoder + linear/logistic head) and compare under the same patient-level K-fold. Large ViTs fine-tuned end-to-end are not justified at this data size.

### Cited Findings
- RadImageNet (radiology-wide pretraining incl. ultrasound) reported, vs ImageNet, AUC improvements of 9.4% for thyroid-nodule US and 4.0% for breast-mass US on small transfer tasks; weights public on GitHub. — [RSNA Imaging AI Atlas card](https://atlas.rsna.org/cards/61caf4ba-8941-4699-9824-9e341d9661b9); [RadImageNet paper record](https://cris.iucc.ac.il/en/publications/radimagenet-an-open-radiologic-deep-learning-research-dataset-for/)
- USFM: ultrasound foundation model trained by masked image modeling in spatial + frequency domains on ~2M ultrasound images. TinyUSFM: distilled version matching USFM with 6.36% of parameters and 6.40% of GFLOPs (200K images used in distillation) — relevant for CPU/consumer GPU. — [TinyUSFM arXiv 2510.19239](https://arxiv.org/html/2510.19239v1)
- USF-MAE: ultrasound-only MAE pretrained on ~370,000 2D/3D US images from 46 open datasets. — [arXiv 2510.22990](https://arxiv.org/pdf/2510.22990)
- UltraDINO (fetal US, DINOv2-style domain pretraining) beat natural-image DINOv2 / iBOT baselines in linear probing, fine-tuning and few-shot settings; a secondary summary claims near full-data performance with 25% of training data on one dataset **[secondary source]**. — [arXiv 2506.19552](https://arxiv.org/pdf/2506.19552)
- DINOv2 on radiology benchmarks (X-ray/CT/MRI, no ultrasound): linear probing on par with or slightly better than supervised methods and better than common supervised CNNs; kNN weaker, attributed to natural→medical domain shift. — [Peng et al., arXiv 2312.02366](https://arxiv.org/pdf/2312.02366)
- Kuo 2019 itself used ImageNet-pretrained ResNet with heavy augmentation and bagging to fight overfitting. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224)
- Seraj et al. 2025 (kidney frame quality, 1,203 frames / 211 patients) compared InceptionV3, EfficientNet, VGG16, ResNet34, ResNet50, YOLOv8x-cls and YOLO11x-cls; YOLO11x-cls best — shows modern pretrained classifiers work at ~1k-image scale for an easier (quality) task. — [Sci Rep 2025, PMC12647705](https://pmc.ncbi.nlm.nih.gov/articles/PMC12647705)

### Inferences
- With ~975 images, variance from fold splits likely exceeds the difference between ResNet18 and ConvNeXt/EfficientNetV2; swapping backbones alone is low-yield. Keep ResNet18 (and EfficientNet-B3) as baselines; **MobileNetV2 can be dropped** unless a deployment-speed requirement exists.
- Best-value experiments: (1) RadImageNet weights for ResNet50/DenseNet121 (drop-in, CNN, Windows-friendly); (2) frozen-feature approach: extract embeddings from DINOv2-S/B or an ultrasound FM (TinyUSFM if weights are available) and train logistic regression / small MLP — low overfitting risk, fast on CPU.
- ROI matters more than backbone: cropping the kidney (as Kuo did) and providing a liver/spleen reference patch is likely more important for echogenicity than the backbone choice (inference, not tested in literature found).

### Gaps
- No direct comparison of RadImageNet vs USFM vs DINOv2 vs ImageNet CNN on kidney US at <1,000 images was found.
- Weight availability and licenses of USFM/TinyUSFM/USF-MAE/UltraDINO not verified (check each repo before planning).
- ConvNeXt / EfficientNetV2 specific small-ultrasound evidence not found in this session.

---

## Q3. Ordinal classification (CORAL vs CORN vs others), calibration, class imbalance

### Takeaway
For a 4-level echogenicity grade (and 5-class eGFR), CORN is a drop-in upgrade to CORAL in the same `coral-pytorch` package and in its authors' benchmarks performed as well or better; plain cross-entropy should remain a baseline. Per-grade probabilities should be post-hoc calibrated (temperature scaling on out-of-fold predictions) and reported with ECE + reliability diagrams.

### Cited Findings
- CORN (Shi, Cao, Raschka; arXiv 2111.08851, revised 2023) achieves rank consistency via conditional training subsets + chain rule, rather than CORAL's weight-sharing constraint in the output layer, which the authors argue limits expressiveness. — [arXiv 2111.08851](https://arxiv.org/abs/2111.08851v5)
- In the CORN paper, CORN outperformed other binary-extension ordinal methods on MORPH-2 and AFAD image datasets and tied OR-NN on a tabular dataset; CORAL performed noticeably worse than OR-NN on balanced MORPH-2/AFAD. Code in the `coral-pytorch` package. — [arXiv 2111.08851](https://arxiv.org/pdf/2111.08851)
- A 2026 paper comparing methods reports CORN had the smallest or comparable MAE/RMSE versus classification, Niu et al.'s ordinal CNN, and CORAL. — [AIME-con 2026 paper](https://aclanthology.org/2026.aimecon-main.55.pdf) **[domain is not imaging]**
- Temperature scaling (single scalar on logits, fit on held-out data) is a simple and effective post-hoc calibration method for modern NNs; ECE is the standard metric. — [Guo et al. 2017, arXiv 1706.04599](https://arxiv.org/abs/1706.04599) **[classic, not re-fetched]**
- MIL calibration: attention-based aggregators gave stronger discrimination but more overconfident predictions in ultrasound diagnosis; simpler instance-level methods gave more reliable risk estimates at a modest cost in classification metrics (MICCAI 2025). — [MICCAI 2025 paper 4101](https://papers.miccai.org/miccai-2025/paper/4101_paper.pdf)

### Inferences
- CORAL/CORN output cumulative P(y>k); per-grade probabilities = differences of cumulative probabilities (CORN guarantees non-negative via chain rule). For a UI showing "P(Grade 0..3)", CE+softmax gives this directly and is easiest to calibrate; ordinal heads give better MAE / fewer off-by-2 errors. Recommend: run CE, CORAL, CORN under same folds; report accuracy, MAE, quadratic weighted kappa, ECE.
- Temperature scaling for CORAL/CORN must be applied to the K−1 binary logits (shared T); fit T on out-of-fold predictions (nested in K-fold) to avoid leakage.
- Class imbalance (Grade 3 and eGFR<15 likely rare): use class-weighted loss or balanced sampling, stratified-by-patient folds (StratifiedGroupKFold), and report per-class recall. Avoid oversampling at image level across folds of the same patient.

### Gaps
- No kidney-ultrasound-specific comparison of ordinal losses was found.
- Other ordinal losses (e.g., soft ordinal labels / SORD, ordinal-aware CE, earth mover's distance loss) were not researched in this session.

---

## Q4. Explainable alternative: segmentation + grayscale ratio + rules/logistic regression vs end-to-end CNN vs hybrid

### Takeaway
There is direct published support for both the quantitative ratio (kidney/liver mean pixel density correlates with eGFR and histology) and the hybrid design (segmentation-derived length + echogenicity ratio added to a CNN improved AUROC 0.81→~0.88). For Grade 0–3 relative to liver/spleen, the recommended architecture is **hybrid**: segment kidney cortex + liver/spleen ROI → compute ratio (and texture stats) → logistic/ordinal regression baseline, plus a CNN branch, fused in the existing MLP-ResNet18 framework.

### Cited Findings
- Kidney/liver mean pixel-density ratio measured in 197 patients, inversely correlated with eGFR (r=−0.684). — [DOAJ, Kidney Blood Press Res 2017](https://doaj.org/article/da03193e070c494689d7fbbb8ed876df)
- Renal/liver echogenicity ratio correlated with IFTA; AUC 0.83 (IFTA>50%), 0.95 combined. — [GMSMJ](https://he02.tci-thaijo.org/index.php/gmsmj/article/view/262871)
- Korean hybrid: Mask R-CNN extracts kidney length + kidney/liver echogenicity ratio; adding these to ResNet18 raised AUROC 0.81 → ~0.88 (+diabetes ~0.91). — [Yonsei repository](https://ir.ymlib.yonsei.ac.kr/handle/22282913/193103) **[performance numbers from search summary; unverified]**
- Kidney segmentation in US is mature: e.g., Fast-UNet++ (744 images, 3 centers) DSC >95% and directly predicts length, width, thickness, volume (Oghli 2024); multiscale CNN 7,350 images DSC 95.86%; YSegNet 700 images DSC 97%. — [Review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- Tian et al. 2024 combined ResNet34 deep features with GLCM/HOG texture (1,049 pts, AUC 0.781–0.931) — another hybrid deep + handcrafted example. — [Review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)

### Inferences
- Grayscale ratios are sensitive to gain, depth, TGC, focal zone and machine; the ratio should use ROIs at similar depth (cortex and adjacent liver/spleen in the same image), which matches the clinical definition. Machine/preset should be recorded and used as covariate.
- Explainability for clinicians: the ratio + ROI overlay is directly auditable; a CNN Grad-CAM is not. A logistic/ordinal regression on (ratio, ratio texture stats) gives a transparent baseline that the CNN must beat to justify itself.
- Segmentation also yields kidney length (the later "measure length" requirement) — one U-Net-family model serves both needs. Annotating ~150–300 images with kidney contour + one liver/spleen ROI is likely enough to train a usable segmenter given the reported DSCs (inference).

### Gaps
- No published ML model directly predicting a Grade 0–3 score from the ratio; thresholds for grade boundaries must be learned locally.
- Reproducibility of pixel-ratio across machines/presets not quantified in the sources found.

---

## Q5. Patient-level aggregation (MIL / attention-MIL / pooling / voting)

### Takeaway
Attention-based MIL is used for patient-level ultrasound diagnosis (thyroid, echocardiography), but with only ~181 bags, attention MIL is prone to attending to wrong images and to overconfidence. Start with simple, calibrated aggregation (mean of per-image probabilities or mean of logits, optionally side-specific: right-kidney images vs liver, left vs spleen), and treat ABMIL as an experiment.

### Cited Findings
- Thyroid (AMIA 2023): multi-scale attention MIL over US frames, patient-level malignancy AUROC 0.785 vs 0.667 for clinical-features baseline. — [UT Southwestern record](https://utsouthwestern.elsevierpure.com/en/publications/patient-level-thyroid-cancer-classification-using-attention-multi); [eScholarship](https://escholarship.org/uc/item/01z594pc)
- Aortic stenosis from multi-view echo (MLHC 2023): standard attention MIL attended to irrelevant instances; fixed with supervised attention toward relevant views + study-level self-supervised pretraining. — [arXiv 2306.00003](https://arxiv.org/html/2306.00003v3)
- MICCAI 2025: attention aggregators → better discrimination but worse calibration in ultrasound; instance-level methods more reliable risk estimates. — [MICCAI 2025 paper 4101](https://papers.miccai.org/miccai-2025/paper/4101_paper.pdf)
- Pediatric CAKUT vs hydronephrosis multi-view multi-instance DL: AUC 0.961, 157 children (Yin et al. 2020). — [Review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- Kuo 2019 avoided aggregation by choosing one image per study (longest kidney length) at test time. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224)
- ABMIL (gated attention pooling) original method. — [Ilse et al. 2018, arXiv 1802.04712](https://arxiv.org/abs/1802.04712) **[classic, not re-fetched]**

### Inferences
- Important structural point: echogenicity grade is per kidney (right vs liver, left vs spleen); a patient has two kidneys that may differ. Aggregate **per kidney side** first, then define the patient result (e.g., max grade or report both). Confirm with clinicians.
- Recommended order: (1) mean of per-image calibrated probabilities (ordinal-aware: average cumulative probabilities); (2) quality-weighted mean using the frame-quality score from Q6; (3) ABMIL with attention supervision from quality labels — only if (1)/(2) plateau. Majority voting discards probability info and is poorly suited to 4-level probabilities.
- Evaluate at patient level with patient-grouped folds; image-level metrics overstate performance due to correlated images.

### Gaps
- No kidney-ultrasound-specific MIL study for CKD/echogenicity found.

---

## Q6. Video: keyframe / standard-plane detection, image quality assessment

### Takeaway
A directly relevant 2025 *Scientific Reports* kidney study (Seraj et al.) classifies each video frame as Good/Bad/Null with YOLO11x-cls (5-fold patient-wise CV, mean acc 90%), but it does not choose a single best frame or enforce long-axis. For "pick the longest long-axis view", combine a frame-quality/view classifier with the kidney segmenter (from Q4) and select the frame maximizing measured kidney length among good-quality frames — exactly the rule Kuo 2019 used on stills.

### Cited Findings
- Seraj et al., *Sci Rep* 2025;15:41940 (doi 10.1038/s41598-025-25755-1): 1,203 labeled frames from 211 patients (DICOM videos, 30–800 frames each); labels Good 448 / Bad 354 / Null 401; compared InceptionV3, EfficientNet, VGG16, ResNet34, ResNet50, YOLOv8x-cls, YOLO11x-cls; YOLO11x-cls best; test F1 Good 100%, Bad 92%, Null 94% (text says 86%/89% — inconsistency); 5-fold patient-wise CV mean acc 90% ± 5.9%. No long-axis criterion; no rule for choosing one frame among several Good frames. Code/data on request only (non-commercial); link via github.com/am-a-s/Kidney-ultrasound-cls. — [PMC12647705](https://pmc.ncbi.nlm.nih.gov/articles/PMC12647705); [JoVE summary](https://visualize.jove.com/41290740)
- SonoNet (Baumgartner et al., IEEE TMI 2017): real-time detection of 13 fetal standard planes with weakly supervised localization; F1 0.798 real-time, 90.09% accuracy retrieving frames from saved videos, 77.8% localization accuracy. — [arXiv 1612.05601](https://arxiv.org/pdf/1612.05601); [PMC6051487](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6051487/)
- 2025 French doctoral thesis on video-based liver/kidney US diagnosis includes a relevant-frame assessor. — [Unistra thesis PDF](https://publication-theses.unistra.fr/public/theses_doctorat/2025/SAIBRO_Guinther_2025_ED269.pdf) **[not read in detail]**
- Kuo 2019 selected per study the image with the longest annotated kidney length. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224)
- Renal artery Doppler sampling-position selection with object detection (Sci Rep 2024). — [PMC11116437](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11116437/)

### Inferences
- Suggested pipeline for 3–5 min videos: subsample (e.g., 2–5 fps) → lightweight quality/view classifier (Good long-axis / other view / no kidney; ResNet18 or MobileNet is sufficient, avoids AGPL) → kidney segmentation on Good frames → compute long-axis length → pick top-k frames by length (k=5–8 to feed the MIL/mean aggregator) with temporal non-max suppression to avoid near-duplicate frames.
- Labeling cost is modest: Seraj used ~1.2k labeled frames; ~1k frames from this site's videos is a reasonable first target (inference).
- Selected frames from video are a different distribution from sonographer-saved stills (motion blur, unfrozen gain); validate the downstream grader on video-derived frames before trusting it.

### Gaps
- No published kidney study explicitly detecting "longest long-axis" frame in video was found; method must be built locally.
- Video duration and frame-rate handling details absent in Seraj paper.

---

## Q7. Lesion detection: cysts, stones, hydronephrosis

### Takeaway
Published kidney-US lesion work is fragmented: mostly single-condition, single-center, some with implausibly high accuracy (99.8%) and no widely used public multi-lesion US benchmark. Hydronephrosis is best framed as image/kidney-level classification (or grading); cysts as segmentation/detection; stones (small echogenic foci with shadowing) as detection with low expected performance on small data. Plan this as a later phase requiring new annotations.

### Cited Findings
- Taiwanese hydronephrosis study: 3,462 US frames from 97 hydronephrosis patients (expert-confirmed) + 265 controls; YOLOv4 for background removal then U-Net variants; Res-UNet 94.6% accuracy for moderate/severe hydronephrosis. — [NTU scholars record](https://scholars.lib.ntu.edu.tw/signposting/describedby/5a4de7c8-4f8e-4b81-b034-92d55be488fe) **[details from search summary]**
- Hydronephrosis DCNN on a public dataset (1,057 images), accuracy 99.8% — flagged by a review as unusually high. — [PMC11636695 (PeerJ CS 2024)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11636695/); [Review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- Stones in US: thesis comparing YOLO-NAS, YOLOv8, YOLOv5, Detectron2 Faster R-CNN on 135 normal + 495 stone images; YOLO-NAS best, 86.7% mAP. — [Jimma University repository](https://repository.ju.edu.et/handle/123456789/9150) **[thesis, not peer reviewed]**
- Renal cysts: YOLOv5 detection + UNet++ landmarks (Healthcare 2023). — [DOAJ Healthcare 2023](https://doaj.org/article/7a11e307ad674da8bfc5db3836ca0129)
- Multi-pathology URI-CADS (multitask ResNet-50 + Mask R-CNN), 1,985 images, AUC 0.819; pediatric abnormalities ResNet-50 1,599 images AUC 0.959; 4-class public dataset (4,940 images) ensemble 96.54%. — [Review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- Large stone/cyst/tumor dataset with YOLOv8 (12,446 images) is **CT**, not US: accuracy 82.52%. — [IEEE Access 2024 (DOAJ)](https://doaj.org/article/c3c13ffafa0a4632a0553940cd8933ba)
- The review notes several "public datasets" but does not name a standard kidney-US lesion benchmark. — [Review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)

### Inferences
- Many popular "kidney stone/cyst" Kaggle datasets are CT; beware mixing modalities when searching for pretraining data.
- Reported 96–99.8% accuracies on public sets likely reflect leakage or easy splits; expect much lower on a local single-site set.
- Suggested approach: hydronephrosis = kidney-level classifier (reuse classification backbone; grade per SFU/clinician scale); cysts = segmentation (U-Net family shared with kidney segmenter, add a cyst class); stones = detector (RT-DETR / Faster R-CNN / YOLO) only after collecting enough positive cases.

### Gaps
- No verified public kidney-US dataset with bounding boxes for cysts + stones + hydronephrosis was found.
- YOLOv11 stones/cysts paper results were truncated in search results.

---

## Q8. Practicality: compute, licensing, Windows

### Takeaway
Everything recommended (ResNet18/50, U-Net, logistic regression, mean/ABMIL aggregation, frozen DINOv2-S features) runs on CPU or one consumer GPU on Windows. The main licensing risk is Ultralytics YOLO (AGPL-3.0; Enterprise license needed for proprietary/commercial/SaaS use); Apache-2.0 alternatives exist (RT-DETR, RF-DETR, torchvision detectors).

### Cited Findings
- Ultralytics: AGPL-3.0 (requires open-sourcing) or paid Enterprise License for commercial products, proprietary software, SaaS, embedded; pricing per deployment, not public. — [Ultralytics license page](https://ultralytics.com/license); [Request license](https://www.ultralytics.com/request-license)
- RT-DETR released by Baidu (April 2023) under Apache-2.0; RT-DETRv2 HF mirror also Apache-2.0. RF-DETR (Roboflow, March 2025) Apache-2.0. YOLO-NAS weights have a separate non-commercial license. — [Roboflow RT-DETR page](https://playground.roboflow.com/models/baidu/rt-detr); [HF rtdetr-v2-r18vd](https://huggingface.co/zeromodels/rtdetr-v2-r18vd); [RF-DETR vs RT-DETR](https://playground.roboflow.com/models/compare/rf-detr-vs-rt-detr) **[aggregator sources; verify LICENSE files]**
- A search summary claimed RTMDet is GPL-3.0 — **likely incorrect / unverified**: RTMDet is distributed in OpenMMLab MMDetection, which is (to my knowledge) Apache-2.0; check the repo LICENSE.
- Seraj 2025's best kidney frame model is YOLO11x-cls (Ultralytics → AGPL implications if reused). — [PMC12647705](https://pmc.ncbi.nlm.nih.gov/articles/PMC12647705)
- TinyUSFM targets resource-constrained settings (6.4% of USFM GFLOPs). — [arXiv 2510.19239](https://arxiv.org/html/2510.19239v1)

### Inferences
- For an academic, non-distributed research prototype, AGPL is usually workable; if the system will be delivered to a hospital as a closed product or service, avoid Ultralytics or budget for the Enterprise license. For frame-quality classification, a torchvision ResNet/EfficientNet (BSD) is a license-clean substitute for YOLO11-cls.
- Windows: PyTorch + torchvision + timm + segmentation_models_pytorch + coral-pytorch all work on Windows; avoid pipelines that need Linux-only CUDA extensions (e.g., some MMCV ops / deformable attention builds) (inference from general experience, unverified here).

### Gaps
- License text of USFM/TinyUSFM/RadImageNet weights not verified.
- No measured CPU inference times for these models on the target hardware.

---

## Summary recommendation table (synthesized from the above; inference)

| Component | Recommendation |
|---|---|
| ResNet18 (ImageNet) | **Keep** as baseline; fine-tune for echogenicity Grade 0–3 on kidney-cropped ROI |
| EfficientNet-B3 | **Keep** as second baseline (or replace with RadImageNet-pretrained CNN) |
| MobileNetV2 | **Drop** unless deployment speed needed |
| MLP-ResNet18 (image + clinical) | **Keep and repurpose** — add auto-measured cortex/liver(spleen) ratio + length; aligns with Korean hybrid evidence |
| CORAL head | **Fine-tune/compare**: add CORN and plain CE; pick by MAE/QWK/ECE; add temperature scaling |
| New: kidney + liver/spleen segmentation (U-Net family) | **Add** — enables ratio features, length measurement, ROI cropping, frame selection |
| New: frame quality/view classifier + longest-length rule | **Add** (ResNet18-level classifier; avoid AGPL if distributing) |
| Patient aggregation | Mean of calibrated per-image probabilities per kidney side first; ABMIL as experiment |
| Domain-pretrained backbones (RadImageNet, DINOv2/US-FM frozen features) | **Experiment**, not default |
| Lesion detection | Later phase; hydronephrosis classification, cyst segmentation, stone detection with Apache-2.0 detector |
| eGFR 5-class | **Demote to auxiliary** (binary eGFR<60 or correlation with grade); drop 5-class as primary |
