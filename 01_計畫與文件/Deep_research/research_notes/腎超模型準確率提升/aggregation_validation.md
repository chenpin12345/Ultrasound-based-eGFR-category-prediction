# Multi-image aggregation, ensembling, calibration, and rigorous validation for small medical imaging datasets (kidney US, ~180 patients x ~6 images)

Legend: **[US]** = ultrasound-specific evidence; **[GEN]** = general ML / other modality.
Sources marked "(classic; not re-fetched this session)" are well-established methodology papers cited from standard knowledge; their URLs point to the canonical record but specific numbers were not re-verified in this session. All other findings were retrieved in this session (some via search-engine summaries of abstracts, flagged where relevant).

Project anchor numbers (for the inferences below): ~180 patients; fixed 20% test ≈ 36 patients (≈72 kidneys if both sides graded); 5-fold CV on ≈144 patients → ≈29 patients per validation fold.

---

## Q1. Multi-image per patient: mean vs max vs best-view selection vs attention MIL

### Takeaway
The only kidney-US study found that directly reports per-subject aggregation (Yin et al. 2020) shows bagging all images with **mean pooling** raised AUC from ~0.80 (single image) to ~0.95–0.96, and mean beat max. Attention MIL is used in thyroid/breast US but no controlled attention-vs-mean ablation on US was found; with ~6 images x ~180 patients, mean of per-image probabilities (or mean of per-image features) is the evidence-supported default, with attention MIL as an exploratory ablation.

