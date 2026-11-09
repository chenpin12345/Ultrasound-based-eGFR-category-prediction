# Data & Annotation Strategies for Small-Dataset Medical Imaging (priority: ultrasound / kidney)

Evidence tags used throughout:
- **[US-kidney]** kidney ultrasound evidence
- **[US]** ultrasound evidence from another organ
- **[Other]** inferred from another modality or domain (CT, MRI, fundus, histopathology, natural images)
- **[Unverified]** comes from a search snippet or a secondary summary that was not checked against the primary full text

Research limits: about 15 tool calls in total. Several primary pages (PubMed, ScienceDirect) blocked the fetch, so some numbers rest on search-engine summaries and are marked [Unverified].

---

## Q1. Label quality vs label quantity in small medical datasets (label noise, learning curves, how many ultrasound images)

### Takeaway
No controlled learning curve (Dice vs number of labelled images) was found for kidney ultrasound. Published 2D kidney ultrasound segmentation models reach about 0.91–0.94 Dice with training sets of about 100 to 1,700 images, so this project's 975 images (about 180 patients) sit inside that range. On noise, *systematic (biased)* annotator error hurts segmentation much more than *random* boundary noise, and more data partly offsets random noise. For this project, mask **consistency** (one protocol, one annotator style) matters more than marginal extra volume.

