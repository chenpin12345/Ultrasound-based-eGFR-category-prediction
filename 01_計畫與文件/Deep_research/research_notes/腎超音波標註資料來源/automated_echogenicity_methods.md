# Automated / Semi-automated Quantification of Renal Cortical Echogenicity from B-mode Ultrasound

Context: project plans R = median grey(cortex) / median grey(liver or spleen) and P = (cortex − liver)/(sinus − liver), mapped to Grade 0–3, validated against eGFR and a small physician-reviewed subset (~975 images, ~195 patients, Toshiba/Canon Aplio 300).

## 1. Published quantitative indices, ROI rules, and acquisition effects (gain/TGC/depth/machine)

### Takeaway
The quantitative index used in the literature is a ratio of mean pixel grey levels in ROIs on the renal cortex and the adjacent liver, measured at the same depth. In nephrology it is reported as kidney/liver; in hepatology (the hepatorenal index, HRI) it is reported as liver/kidney. Every published ROI rule uses the mean, not the median. No published study validates a "sinus-normalised" index like P, and no study validates cross-vendor comparability of display grey levels.

### Cited Findings
- **Libório et al. 2017, Kidney Blood Press Res 42(4):708–716 (prospective, n=197, glomerulopathy patients undergoing biopsy, no liver disease).**
  - Echogenicity was quantified from the mean pixel densities of the renal cortex and the adjacent liver using ScionImage.
  - The methods describe echogenicity as "the inverse of the ratio" of cortex to liver mean pixel densities. So the direction of the ratio must be checked before comparing studies.
  - The mean kidney/liver ratio was 1.06 ± 0.19. — [DOAJ record](https://doaj.org/article/da03193e070c494689d7fbbb8ed876df); [search summary/abstract mirror](https://oalib-perpustakaan.upi.edu/Record/doaj_da03193e070c494689d7fbbb8ed876df/Description)
- **Moghazi et al. 2005, Kidney Int (retrospective, n=207 biopsy patients).**
  - Compared length, quantitative echogenicity, cortical thickness and parenchymal thickness against histology.
  - Cortex > liver was coded as ratio > 1.0.
  - Moghazi's reported renal/liver echogenicity ratio range in parenchymal disease was 0.71–1.89, as cited by Araújo 2020.
  - — [Kidney Int DOI record](https://read.qxmd.com/doi/10.1111/j.1523-1755.2005.00230.x); [Stony Brook record](https://researchconnect.stonybrook.edu/en/publications/correlation-of-renal-histopathology-with-sonographic-findings/); [Araújo 2020 citing it](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- **Normal reference values cited in Araújo 2020.**
  - Manley & O'Neill (normal kidneys): the mean pixel density ratio (renal/liver) was 0.812–0.987, and water loading raised echogenicity by about 6.4%.
  - Emamian et al.: about 33% of normal right kidneys were isoechoic to the liver.
  - — [Araújo et al. 2020 BMC Nephrol](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/) (secondary citation; I could not retrieve the Manley primary paper)
- **HRI ROI protocol (Webb-style computerized HRI), detailed in a 2021 biopsy-referenced study.**
  - Design: retrospective, n=267, Philips HDI5000/iU22, 5 MHz curved probe.
  - Liver ROI: at least 400 pixels, avoiding vessels, ducts, masses and cysts.
  - Kidney ROI: renal cortex only, at the same depth as the liver ROI, excluding the collecting system (sinus), cysts and extrarenal fat.
  - Both ROIs sit at or above the focal zone.
  - Three liver/kidney pairs were averaged, using mean grey on a 0–255 PACS scale.
  - Gain was "optimized" by the operator, and TGC handling was not described.
  - The authors warn that cut-points may differ on other vendors' systems.
  - — [PMC8391375](https://pmc.ncbi.nlm.nih.gov/articles/PMC8391375/)
- **HRI definition and the same-depth rule.** Same-depth placement is justified as controlling for depth-dependent attenuation and beam distortion. One protocol places the liver–kidney interface at the image centre so both ROIs fall at the same depth. HRI accuracy was similar across methods of ROI placement, except random placement, with good interobserver agreement. — [PMC7705486](https://pmc.ncbi.nlm.nih.gov/articles/PMC7705486); [Diagnostic accuracy of HRI, U Minnesota record](https://experts.umn.edu/en/publications/diagnostic-accuracy-of-hepatorenal-index-in-the-detection-and-gra/)
- **Original computerized HRI.** Webb M, Yeshua H, Zelber-Sagi S, et al. AJR 2009;192(4):909–914. Later HRI steatosis cut-offs:
  - ≥1.28: 100% sensitivity, 54% specificity for >5% fat (Marshall 2012).
  - ≥1.34: 92% sensitivity, 85% specificity (Shiralkar 2015).
  - ≤1.17: >95% PPV for ≤5% fat; ≥1.4: >95% PPV for ≥10% fat (2021).
  - — [PMC8391375](https://pmc.ncbi.nlm.nih.gov/articles/PMC8391375/); [Shiralkar 2015, PubMed 26014325](https://pubmed.ncbi.nlm.nih.gov/26014325/)
- **Gain/TGC/dynamic range and log compression.**
  - A patent disclosure (not peer-reviewed) says HRI must be measured with well-defined gain, TGC and dynamic range settings.
  - It says displayed grey level has a "severely nonlinear relationship" to true echo intensity because of log compression and post-processing.
  - It says grey level depends on imaging mode (harmonic vs fundamental), and proposes RF-based HRI to reduce sensitivity to settings.
  - — [US patent 12508000, "Systems and methods for finding hepato-renal indices"](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12508000)
- **Inter-operator and inter-machine variability.**
  - Two trained operators scanning on the same day differed in HRI by a mean of −0.1 ± 0.4 (119 scans, 60 participants; registry pilot, not a peer-reviewed paper). — [ClinicalTrials.gov NCT04657523](https://clinicaltrials.gov/study/NCT04657523)
  - A phantom-calibrated attenuation/backscatter method using RF data was reproducible across transducers. This is the "attenuation/backscatter" family, which needs raw RF data. — [search result summary; univr.it PDF](https://iris.univr.it/retrieve/e14ff6e5-2cdb-0209-e053-6605fe0ad24c/sacjhepatol1997.pdf)
- **Kidney-to-spleen ratio.** A diabetic nephropathy study measured hepatic/renal and splenic/renal echo-intensity ratios. Both ratios were lower in nephropathy (that is, kidney brighter), and the spleen/kidney ratio was inversely correlated with urinary albumin. — [Abant Izzet Baysal Univ. repository](https://acikerisim.ibu.edu.tr/items/73edb536-90b4-48aa-9f9b-d0c5ddad888b/full)
- **Texture and histogram features.**
  - Chen CJ, Pai TW et al. 2020 (Taiwan: Chang Gung / NTOU), Enterprise Information Systems 14(2):178–195: used "area-proportional and textural" features with an SVM to classify CKD stages by eGFR. The abstract does not mention echogenicity ratios. — [CGU Pure](https://pure.lib.cgu.edu.tw/en/publications/prediction-of-chronic-kidney-disease-stages-by-renal-ultrasound-i-3/)
  - Tian 2024: ResNet34 + GLCM/HOG texture, n=1,049, AUC 0.781–0.931 for CKD. — [Review PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)

### Inferences
- The project's use of the **median** departs from every published protocol, which all use the mean. The median is defensible because it is robust to vessels and specular reflectors. Report both the mean and the median so results can be compared with the literature.
- The literature direction convention is **kidney/liver**, with values of about 0.8–1.0 in normals and >1.0 meaning the cortex is brighter than the liver. The project's R uses the same convention. An HRI is the reciprocal (liver/kidney).
- Same-depth matching matters more than ROI size. The project has depth-ruler pixel spacing, so it can enforce |depth_cortex − depth_liver| below a tolerance (for example 1 cm), and should log and exclude images where this fails.
- Because grey levels are log-compressed and post-processed, ratios of display grey levels are not linear in backscatter. The ratio is internally referenced, so gain largely cancels when both ROIs share the same depth and TGC band. The project's OCR-read gain can be checked as a covariate: R should be roughly independent of gain if matching is good.
- The P index, which normalises by the sinus as a "maximally bright" internal anchor, has no published validation I could find. It should be framed as exploratory. Sinus brightness itself varies with sinus fat, which depends on age and obesity.

### Gaps
- I could not retrieve primary full texts for Manley & O'Neill, Platt/Emamian normal-value papers, or Webb 2009, so the exact ROI sizes and normal ranges are secondary citations.
- I found no peer-reviewed study quantifying the cross-vendor reproducibility (for example Toshiba vs Canon vs GE) of the kidney/liver grey-level ratio.
- I found no published validation of median-based or sinus-normalised (P-type) renal indices.

## 2. Correlations with eGFR, CKD stage and biopsy; cut-offs and reference ranges; agreement with visual grading

### Takeaway
The quantitative cortex/liver ratio correlates moderately with eGFR (r ≈ −0.46 to −0.68) and weakly-to-moderately with chronic histology (r ≈ 0.26–0.35). The only adult cut-off with published performance is a kidney/liver ratio > 1.15 for advanced CKD in glomerulopathy patients without liver disease. Cut-offs come from single centres and single machines.

### Cited Findings
- **Libório 2017 (n=197, glomerulopathy).**
  - The ratio correlated inversely with eGFR at follow-up (r = −0.684, p<0.001).
  - A ratio > 1.15 had the best discrimination.
  - That cut-off had a 92% positive predictive value for eGFR < 30 mL/min/1.73 m².
  - — [DOAJ](https://doaj.org/article/da03193e070c494689d7fbbb8ed876df); [abstract mirror](https://oalib-perpustakaan.upi.edu/Record/doaj_da03193e070c494689d7fbbb8ed876df/Description)
- **Moghazi 2005 (n=207 biopsies).**
  - Echogenicity was the sonographic parameter that correlated best with all four histologic scores: glomerulosclerosis, tubular atrophy, interstitial fibrosis and inflammation (r = 0.28–0.35).
  - On multivariate analysis, tubular atrophy and interstitial inflammation were significant determinants of cortical echogenicity, but interstitial fibrosis was not.
  - Severe disease occurred in 66% of patients with ratio > 1.0 versus 30% with ratio ≤ 1.0.
  - — [Kidney Int record](https://read.qxmd.com/doi/10.1111/j.1523-1755.2005.00230.x); [Stony Brook](https://researchconnect.stonybrook.edu/en/publications/correlation-of-renal-histopathology-with-sonographic-findings/)
- **Paediatric AKI/CKD (2024).**
  - An echogenicity index (right kidney/liver mean pixel density) correlated with eGFR at r = −0.46.
  - EI 1.0–1.1 predicted eGFR < 90 with AUC 0.71–0.78.
  - EI 1.1–1.2 predicted eGFR < 60 with AUC 0.75–0.80.
  - The correlations were not maintained within aetiology subgroups.
  - — [BVS record mdl-38219260](https://busqueda.bvsalud.org/portal/resource/es/mdl-38219260); [Physician's Weekly summary](https://www.physiciansweekly.com/?p=501874)
- **Paediatric biopsy study (Childhood Kidney Diseases 2017).** Echogenicity correlated with interstitial infiltration or fibrosis (r = 0.259, p = 0.025) and with tubular atrophy (r = 0.268). — [DOAJ](https://doaj.org/article/5d94df36d23945a39e4b51f042c2928b)
- **Thai computer-based analysis (n=37 chronic glomerulopathy, 3-month follow-up).**
  - Higher cortical echogenicity was associated with progression (HR 1.13, 95% CI 1.01–1.25). Long-axis echogenicity gave AUC 0.71 for progression.
  - The renal/liver ratio correlated with IFTA. It gave AUC 0.83 for IFTA > 50%, rising to 0.95 when combined with other findings.
  - — [GMSMJ](https://he02.tci-thaijo.org/index.php/gmsmj/article/view/262871)
- **Araújo et al. 2020, BMC Nephrol (n=112 biopsied, single operator, Siemens 3.5 MHz; visual 3-level grading cortex <, =, > liver).**
  - Weighting kidney length/height by echogenicity (weights 1.17, 1.00, 0.69) raised AUROC for creatinine > 1.5 from 0.62 to 0.84.
  - It raised AUROC for eGFR < 45 to 0.81 and for severe chronic histology index to 0.85, versus about 0.60 for unweighted measures.
  - Interobserver agreement was not reported.
  - — [PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- **Normal values.** The normal renal/liver ratio was 0.812–0.987 (Manley & O'Neill, cited). About 33% of normal adult right kidneys are isoechoic to the liver (Emamian, cited). — [PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- **Transient increases in children.** Cortex ≥ liver was seen in 18% of 189 acutely ill children and normalised within 2 or more weeks, so increased echogenicity can be transient. — [search result, AJR mirror](https://shibboleth.idm.home.nyu.edu/echogenicity-of-the-liver/increased-echogenicity-of-renal-cortex-a-transient-feature-in-acutely-ill-children-ajr)
- **Age.** In neonates the cortex equals or exceeds the liver in echogenicity, so adult norms do not apply to infants. — [Radiology 1983](https://pubs.rsna.org/doi/10.1148/radiology.147.3.6844606)

### Inferences
- A literature-anchored adult grade mapping that could substitute for physician grading:
  - Grade 0: R < ~1.0 (normal range about 0.81–0.99).
  - Grade 1: R ≈ 1.0–1.15 (isoechoic to slightly hyperechoic).
  - Grade 2 or higher: R > 1.15 (Libório's cut-off for advanced CKD).
  - These are approximate anchors from different machines (ScionImage on unknown hardware) and should be recalibrated on the project's own data. A grade 3 threshold (cortex ≈ sinus) has no published quantitative cut-off; P ≈ 1 is a natural operational definition.
- Expected effect sizes for the project's eGFR validation: |r| about 0.4–0.7. A substantially weaker correlation would suggest ROI or depth issues.

### Gaps
- No published reference ranges by CKD stage (G1–G5) for the quantitative ratio, and no published grade 0–3 quantitative cut-offs.
- No primary data on cut-offs from Toshiba/Canon systems.

## 3. Confounders: fatty liver, splenic reference, age, body habitus

### Takeaway
Fatty liver raises liver brightness and therefore lowers the kidney/liver ratio, masking hyperechoic kidneys. Validation studies handle this by excluding liver disease or by switching to the spleen and left kidney. Kidney disease conversely contaminates the HRI, so the two literatures exclude each other's disease.

### Cited Findings
- Libório 2017 explicitly restricted the cohort to patients with "no liver disease". — [DOAJ](https://doaj.org/article/da03193e070c494689d7fbbb8ed876df)
- Araújo 2020 graded six patients with fatty liver against the spleen, using the left kidney. — [PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- **Magnitude of the fatty-liver effect.** HRI (liver/kidney) averaged 1.09 ± 0.25 in ≤5% steatosis and 1.76 ± 0.56 in ≥10% steatosis. Liver steatosis can therefore shift the ratio by more than 50%, far larger than the CKD effect (about 1.0 → 1.15). The same study states HRI is unreliable in chronic renal disease, and it excluded cortical thinning or loss of corticomedullary differentiation. — [PMC8391375](https://pmc.ncbi.nlm.nih.gov/articles/PMC8391375/)
- An MRI-PDFF study of the hepatorenal ratio (n=179) excluded right-kidney atrophy, cysts, scarring and hydronephrosis. — [J Ultrason 2020](https://jultrason.pl/index.php/issues/volume-20-no-82/comparison-of-sonographic-hepatorenal-ratio-and-the-degree-of-hepatic-steatosis-in-magnetic-resonance-imaging-proton-density-fat-fraction)
- In diabetic nephropathy, both right and left renal echo-intensity rose, and both the liver/kidney and spleen/kidney ratios fell. This supports using the spleen as the left-side reference. — [IBU repository](https://acikerisim.ibu.edu.tr/items/73edb536-90b4-48aa-9f9b-d0c5ddad888b/full)
- Hydration matters: water loading raised renal echogenicity by about 6.4% (Manley & O'Neill, cited). — [PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)

### Inferences
- Because fatty liver is highly prevalent in Taiwanese adults and in CKD/diabetic populations, a right-kidney R that is not adjusted for fatty liver will be biased toward "normal".
- Mitigations:
  - (a) Compute both the right-side (liver) and left-side (spleen) ratios per patient and flag disagreement.
  - (b) Flag likely steatosis using liver texture or the liver/spleen ratio. A liver much brighter than the spleen at matched depth suggests steatosis.
  - (c) Run a sensitivity analysis that excludes flagged livers.
- The spleen is less affected by fat, but in long-axis left-kidney views it is often small or at a different depth from the cortex, so many images will fail depth matching.
- Body habitus (deeper organs, more attenuation) mainly hurts the same-depth assumption. Include depth and BMI (if available) as covariates.

### Gaps
- No published quantitative correction factor for steatosis in the renal ratio.
- No published normative data on age-specific adult kidney/liver or kidney/spleen ratios.
- No published comparison of how the left-kidney/spleen and right-kidney/liver ratios agree in the same patients.

## 4. Automated pipelines (segmentation of cortex/sinus, automatic echogenicity)

### Takeaway
Fully automated pipelines either predict eGFR end-to-end with CNNs (Kuo 2019, Taiwan) or segment the kidney and liver and then extract the kidney/liver echogenicity ratio as a handcrafted feature (Korean J Digit Imaging study). Public data with cortex/medulla/central-echo-complex (sinus) labels exists (Open Kidney, UBC). I found no published pipeline that automatically separates cortex from sinus and then validates a cortex/liver grade against physicians.

### Cited Findings
- **Kuo CC et al. 2019, npj Digit Med (China Medical University Hospital, Taichung).**
  - Data: 1,299 patients, 4,505 images, GE LOGIQ E9/P3.
  - Labels: MDRD eGFR within 4 weeks of the scan.
  - Preprocessing: images cropped using the kidney-length calipers.
  - Model: ResNet-101 (ImageNet transfer) with 10-model bagging, plus XGBoost for CKD classification.
  - Continuous eGFR: r = 0.741, MAE 17.6.
  - CKD (eGFR < 60): accuracy 85.6%, AUC 0.904, specificity 92.1%, sensitivity about 60.7%.
  - Comparison: 4 nephrologists scored 60.3–80.1% accuracy.
  - Limitations: no explicit echogenicity features, no external validation, single centre, about 15% of studies with eGFR > 60.
  - — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Severance Hospitals, Yonsei, J Digit Imaging (n=909, 2011–2018).**
  - Mask R-CNN segmented the organs, and kidney length and kidney-to-liver echogenicity ratio were extracted automatically.
  - A ResNet18 image-only model gave AUROC about 0.81. Adding the extracted features raised it to 0.88, and adding diabetes raised it to 0.91.
  - This is the closest published analogue to the project's R.
  - — [Yonsei repository](https://ir.ymlib.yonsei.ac.kr/handle/22282913/193103)
- **Open Kidney Ultrasound Data Set (Singla, Rohling et al., UBC; arXiv 2206.06657).**
  - The first public kidney B-mode set with multi-class segmentation, more than 500 patients, native and transplant kidneys, annotated by two expert sonographers.
  - It describes semantic segmentation of cortex and medulla.
  - Capsule Dice was 0.85 in v2 (0.74 in v1).
  - A companion paper segmented cortex, medulla and central echogenic complex with nnU-Net on 514 images labelled by two sonographers with more than 20 years of experience.
  - — [arXiv 2206.06657](https://arxiv.org/abs/2206.06657v2); [arXiv 2206.06654](https://arxiv.org/pdf/2206.06654)
- **Review of DL in renal ultrasound (PMC12832298).**
  - Whole-kidney segmentation Dice is about 0.77–0.97 (U-Net variants, CycleGAN, YSegNet).
  - CKD/fibrosis prediction AUC is about 0.69–0.94. One AUC of 1.0 was flagged as likely overfitting.
  - Most segmentation work is whole-kidney rather than cortex/sinus.
  - — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- Other classical or ML pipelines:
  - Chen/Pai 2020 Taiwan: area-proportional and texture features with SVM. — [CGU](https://pure.lib.cgu.edu.tw/en/publications/prediction-of-chronic-kidney-disease-stages-by-renal-ultrasound-i-3/)
  - MobileNetV2 + GAN augmentation: 81.9% accuracy for 4-stage CKD classification. — [Appl Sci 12:352](https://mdpi-res.com/d_attachment/applsci/applsci-12-00352/article_deploy/applsci-12-00352.pdf)
  - Two-stage U-Net plus dual-input classifier: 82.9% accuracy. — [ETASR](https://etasr.com/index.php/ETASR/article/download/16275/6301/81473)
  - DeepLabV3+ for multicentre DKD radiomics. — [Front Oncol 2022](https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2022.876967/full)

### Inferences
- A practical pipeline for the project:
  1. Use the existing whole-kidney masks (or a U-Net fine-tuned from them) as the outer boundary.
  2. Separate the sinus inside the mask using intensity clustering (for example k-means or Otsu, k=2–3) plus morphology. The sinus is the large bright central connected component.
  3. Define the cortex as a peripheral band (for example 3–10 mm inward from the capsule, using pixel spacing), excluding the sinus and the dark medullary pyramids. One option is a lower-percentile exclusion or a third cluster.
  4. Optionally fine-tune nnU-Net on Open Kidney cortex, medulla and central echogenic complex labels, though domain shift from UBC/Canadian machines to Aplio 300 is expected.
- In-mask clustering will misclassify in advanced CKD, where corticomedullary and cortex-sinus differentiation is lost. That is the very grade 3 case, so cluster failure (low contrast between sinus and cortex) could itself be used as a grade 3 signal. It should then be confirmed by physician review.

### Gaps
- No published method or code was found that automatically segments renal cortex vs sinus and computes cortex/liver ratios validated against physician grading.
- The Open Kidney label taxonomy (cortex/medulla/CEC) is not confirmed for the public release; the dataset paper should be checked.
- The full text of the Korean J Digit Imaging paper (liver ROI method, year, authors) was not retrieved.
- I found no 2023–2025 Taiwanese follow-up with external validation.

## 5. Validation strategies when physicians are scarce

### Takeaway
Published studies validate quantitative echogenicity against eGFR or creatinine and against biopsy, not against consensus physician grades. Inter-observer kappa for visual cortical echogenicity grading appears essentially unreported, so a small physician-reviewed subset combined with eGFR-based external validation is consistent with field practice.

### Cited Findings
- Libório 2017 and the paediatric 2024 study validated the ratio against eGFR (r, AUC, PPV), not against reader grades. — [DOAJ](https://doaj.org/article/da03193e070c494689d7fbbb8ed876df); [BVS](https://busqueda.bvsalud.org/portal/resource/es/mdl-38219260)
- Araújo 2020 used a single operator and a single pathologist and reported no interobserver data. The authors acknowledged visual grading as a limitation. — [PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- Kuo 2019 benchmarked against 4 nephrologists on a small test set. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- **Closest interobserver data.**
  - In 54 CKD patients scanned by 2 blinded radiologists, agreement was 0.754 for cortical thickness, 0.833 for length and 0.523 for parenchymal thickness. Echogenicity agreement was not reported. — [SciELO Radiol Bras](https://www.scielo.br/j/rb/a/VLcHYqjHh8Pv9PWbbrJYXDH/?lang=en)
  - HRI ROI placement shows good interobserver agreement. — [UMN record](https://experts.umn.edu/en/publications/diagnostic-accuracy-of-hepatorenal-index-in-the-detection-and-gra/)
  - The Open Kidney dataset used two sonographers' annotations, which allows inter-annotator Dice to serve as a segmentation ceiling. — [arXiv 2206.06657](https://arxiv.org/abs/2206.06657v2)

### Inferences
Suggested validation design for the project:
- (a) **Primary external validation against eGFR.** Report the Spearman correlation of R with eGFR (literature expects |r| about 0.45–0.7), and AUC for eGFR < 60 and < 30 (literature: Kuo AUC 0.90 for an end-to-end CNN; Libório PPV 92% for > 1.15 at eGFR < 30). Use patient-level aggregation across the ~5 images per patient.
- (b) **Physician subset.** About 50–100 images, stratified by predicted grade. Report weighted kappa between the algorithm and the physician, and if possible between two physicians, using Landis–Koch benchmarks (0.41–0.60 moderate, 0.61–0.80 substantial).
- (c) **Segmentation QC.** A physician accepts or rejects the cortex and sinus overlays rather than drawing them, which is much cheaper.
- (d) **Robustness checks.** Correlation of R with gain, depth and machine (Toshiba vs Canon), left vs right consistency, and a sensitivity analysis excluding suspected fatty liver.

### Gaps
- No peer-reviewed kappa benchmark for visual renal cortical echogenicity grading (Grade 0–3) was found. The well-known Hricak/Platt-era visual grading papers could not be retrieved in this session.
- No published guidance on minimum physician-subset sizes for this specific task.