### Cited Findings
- **[US, kidney]** Yin et al., *Urology* 2020: 86 PUV cases vs 71 controls (pediatric), 3,504 sagittal + 2,558 transverse images, 5-fold CV. Each subject's images form a bag; per-image CNN probabilities are pooled. Results (mean ± SD across folds): sagittal single-image AUC 0.796 ± 0.064; transverse single-image 0.815 ± 0.071; sagittal MIL (mean pooling) 0.949 ± 0.035; transverse MIL 0.954 ± 0.033; multi-view MIL 0.961 ± 0.026 (accuracy 0.925). Authors state "the mean pooling operator led to better classification performance" than max (max numbers only in supplement). No attention pooling tested. — [Yin et al. 2020, PMC7387180](https://pmc.ncbi.nlm.nih.gov/articles/PMC7387180)
- **[US, kidney]** Multi-view vs single-view MIL gain (0.949/0.954 → 0.961) is within fold SD, i.e., modest; the big jump is single-image → bag-level aggregation. — [Yin et al. 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7387180)
- **[US, kidney]** Kuo et al. 2019 (npj Digital Medicine): ResNet transfer learning on 4,505 kidney US images with eGFR-derived labels; CKD classification accuracy 85.6% vs 60.3–80.1% for nephrologists. — [Kuo et al. 2019, PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **[US, kidney]** Multimodal US (grayscale + SMI + strain elastography) for early CKD fibrosis: single-mode AUCs 0.682/0.745/0.648 vs fused 0.86 (Renal Failure 2024) — evidence that combining complementary views/modalities per patient helps. — [PMC11497579](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11497579/)
- **[US, thyroid]** Patient-level attention MIL fusing multi-scale features from all frames of a patient's scan: AUROC 0.785 vs 0.667 for a clinical-feature baseline (comparison is against clinical features, not against mean pooling). — [Patient-level thyroid attention MIL, PMC10785838](https://pmc.ncbi.nlm.nih.gov/articles/PMC10785838) / [eScholarship](https://escholarship.org/uc/item/01z594pc)
- **[US, thyroid]** Multi-instance CNN for thyroid nodule risk treats each patient's image set as a bag; lists global average, max, and attention as standard aggregators. — [PMC12330392](https://pmc.ncbi.nlm.nih.gov/articles/PMC12330392/)
- **[US, echo]** EchoNet-Dynamic (Nature 2020) predicts EF beat-by-beat and aggregates across cardiac cycles; MAE 4.1% internal, 6.0% external; Dice 0.92 for LV segmentation; variance comparable to or lower than human experts. (Exact per-beat averaging gain not extracted.) — [Ouyang et al. 2020, PubMed 32269341](https://pubmed.ncbi.nlm.nih.gov/32269341/)
- **[GEN]** Attention-based deep MIL (Ilse et al. 2018) motivates attention as a trainable pooling vs non-trainable mean/max. — [arXiv 1802.04712](https://arxiv.org/pdf/1802.04712)
- **[GEN, histopathology]** Mean pooling weights instances equally (can dilute sparse positive signal); max pooling is sensitive to outliers. — [arXiv 2003.00823](https://arxiv.org/pdf/2003.00823)

### Inferences
- For kidney grading (a diffuse parenchymal property — echogenicity, cortical thickness, size), the signal is present in most images, not sparse; this favors **mean** (or trimmed/median) over max. Max is appropriate for focal findings (e.g., a single hydronephrosis/stone frame), not diffuse grades.
- **Best-view selection (longest long-axis)**: no comparative study was found. It is biologically sensible for length-based features (kidney length is defined on the maximal longitudinal view) but discards information for texture/echogenicity features. Practical protocol: compute **length features from the best long-axis view** (max length across images per kidney) and **texture/echogenicity features as the mean (or median) across images**; compare against "mean everything" in the ablation.
- **Attention MIL** with ~144 training patients is high-variance; treat as an ablation arm and require it to beat mean pooling by more than the paired-bootstrap CI (see Q6) before adopting.
- Aggregate **per kidney** (left/right separately) since grades may be asymmetric; keep both kidneys of a patient in the same split.
- For ordinal outputs, aggregate **probabilities** (mean of the 4-class probability vectors, or of cumulative P(grade ≥ k)), then take the argmax/expected grade — not the mean of hard labels.

### Gaps
- No controlled US study comparing mean vs max vs attention vs best-view on the same data with numbers (Yin's max results are in a supplement not retrieved).
- No kidney-grading-specific (ordinal 0–3) aggregation study found.

---

## Q2. Gains from K-fold ensembles, multi-seed averaging, TTA in small medical datasets

### Takeaway
Fold-ensembling is the default in nnU-Net and won KiTS19, but gains are usually small and not always present; seed variance is real but smaller than data-sampling variance. TTA can improve net accuracy while flipping some correct predictions; its benefit depends on aggregation. Expect low-single-digit point gains at best — smaller than the test-set CI for 36 patients.

### Cited Findings
- **[GEN]** Bouthillier et al. (MLSys 2021): modeled variance across data sampling, augmentation, initialization, dropout, data order (200 runs per source). **Data bootstrap is the largest source of variance; model initialization typically <50% of bootstrap variance.** Randomizing more sources of variation approximates the ideal estimator at ~51x lower compute. — [Bouthillier et al. 2021, arXiv 2103.03098](https://arxiv.org/abs/2103.03098)
- **[GEN, segmentation]** nnU-Net trains 5 fold models and averages their softmax at inference by default; KiTS 2019 winning entry averaged 5 fold models. — [nnU-Net arXiv 1809.10486](https://arxiv.org/pdf/1809.10486); [nnU-Net BraTS arXiv 2011.00848](https://arxiv.org/pdf/2011.00848)
- **[GEN]** Fold ensembles are not equivalent to deep ensembles: each member sees a different data subset, so disagreement conflates epistemic uncertainty with data-exposure variability (2026 preprint). — [Lost in the Folds, arXiv 2605.18329](https://arxiv.org/pdf/2605.18329)
- **[GEN]** Reports exist where fold ensembles combined with other configurations did not outperform a single strong baseline on all labels (pediatric brain tumor). — [arXiv 2410.14020](https://arxiv.org/pdf/2410.14020)
- **[GEN]** TTA (Shanmugam et al., ICCV 2021): even when TTA yields a net accuracy gain, it changes many correct predictions to incorrect; simple averaging is sometimes suboptimal; learned aggregation improves consistently. — [Shanmugam et al. 2021, CVF](https://openaccess.thecvf.com/content/ICCV2021/html/Shanmugam_Better_Aggregation_in_Test-Time_Augmentation_ICCV_2021_paper.html)
- **[GEN, medical]** Ayhan et al. (diabetic retinopathy): median of 128 augmented forward passes gave the best-calibrated results (as summarized in a systematic review). — [JMIR Med Inform 2022 review](https://medinform.jmir.org/2022/8/e36427)
- **[GEN]** Deep ensembles (Lakshminarayanan et al. 2017) improve accuracy and uncertainty quality over single nets. (classic; not re-fetched this session) — [arXiv 1612.01474](https://arxiv.org/abs/1612.01474)

### Inferences
- In this pipeline, the 5 CV fold models are a "free" ensemble for the held-out test set: average the 5 fold models' probabilities on the test set (both segmentation and the downstream grader). Expected gain is small; report it as an ablation (single full-train model vs 5-fold ensemble) with a paired bootstrap CI.
- Because seed variance < data variance (Bouthillier), report results over **≥5 seeds × repeated CV**, and do not claim a model improvement smaller than the seed-to-seed SD.
- For US, use only physically plausible TTA (small intensity/gain change, small rotation/scale, horizontal flip only if laterality-invariant). Multi-image aggregation already acts like "natural TTA" (6 different views), so incremental TTA gains are likely smaller than in single-image settings.

### Gaps
- No small-dataset medical *classification* study with a direct fold-ensemble vs single-model AUC delta was found.
- No ultrasound-specific TTA delta found.

---

## Q3. Calibration: temperature scaling, ECE, reliability diagrams for ordinal outputs; ensembles' effect

### Takeaway
Temperature scaling (1 parameter) is the strong cheap baseline; in a small medical example it halved ECE and matched an ensemble. With tiny calibration sets, even 1-parameter scaling can overfit (BloodMNIST: only 11 ensemble errors in validation made calibrated ensemble worse). ECE itself is very noisy at n≈36–72 test kidneys; report Brier/ranked probability score with bootstrap CIs alongside reliability diagrams.

### Cited Findings
- **[GEN, medical small data]** DermaMNIST (ResNet-18): one validation-fitted temperature halved single-model ECE 5.1% → 2.3%; calibrated single model ≈ ensemble (2.3% vs 2.5%). On BloodMNIST, temperature-scaling the ensemble made test NLL and ECE slightly *worse* because the validation set contained only 11 ensemble errors. (GitHub project, not peer-reviewed.) — [medical-image-uncertainty repo](https://github.com/ChetanYarlagadda/medical-image-uncertainty)
- **[GEN, radiology]** TTA for black-box radiology AI: deep ensembles improved ECE and Brier vs no TTA; TTA calibration gains depend on aggregation method and are not automatic. — [arXiv 2609.29931](https://arxiv.org/pdf/2609.29931)
- **[GEN]** Guo et al. 2017: modern deep nets are miscalibrated; temperature scaling (single scalar on logits, fit on validation NLL) is a simple, effective post-hoc fix and does not change argmax accuracy. (classic; not re-fetched this session) — [arXiv 1706.04599](https://arxiv.org/abs/1706.04599)
- **[GEN]** Ovadia et al. 2019: deep ensembles were the most robustly calibrated method under dataset shift; temperature scaling calibrated in-distribution but degraded under shift. (classic; not re-fetched this session) — [arXiv 1906.02530](https://arxiv.org/abs/1906.02530)
- **[GEN]** Survey: ensembles need multiple trained models; MC dropout/TTA need repeated inference. — [MDPI J Imaging survey](https://www.mdpi.com/2313-433X/12/8/341)

### Inferences (practical protocol for ordinal 0–3)
- **Fit temperature on out-of-fold (OOF) CV predictions** of the 144 development patients (≈ 144×2 kidneys), never on the test set. Apply the single T to test predictions (or to the averaged fold-ensemble logits; refit T for the ensemble since averaging changes sharpness).
- **Ordinal calibration views**: (a) multiclass top-label ECE + classwise ECE; (b) **cumulative calibration**: for k=1,2,3 plot reliability of P(grade ≥ k) — three binary reliability diagrams, which map to clinically meaningful thresholds (e.g., "≥ grade 2"); (c) **Ranked Probability Score (RPS)** as the proper scoring rule for ordinal outcomes, plus Brier.
- With ~72 test kidneys, use ≤5 equal-mass bins (or a smoothed/LOESS reliability curve) and bootstrap ECE by patient; a 10-bin ECE on 72 samples is dominated by noise.
- Ordinal models (CORAL/CORN/cumulative-link) produce cumulative probabilities that can be temperature-scaled at the shared logit; ensure monotonicity P(≥1) ≥ P(≥2) ≥ P(≥3) after calibration.

### Gaps
- No ultrasound- or ordinal-specific calibration study with numbers found in this session.
- ECE minimum-sample guidance for n<100 not found in a primary source.

---

## Q4. Data leakage types and quantified impact

### Takeaway
Leakage via patient/subject overlap and via feature selection is the dominant inflator; reported inflation ranges from ~0.04 AUROC to ~9–28 accuracy points, and is worse in small datasets. A kidney-CT stone study measured 0.905 → 0.991 accuracy from image-level splitting — directly analogous to this project's old system.

### Cited Findings
- **[GEN]** Kapoor & Narayanan (Patterns 2023): 8-type leakage taxonomy (incl. no train/test split, preprocessing on train+test, feature selection on train+test, duplicates, illegitimate features, temporal leakage, non-independence between train/test, sampling bias); leakage found in 17 fields affecting 294 papers (Patterns version; preprint said 329); project page (May 2024) lists 648 papers across 30 fields. Proposes "model info sheets". — [Kapoor & Narayanan 2023, PMC10499856](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856); [project page](https://reproducible.cs.princeton.edu/)
- **[GEN, medical imaging]** Varoquaux & Cheplygina (npj Digit Med 2022), "How I failed machine learning in medical imaging": reviews dataset, evaluation, and publication pitfalls; notes many challenge submissions differ by less than evaluation noise. — [arXiv 2103.10292](https://arxiv.org/abs/2103.10292v1); DOI 10.1038/s41746-022-00592-y
- **[GEN]** Varoquaux 2018 (NeuroImage): CV with ~100 samples gives error bars of about **±10%**; standard error across folds strongly underestimates true uncertainty. — [arXiv 1706.07581](https://arxiv.org/pdf/1706.07581)
- **[GEN, MRI]** Wen et al. (Medical Image Analysis 2020): data leakage potentially present in about half of 32 surveyed AD-CNN studies; simulated leakage gave validation balanced accuracy 1.00 vs 0.75 (ADNI test) / 0.80 (AIBL test). Slice-level (2D) approaches are especially prone. — [Wen et al., arXiv 1904.07773](https://arxiv.org/pdf/1904.07773)
- **[GEN, connectomics]** Rosenblatt et al. (Nat Commun 2024): of 5 leakage types, **feature-selection leakage and repeated-subject leakage drastically inflate** performance; others minor; **small datasets exacerbate** leakage effects. — [PMC10901797](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10901797/)
- **[GEN, kidney CT]** Kidney stone detection preprint, 201 patients/3 centers, 3,364 original + 35,457 augmented images: patient-wise split accuracy 0.905 / AUC 0.946 vs image-level split 0.991 / 0.999 (~9-point inflation, consistent across seeds). Augmented copies of the same image in train and test is a near-duplicate leak. (Preprint; abstract-level numbers.) — [Research Square rs-10604877](https://www.researchsquare.com/article/rs-10604877/latest)
- **[GEN, leukemia cells]** Random vs subject-disjoint split inflates AUROC by ~0.04 even with frozen features; malaria cell-level vs patient-level accuracy fell 96.90% → 78.00% in one prior study (as cited in preprints). — [arXiv 2606.24944](https://arxiv.org/pdf/2606.24944); [arXiv 2608.24793](https://arxiv.org/pdf/2608.24793)
- **[GEN, dental X-ray]** Image-level random split puts the same patient's images in train and test and inflates performance. — [arXiv 2609.14703](https://arxiv.org/pdf/2609.14703)

### Inferences (checklist for this project)
1. **Patient overlap**: split by patient ID (both kidneys, all images, all visits). Use `GroupKFold`/`StratifiedGroupKFold` with groups=patient. Old system's image-level split is the classic ~10-point inflator.
2. **Near-duplicates / video frames**: consecutive cine frames or re-acquired images of the same kidney are near-duplicates; deduplicate by perceptual hash and keep groups at patient level anyway. Never augment before splitting.
3. **Label in filename/metadata**: strip grade from filenames, DICOM descriptions, burned-in annotations/calipers text; audit by training a model on metadata only (filename tokens, image size, machine ID) — if it predicts grade above chance, there is a shortcut.
4. **Preprocessing before split**: normalization stats, PCA, feature selection, SMOTE, imputation must be fit inside each training fold (sklearn `Pipeline`).
5. **Tuning on test**: the fixed 20% test is touched once; all hyperparameter/aggregation/threshold choices are made with CV on the 80%. Log each test evaluation.
6. **Segmentation leakage**: segmentation model used to make features for a patient must not have been trained on that patient (see Q5).

### Gaps
- No ultrasound-specific (kidney US) quantified leakage study found; the closest is kidney CT (preprint).

---

## Q5. Cross-fitting: why downstream models need features from out-of-fold predicted masks

### Takeaway
Training the grader on features from ground-truth masks (or from masks predicted by a segmenter that saw those patients) creates a train/test distribution mismatch and optimistic bias; standard stacking theory and scikit-learn's stacking implementation both require the second stage to be trained on **out-of-fold** first-stage predictions.

### Cited Findings
- **[GEN]** scikit-learn: in stacking, base estimators are fit on full training data for inference, but "To generalize and avoid over-fitting, the `final_estimator` is trained on out-samples using `sklearn.model_selection.cross_val_predict` internally." — [scikit-learn ensemble docs §1.11.6](https://scikit-learn.org/stable/modules/ensemble.html)
- **[GEN]** Wolpert 1992, "Stacked generalization": level-1 learner trained on level-0 predictions on held-out partitions. (classic; not re-fetched this session) — [Neural Networks 5(2):241–259](https://doi.org/10.1016/S0893-6080(05)80023-1)
- **[GEN]** Chernozhukov et al. 2018, Double/debiased ML: cross-fitting (estimate nuisance models on other folds, evaluate on held-out fold) removes overfitting bias of first-stage ML estimates. (classic; not re-fetched this session) — [Econometrics Journal, arXiv 1608.00060](https://arxiv.org/abs/1608.00060)
- **[GEN]** Kapoor & Narayanan classify using information at training time that won't be available at deployment as leakage ("illegitimate features"). — [PMC10499856](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856)

### Inferences (protocol)
- At deployment, features come from **predicted** masks (with their errors). If the grader is trained on GT-mask features, it learns a cleaner feature distribution than it will see; if trained on in-sample predicted masks (segmenter trained on the same patients), masks are near-perfect and the same bias occurs.
- **Cross-fitting scheme** (nested in the 5-fold CV of the 144 dev patients):
  1. For outer fold f: train segmenter on the other 4 folds' patients; predict masks for fold f → OOF masks for all 144 dev patients.
  2. Compute features from OOF masks → train/evaluate grader in the same folds (grader for fold f trained on OOF features of other folds, which were produced by segmenters that didn't see those patients — strictly, use an inner cross-fit or accept the mild approximation that all OOF features are "held-out quality").
  3. For the test set: masks from the 5-fold segmenter ensemble (or a segmenter retrained on all 144) → features → grader trained on all 144 OOF features.
- Ablation to show the effect: grader trained on (a) GT-mask features, (b) in-sample predicted-mask features, (c) OOF predicted-mask features, all evaluated on test features from predicted masks. Expectation: (a)/(b) give optimistic CV but worse/equal test vs (c).
- Optionally also train on GT + OOF features (augmentation) but always evaluate on predicted-mask features.

### Gaps
- No medical-imaging paper found in this session that quantifies the GT-mask vs OOF-mask feature gap (radiomics "auto vs manual segmentation" literature exists but was not retrieved).

---

## Q6. Comparing models with small data: repeated CV, seeds, patient-level bootstrap, tests, minimum detectable differences

### Takeaway
At 36 test patients, a single-test-set accuracy has a 95% CI of roughly ±15 points; differences of a few points between pipelines are undetectable there. Use repeated grouped CV on the dev set with the Nadeau–Bengio corrected t-test, paired patient-level bootstrap on the test set, and report CIs rather than p-values alone.

### Cited Findings
- **[GEN]** ~100 samples → CV error bars ≈ ±10%; across-fold SE underestimates the true variance. — [Varoquaux 2018, arXiv 1706.07581](https://arxiv.org/pdf/1706.07581)
- **[GEN]** Data-sampling variance dominates seed variance; randomizing more variance sources (data splits + seeds) gives better comparisons at lower cost. — [Bouthillier et al. 2021](https://arxiv.org/abs/2103.03098)
- **[GEN]** Nadeau & Bengio 2003: corrected resampled t-test — variance term multiplied by (1/J + n_test/n_train) to account for overlapping training sets across resamples. (classic; not re-fetched this session) — [Machine Learning 52:239–281](https://link.springer.com/article/10.1023/A:1024068626366)
- **[GEN]** Dietterich 1998: standard paired t-test on resampled/CV splits has inflated Type I error; recommends 5x2cv or McNemar. (classic; not re-fetched this session) — [Neural Computation 10(7)](https://doi.org/10.1162/089976698300017197)
- **[GEN]** DeLong et al. 1988: nonparametric test for comparing correlated AUCs on the same cases. (classic; not re-fetched this session) — [Biometrics 44(3):837–845](https://doi.org/10.2307/2531595)
- **[GEN]** scikit-learn provides `permutation_test_score` and `StratifiedGroupKFold`; repeated CV statistics example implements the corrected t-test. (classic docs; not re-fetched) — [sklearn: statistical comparison of models](https://scikit-learn.org/stable/auto_examples/model_selection/plot_grid_search_stats.html)

### Inferences (calculations and protocol)
- **Binomial CI arithmetic** (my calculation): n=36 patients, accuracy 0.70 → SE = √(0.7·0.3/36) ≈ 0.076 → 95% CI ≈ ±15 pp. With n=72 kidneys (not independent—two per patient), effective n is between 36 and 72; CI ≈ ±11–15 pp. Hence the test set can confirm "no catastrophic drop vs CV", not small improvements.
- **Minimum detectable difference (paired)**: for McNemar on 36 paired cases, detecting a difference requires the discordant pairs to be very lopsided (e.g., ≥ ~9 vs 2 discordant). Rule of thumb: on this test set only differences of ≳10–15 pp accuracy are detectable; use CV (all 144 dev patients × repeats) as the primary comparison venue.
- **Protocol**:
  1. Primary comparison: **repeated StratifiedGroupKFold** (e.g., 10 × 5-fold, groups=patient, stratified by max grade) on dev set; same splits for all models (paired). Metrics per fold: QWK (ordinal), macro-F1, MAE in grades, AUC for clinically relevant thresholds (≥ grade 2). Test difference with **Nadeau–Bengio corrected t-test**, report mean difference + corrected 95% CI.
  2. Seeds: ≥3–5 seeds per configuration nested within repeats; report seed SD; treat differences < seed SD as noise.
  3. Test set (once): **paired patient-level bootstrap** (resample patients, carrying both kidneys and all images) for metric differences, 2,000+ resamples, percentile or BCa CI. DeLong for binary-threshold AUCs; McNemar / permutation test (swap model labels within patient) for accuracy/QWK.
  4. Multiple comparisons: pre-specify the primary comparison; Holm-correct secondary ones.
  5. Pre-register (in a lab log) all choices before touching test.

### Gaps
- No primary source retrieved with explicit power/MDD tables for QWK with n≈36; numbers above are my binomial approximations.

---

## Q7. Designing ablation studies to prove segmentation features add accuracy

### Takeaway
Use a nested, paired ablation on identical grouped splits with OOF-predicted-mask features, comparing image-only vs image + segmentation features (and features-only), and judge by the corrected CV CI and paired test bootstrap — not by a single test number.

### Cited Findings
- **[GEN]** Feature selection performed outside the training fold is one of the two most inflating leakages, worse in small samples — so any feature-group selection must be inside CV. — [Rosenblatt et al. 2024](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10901797/)
- **[GEN]** Data-sampling variance dominates; comparisons need repeated splits. — [Bouthillier et al. 2021](https://arxiv.org/abs/2103.03098)
- **[US, kidney]** Multi-view/multimodal fusion gains reported in kidney US are often within fold SD (0.954 → 0.961), illustrating why paired, repeated evaluation is required to claim added value. — [Yin et al. 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7387180)

### Inferences (ablation design)
- **Arms** (all with identical repeated grouped splits, same aggregation, same seeds):
  - A0: clinical/demographic baseline only (if available).
  - A1: image-only model (CNN on images, patient/kidney aggregation).
  - A2: segmentation features only (from OOF predicted masks).
  - A3: A1 + A2 (late fusion or stacked on OOF predictions).
  - A4: A3 with GT-mask features (upper bound / leakage illustration — not deployable).
  - A5: A3 with noise/permuted segmentation features (negative control: shuffle feature values across patients within training fold) — gain should vanish.
  - Aggregation sub-ablation: mean vs max vs best-long-axis vs attention for the winning arm.
- **Claim criterion**: A3 − A1 > 0 with corrected-t 95% CI excluding 0 on repeated CV, and same direction on test (paired bootstrap CI reported, may include 0 given n=36).
- **Feature-group importance**: grouped permutation importance computed on OOF predictions (permute the whole segmentation-feature group), and drop-group refits.
- **Robustness**: dose-response with mask quality — degrade masks (erode/dilate, or use segmenter checkpoints at different Dice) and show grade accuracy tracks mask quality; strengthens the causal story that segmentation adds information.
- Report Dice of OOF masks alongside, so readers can relate feature value to segmentation quality.

### Gaps
- No published kidney-US ablation of segmentation-derived features vs image-only grading was found in this session.