### Cited Findings
- [US-kidney] Pediatric hydronephrosis study: coronal renal ultrasound from 195 patients. A 10-model ensemble reached a mean Dice of about 0.911 against manual tracing of kidney/hydronephrosis areas. The patient count is very close to this project's ~180. — [ResearchGate: Deep-learning segmentation of US for hydronephrosis area to renal parenchyma ratio](https://www.researchgate.net/publication/361056238_Deep-learning_segmentation_of_ultrasound_images_for_automated_calculation_of_the_hydronephrosis_area_to_renal_parenchyma_ratio) [Unverified: search snippet]
- [US-kidney] CKD kidney ultrasound study: 258 kidneys (124 normal, 134 CKD). It used kidney and renal-sinus contours to derive parenchymal thickness and parenchyma-to-sinus ratios for classification. No separate sinus Dice is reported. — [PMC12457927](https://pmc.ncbi.nlm.nih.gov/articles/PMC12457927/) / [PubMed 40755093](https://pubmed.ncbi.nlm.nih.gov/40755093/) [Unverified: snippet]
- [US-kidney] A hydronephrosis framework trained on 1,731 renal ultrasound images annotated by four urologists reported Dice 0.92 (kidney) and 0.89 (fluid). — [Urology 2025, PubMed 40783131](https://pubmed.ncbi.nlm.nih.gov/40783131/) [Unverified: snippet]
- [US-kidney] A systematic review table lists an older pediatric kidney segmentation model (Yin et al. 2019, boundary-distance regression) trained on about 100 2D images with Dice of about 94%. — [Liang et al., QIMS systematic review: AI-aided ultrasound in renal diseases](https://qims.amegroups.org/article/view/112984/html) [Unverified: snippet]
- [US] Intravascular ultrasound with noisy labels: training sets were progressively reduced, and larger training sets mitigated the harm from noisy labels. — [Ultrasound Med Biol 2026, "Beyond Human Variability"](https://www.sciencedirect.com/science/article/pii/S0301562926000293) [Unverified: snippet]
- [US] Semi/self-supervised muscle ultrasound segmentation reportedly reached 92.71% Dice with a single labelled image. Unlabelled images can substitute for many labels in simple-anatomy ultrasound tasks. — [IEEE OJEMB 2025](https://doi.org/10.1109/OJEMB.2025.3537560) [Unverified: snippet]
- [Other: MRI brain tumour] Vorontsov & Kadoury. Supervised and semi-supervised segmentation networks are "robust or fairly robust to unbiased errors but sensitive to biased errors", so mitigation must target bias (for example, one annotator who systematically draws masks too tight or too loose). — [arXiv 2107.02189](https://arxiv.org/abs/2107.02189)
- [Other: MRI brain tumour] With real (not simulated) label noise, performance degraded about 8% less than simulations predicted. The network *learned the annotators' simulated biases*, and an inversely biased Dice loss partly corrected this. — [arXiv 1909.08959](https://arxiv.org/abs/1909.08959) [Unverified: snippet]
- [Other: CT organs-at-risk] Dice fell monotonically as the number of noisy training cases rose. Clean-label models did best. — [arXiv 2003.06240](https://arxiv.org/pdf/2003.06240) [Unverified: snippet]
- [Other] Segmentation under label noise depends on both quantity and quality. One cited study found many coarse annotations more valuable than a tightly controlled smaller set. Small, thin structures suffered most from noise (clavicles on JSRT chest X-ray). — [Vadineanu et al., PMLR 172, 2022](https://proceedings.mlr.press/v172/vadineanu22a/vadineanu22a.pdf) [Unverified: snippet]

### Inferences
- For organ-level masks (liver, spleen, whole parenchyma), 975 images are probably enough to reach the ~0.9 Dice range reported in kidney ultrasound. The **renal sinus** and thin cortex boundaries are the "small/thin structure" case, which is most sensitive to noise and annotator bias.
- Because one researcher draws all masks, *random* noise is limited, but *systematic* bias (for example, the sinus/parenchyma boundary placed consistently inward) is the main risk, and the model will learn it. Mitigation: a written boundary protocol with example images, physician spot checks targeted at the sinus/cortex boundary, and an intra-rater re-annotation of about 20–30 images to measure self-consistency (Dice).
- A practical learning-curve experiment the team can run cheaply: train on 25/50/75/100% of patients (patient-level splits) and plot validation Dice. If the curve is flat between 75% and 100%, extra masks add little and effort should go to quality or the grading labels.

### Gaps
- No published learning curve (Dice vs N) was found for 2D kidney ultrasound, and no renal-sinus-specific Dice.
- No quantitative study was found on label-noise effects for **ordinal echogenicity** classification in ultrasound.

---

## Q2. Handling inter-rater disagreement for ordinal grades (consensus vs averaging vs soft labels / LDL / label smoothing)

### Takeaway
The strongest evidence (diabetic retinopathy) shows that a **small adjudicated consensus set** gives much more benefit than majority votes, especially as the tuning/validation reference standard. For *training*, soft labels built from rater agreement or ordinal soft labels (SORD) mainly improve **calibration** (up to about 70% lower ECE in histopathology) while keeping or slightly improving accuracy. No ultrasound echogenicity study comparing these strategies was found.

### Cited Findings
- [Other: fundus DR] Krause et al. (Google, *Ophthalmology* 2018). Adjudicated consensus of retinal specialists was used as the reference standard. "A small set of adjudicated DR grades allows substantial improvements in algorithm performance." — [arXiv 1710.01711](https://arxiv.org/abs/1710.01711); [Google Research](https://research.google/pubs/pub46802/)
  - Using adjudicated grades as a tuning set (reported as about 0.22% of images), together with higher-resolution input, raised the AUC for moderate-or-worse DR from 0.934 to 0.986. — [Google Research blog](https://research.google/blog/improving-the-effectiveness-of-diabetic-retinopathy-models/); [Healio](https://www.healio.com/news/ophthalmology/20180314/human-adjudication-of-dr-grading-enhances-machine-learning-algorithm) [Unverified: secondary summaries; the gain combines adjudication and resolution]
  - Of 193 discrepancies between adjudication and the ophthalmologists' majority vote, the most common were missed microaneurysms (36%), artifacts (20%), and misclassified haemorrhages (16%). Majority vote systematically misses *subtle* findings. — same sources [Unverified]
- [Other: histopathology] Wei et al. 2022. Label smoothing scaled by per-image annotator agreement reduced calibration error by "almost 70%" for colorectal polyp classification and maintained or improved accuracy. A variant that uses model confidence as a proxy works when multiple raters are unavailable. — [arXiv 2201.11866](https://arxiv.org/abs/2201.11866)
- [Other: segmentation] Averaging several physicians' masks into probabilistic (soft) masks produced well-calibrated predictions (QUBIQ, MICCAI 2021). — [arXiv 2109.12622](https://arxiv.org/pdf/2109.12622) [Unverified: snippet]
- [Other: natural images] On CIFAR-10H, soft labels elicited from a few annotators matched the accuracy, robustness, and calibration of crowd-distribution labels with about 8.5x fewer annotators. Soft labels from very few raters can still help. — [Eliciting and Learning with Soft Labels from Every Annotator](https://www.researchgate.net/publication/364461513_Eliciting_and_Learning_with_Soft_Labels_from_Every_Annotator) [Unverified: snippet]
- [Other: general ordinal] SORD (Díaz & Marathe, CVPR 2019) converts an ordinal label into a soft distribution, a softmax of the negative distance to the true grade. It is used with ordinary cross-entropy and needs no architecture change. — [CVF open access](https://openaccess.thecvf.com/content_CVPR_2019/html/Diaz_Soft_Labels_for_Ordinal_Regression_CVPR_2019_paper.html); implementation: [dlordinal SORDLoss](https://dlordinal.readthedocs.io/en/latest/_modules/dlordinal/losses/sord.html)
- [Other: ordinal calibration] Kim et al. 2024 combine soft ordinal encoding with label-smoothing regularisation to enforce both calibration and unimodality of the predicted grade distribution, and name medical diagnosis as a target use. They note that calibration in ordinal regression is under-explored. — [arXiv 2410.15658](https://arxiv.org/abs/2410.15658)
- [Other] A 2026 preprint notes that soft-label studies rarely include a plain label-smoothing sweep as a zero-cost control, so the soft-label vs simple-smoothing comparison remains under-tested. — [arXiv 2605.29797](https://arxiv.org/pdf/2605.29797) [Unverified: snippet]
- [US-kidney, related] A cortical-echogenicity grading study (two blinded radiologists, 4-level scale) found that grade tracked serum creatinine (P = 0.004). Disagreements were resolved by consensus. No kappa was found in the snippet. — [Radiol Bras / SciELO](https://www.scielo.br/j/rb/a/VLcHYqjHh8Pv9PWbbrJYXDH/?lang=en) [Unverified: snippet]
- [US-kidney, related] Interobserver agreement for renal ultrasound *measurements* in 54 CRF patients was 0.754 (cortical thickness), 0.833 (bipolar length), and 0.523 (parenchymal thickness). These are measurements, not echogenicity grades. — [same SciELO article / rb.org.br](https://rb.org.br/details/2596/en-US) [Unverified: snippet; statistic type not confirmed]

### Inferences
- Recommended label scheme for Grade 0–3 (inferred, not directly tested in ultrasound):
  1. Collect both physicians' grades independently and keep both. Report quadratic-weighted kappa per kidney.
  2. **Train** with soft targets: the per-kidney empirical distribution of the two grades (for example, 2 and 3 gives 0.5/0.5), optionally convolved with a SORD kernel so adjacent grades get mass. When raters agree, use SORD or label smoothing alone.
  3. **Validate/test** against an **adjudicated consensus** (both physicians resolve disagreements together), at least for the held-out test set. DR evidence shows that a small adjudicated reference set matters most.
  4. Report calibration (ECE, and Brier score per grade) alongside QWK/MAE. Calibration is where soft labels show their clearest benefit.
- With only 2 raters, the soft distribution is coarse (agree, or a 50/50 split), but CIFAR-10H-style evidence suggests that few raters still help. Disagreements by more than one grade should always be adjudicated, since they likely reflect image quality or rater error rather than genuine ambiguity.
- Echogenicity is a *relative* judgment (cortex vs liver/spleen). A cheap way to improve consistency is to ask raters to record which reference organ they used and an image-quality flag. Both can serve as auxiliary metadata.

### Gaps
- No head-to-head study (consensus vs averaging vs soft labels) was found for **ultrasound** ordinal grading (fatty liver, renal echogenicity, or hydronephrosis/SFU grading).
- No published kappa was found for renal cortical echogenicity grading. This project's own two-rater kappa would be novel data.

---

## Q3. Active learning in ultrasound segmentation/classification: reported annotation savings

### Takeaway
Ultrasound-specific active-learning evidence is thin. One ultrasound cost-framework study found only about 2% gain at a 10% annotation budget, with diminishing returns. Larger savings (about 67–87% fewer labels) come from X-ray and MRI segmentation. At this project's scale (975 images, one annotator), active learning is unlikely to pay off much over simple, diversity-aware selection.

### Cited Findings
- [US] A cost-focused ultrasound framework (Biomed Signal Process Control 2024) tested uncertainty-sampled active learning. It reported about 2.22% improvement when active learning chose 10% of the dataset, with diminishing returns at larger fractions. The metric appears to be classification accuracy. — [ScienceDirect S174680942400106X](https://www.sciencedirect.com/science/article/pii/S174680942400106X) [Unverified: snippet; full text blocked (403)]
- [Other: chest X-ray] Active-learning lung segmentation matched full supervision with about 30–35% of the data, estimating about 67% savings in expert effort. — [arXiv 1806.05473](https://arxiv.org/pdf/1806.05473) [Unverified: snippet]
- [Other: MRI BraTS] Active learning with 13% of BraTS 2018 outperformed training on the full dataset. — [NSF PAR 10119080](https://par.nsf.gov/servlets/purl/10119080) [Unverified: snippet]
- [Other: histology] "Suggestive Annotation" (Yang et al., MICCAI 2017), the classic uncertainty and representativeness active learning for biomedical segmentation. — [arXiv 1706.04737 mirror](https://axi.lims.ac.uk/paper/1706.04737)
- [Other] Stochastic-batch active learning for medical segmentation found that randomised batch selection is a strong, cheap baseline against uncertainty methods. — [arXiv 2301.07670](https://arxiv.org/pdf/2301.07670) [Unverified: snippet]

### Inferences
- With about 180 patients, the full dataset will likely be annotated anyway. Active learning is therefore better used for **ordering** the work (which images to mask first) and for **targeting physician spot checks**, sending images with the highest model uncertainty or largest disagreement between ensemble members to physician review.
- Diversity-based selection (stratified by machine × eGFR group × provisional grade) is the low-risk first batch.

### Gaps
- No study was found reporting active-learning label savings specifically for **ultrasound segmentation** with Dice.

---

## Q4. Foundation-model-assisted annotation (MedSAM, SAMUS, SAM2, MedSAM2): measured time savings and accuracy

### Takeaway
Measured savings are large (about 82–92% less time) in MedSAM/MedSAM2 human-in-the-loop studies. The only ultrasound measurement is echocardiography *video*, and there is none for 2D B-mode kidney. Accuracy after correction equals expert-revised quality by design, since humans edit until satisfied. SAMUS is an ultrasound-specific SAM adaptation with public code and modest compute needs.

### Cited Findings
- [Other: CT] MedSAM (Nature Communications 2024). In a human study on 3D adrenal tumour annotation (sparse linear markers, then MedSAM, then expert revision until satisfied), annotation time fell by 82.37% and 82.95% for the two experts. — [Ma et al., Nat Commun 2024](https://www.nature.com/articles/s41467-024-44824-z) [Numbers from search summary of the paper]
- [US-echo + CT + MRI] MedSAM2 (2025). Its abstract states it "can reduce manual costs by more than 85%". The user study covered 5,000 CT lesions, 3,984 liver MRI lesions, and 251,550 echocardiogram video frames. It was fine-tuned on more than 455k 3D image-mask pairs and 76k frames. — [arXiv 2504.03600](https://arxiv.org/abs/2504.03600)
  - Per-modality figures from secondary summaries: echocardiography went from about 97 s/frame to 8 s/frame (91.8% reduction). CT lesions went from 513 s to 74.3 s and MRI from 517 s to 65.2 s. The first CT round alone cut time by about 45% (289.2 s/lesion), and iterative fine-tuning on newly annotated data cut it further. — [Emergent Mind summary](https://www.emergentmind.com/topics/medsam2); [LearnOpenCV](https://learnopencv.com/medsam2-explained/) [Unverified: secondary sources]
- [US] SAMUS (2023). Adapts SAM for ultrasound and is trained on US-30K (about 30k images, 69k masks, 6 object categories). Code: https://github.com/xianlin7/SAMUS — [arXiv 2309.06824](https://arxiv.org/abs/2309.06824)
  - Reported Dice gains over the best competing methods: TN3K +1.97, BUSI +3.55, CAMUS-MYO +0.15, DDTI +7.06, UDIAT +12.22, and HMC-QU +7.42 points. — [ar5iv HTML of 2309.06824](https://ar5iv.labs.arxiv.org/html/2309.06824) [Unverified: snippet]
- [US] CC-SAM (2024, built on SAMUS) raised Dice from about 84.45 to 87.11 (TN3K) and from 85.77 to 89.51 (BUSI) over the SAMUS baseline. These are breast and thyroid lesions, not organs. — [arXiv 2408.00181](https://arxiv.org/pdf/2408.00181) [Unverified: snippet]
- [Other] SAM driven by Grounding DINO text prompts for automated annotation was evaluated empirically, a fully automatic alternative to box or point prompting. — [arXiv 2406.19057](https://arxiv.org/pdf/2406.19057)

### Inferences
- A practical workflow for this project (Windows, one consumer GPU or CPU):
  1. Hand-draw about 50–80 images carefully (stratified by machine and kidney side), with physician review.
  2. Use MedSAM/SAMUS or SAM2 with box prompts to pre-label the rest. Alternatively, as soon as a nnU-Net/U-Net trained on the first batch beats the foundation model on validation, use that model as the pre-labeler. Task-specific models trained on even ~50 in-domain images often beat zero-shot SAM on low-contrast ultrasound boundaries (inferred, not measured here).
  3. Correct the pre-labels by hand. Log time per image so the project has its own savings number.
- Risk: correcting a pre-label anchors the annotator to the model's boundary, a form of *biased* noise (see Q1). Mitigation: keep a small subset (about 20 images) annotated from scratch, and compare Dice between from-scratch and corrected masks to quantify the anchoring bias.
- The renal sinus and parenchyma are not standard SAM "objects" (the sinus is hyperechoic inside the kidney), so a box prompt on the whole kidney plus a point on the sinus will likely be needed. Expect more correction effort there.

### Gaps
- No published time-savings measurement was found for SAM-family pre-labelling on **2D B-mode abdominal/kidney ultrasound**.
- No primary-text verification of the MedSAM2 per-modality seconds (abstract gives only ">85%").

---

## Q5. Practical recommendations for this project (how many to annotate first, double-annotation fraction)

### Takeaway
All recommendations below are **inferences** synthesised from Q1–Q4. No ultrasound study directly prescribes a first-batch size or double-annotation fraction. The evidence supports three principles: (1) a small, high-quality adjudicated reference set has outsized value (DR); (2) systematic annotator bias is the main threat (segmentation noise studies); (3) soft or ordinal labels from both raters improve calibration (histopathology, SORD).

### Cited Findings
- Small adjudicated subsets give large gains when used for tuning and evaluation (DR: AUC 0.934 to 0.986 with adjudicated tuning plus resolution change). — [Google Research blog](https://research.google/blog/improving-the-effectiveness-of-diabetic-retinopathy-models/)
- Kidney ultrasound segmentation reached about 0.91 Dice with about 195 patients' images. — [ResearchGate hydronephrosis study](https://www.researchgate.net/publication/361056238_Deep-learning_segmentation_of_ultrasound_images_for_automated_calculation_of_the_hydronephrosis_area_to_renal_parenchyma_ratio) [Unverified]
- Biased errors are more harmful than unbiased ones. — [arXiv 2107.02189](https://arxiv.org/abs/2107.02189)
- Agreement-aware label smoothing cuts ECE by about 70%. — [arXiv 2201.11866](https://arxiv.org/abs/2201.11866)
- Foundation-model pre-labelling with human correction saves more than 80% of time in CT/MRI/echo. — [MedSAM](https://www.nature.com/articles/s41467-024-44824-z); [MedSAM2](https://arxiv.org/abs/2504.03600)

### Inferences (proposed protocol, 推論建議)
- **Grading (Grade 0–3):**
  - Both physicians grade **100% of kidneys independently** (about 360 kidneys). This is already planned, and with only 2 raters full double reading is cheap relative to its value for soft labels and kappa reporting.
  - **Adjudicate** every kidney where the raters differ by 2 or more grades, plus all disagreements in the held-out **test set** (about 20% of patients). Optionally adjudicate all disagreements if time allows.
  - Run a calibration session before grading: about 15–20 kidneys graded together with written criteria (cortex vs liver for the right kidney, cortex vs spleen for the left) and reference images per grade. Then compute kappa on the first 30 independent cases and re-calibrate if quadratic-weighted kappa is below about 0.6 (the "moderate" threshold).
  - Train with soft labels (two-rater distribution plus SORD smoothing). Evaluate with QWK, MAE, and ECE against the adjudicated test labels.
- **Segmentation masks:**
  - First batch: about **60–100 images (about 10–15 patients per machine, both kidneys, liver and spleen views)**, hand-drawn under a written protocol, with **100% physician review** of this batch. This becomes the "gold" seed set and the source of protocol examples.
  - Then pre-label with the seed-trained model or MedSAM/SAMUS, and correct.
  - Physician spot checks: about **10–20% of the remaining masks**, prioritised by model uncertainty or ensemble disagreement (active-learning-style targeting) rather than at random, with every renal-sinus mask on images flagged as difficult.
  - Intra-rater check: the researcher re-draws about 20–30 images blind after 2 or more weeks to report intra-rater Dice. An optional second annotator on the same 20–30 images gives inter-rater Dice, an upper bound for achievable model Dice.
  - Run a learning-curve ablation (25/50/75/100% of patients) to show whether more masks still help.
- **Splits:** split at patient level, stratified by machine and eGFR<60. The test set gets adjudicated grades and physician-verified masks.

### Gaps
- No direct empirical evidence on optimal double-annotation fraction for ultrasound. The numbers above (20%, 10–20%, 60–100) are expert-judgment heuristics, not measured optima.
- No study was found on the specific auxiliary eGFR<60 task's interaction with annotation strategy.
