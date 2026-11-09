# Segmentation Model Options for Kidney Ultrasound (plus Liver/Spleen Reference ROIs)

Context: about 975 B-mode images from about 181 patients at a single site in Taiwan. The deployment is local Windows on CPU or one consumer GPU. The existing model is a plain UNet (base_c=32, bilinear upsampling, 512x512, 2 classes) trained for whole-kidney segmentation. The new targets are cortex vs renal sinus, liver and spleen ROIs at matched depth, kidney length, and later cysts, stones and hydronephrosis.
Research date: 2026-10-23. Searches were limited (about 20 tool calls), so some points are flagged UNVERIFIED.

## 1. Published kidney ultrasound segmentation: datasets and results

### Takeaway
Whole-kidney ultrasound segmentation is close to solved: most papers report Dice of roughly 0.90-0.97, usually single-center. Internal structures are much harder. On the Open Kidney Ultrasound Data Set (OKUD), cortex and medulla Dice are only about 0.59-0.66, while the central echo complex (≈ renal sinus) reaches about 0.84. The project's "cortex vs sinus" task therefore has realistic targets of roughly 0.80-0.85 for the sinus and less for cortex/parenchyma. Plan for clearly defined label rules and inter-rater checks.

### Cited Findings
- **OKUD (Singla et al., arXiv 2206.06657):** more than 500 patients collected over 5 years. Images have multi-class semantic segmentation and view labels from two expert sonographers, and both native and transplanted kidneys are included. License is CC BY-NC-SA 4.0 (non-commercial). The baseline "state-of-the-art algorithm" reached Dice 0.85 on the kidney capsule (v2) — [arXiv abs v2](https://arxiv.org/abs/2206.06657v2)
- The OKUD v1 preprint reported capsule Dice 0.74, which changed to 0.85 in v2 — [arXiv v1 PDF](https://arxiv.org/pdf/2206.06657v1), via [search summary / SOTAVerified](https://sotaverified.org/papers/the-open-kidney-ultrasound-data-set). Version discrepancy: cite v2.
- OKUD classes are capsule, cortex, medulla and central echo complex — [search summary of arXiv 2206.06657](https://arxiv.org/pdf/2206.06657.pdf). I could not read the PDF text, so the exact image count (about 500 images) is UNVERIFIED. The UltraSam paper lists the dataset as "KidneyUS" with 487 images and 487 masks — [UltraSam arXiv 2411.16222v2](https://arxiv.org/html/2411.16222v2)
- **MAT-UNet on OKUD (MDPI Diagnostics 2025, 15(15):1978):** capsule Dice 93.83%, central echo complex 84.34%, medulla 66.34%, cortex 58.93% — per search snippet of [MDPI Diagnostics](https://www.mdpi.com/2075-4418/15/15/1978/htm). The full text returned 403, so baselines and setup are UNVERIFIED.
- **Frontiers in Oncology 2026 review (Zhang et al., 15:1730628), Table 2:** whole-kidney US segmentation studies, as listed in the review:
  - YSegNet: 700 images, DSC 97%
  - Multiscale CNN: 7,350 images, DSC 95.86%
  - Fast-UNet++: 3 centers, 744 images, DSC above 95%
  - MLAU-Net: 44,880 images, DSC 90.21%
  - CycleGAN-based methods: DSC 77-85%
  - Kim et al. 2021: U-Net plus active contour in 331 children, volume ICC 0.925 vs CT

  — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- The same review gives no per-structure Dice for cortex, sinus, cyst, hydronephrosis or stone. Most studies use normal kidneys from a single center. Other points from the review:
  - Labeling takes 10-15 min per image for a senior sonographer.
  - Differences between operators shift Dice by 5-7%.
  - Adult-trained models lose about 22% performance on pediatric data.
  - A 30% drop in SNR is linked to an 8-12% drop in Dice.

  — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- **Coarse-to-refined network (Biomolecules 2023;13(10):1548):** Dice 94.6% on 1,380 transabdominal kidney images, whole kidney only — [PMC10604927](https://pmc.ncbi.nlm.nih.gov/articles/PMC10604927)
- **MLAU-Net (Digital Health 2024):** attention plus deep supervision U-Net, Dice 90.2% on a Würzburg dynamic kidney US dataset — [DOAJ](https://doaj.org/article/d1d7c2034a114ad3b3c7b09c06796bfe)
- **Pediatric work (Yin et al., CHOP):** uses boundary distance regression plus pixel classification on top of pretrained ImageNet features, with shape-registration augmentation, trained on "a small number" of labeled pediatric US images (hydronephrosis/CAKUT). The authors report it beats U-Net and DeepLab variants, but the abstract gives no Dice — [arXiv 1811.04815](https://arxiv.org/abs/1811.04815). I could not confirm a co-author named "Kuo" in this line of work.
- **Pediatric hydronephrosis:**
  - Attention U-Net segmenting the kidney and the dilated pelvicalyceal system, proposing a fluid-to-kidney area ratio (Abdominal Radiology 2021) — per [search summary, PMC7387180 / PMC9262488](https://pmc.ncbi.nlm.nih.gov/articles/PMC9262488)
  - HARP ratio (hydronephrosis area to renal parenchyma) in 168 pediatric patients with UPJO (Investigative and Clinical Urology 2022) — [DOAJ](https://doaj.org/article/c9dce30c0180466cb814415804e833b1)
  - Exact Dice values were not retrieved.

### Inferences
- Defining "cortex = kidney minus sinus" matches the OKUD central-echo-complex setup well. Segmenting **sinus/CEC** directly (Dice about 0.84 in published work) and deriving parenchyma by subtraction should be more robust than separating cortex from medulla, which reaches only about 0.6 Dice.
- An internal test with about 181 patients, single site and one vendor will likely give optimistic Dice. Plan a patient-level split and, if possible, a check on OKUD (non-commercial license only).

### Gaps
- Exact OKUD image count, inter-rater Dice and baseline architecture could not be read because PDF text extraction failed.
- I found no ultrasound paper reporting renal-sinus Dice outside OKUD-based work.
- Published Dice for cyst, stone or hydronephrosis segmentation in US was not found in this pass.

## 2. Candidate methods and small-data performance

### Takeaway
For a fully automatic, multi-class 2D model on about 1k images, **nnU-Net (2D) is the strongest default baseline**. "nnU-Net Revisited" shows that many newer architectures, including transformers, fail to beat a well-configured CNN U-Net. SAM-family models (MedSAM, SAMUS, UltraSam) are most useful as **annotation accelerators** (prompted segmentation) rather than as the deployed automatic model. Ultrasound foundation models (USFM, UltraSam) claim label efficiency but have little kidney-specific evidence.

### Cited Findings
- **nnU-Net Revisited (Isensee et al., MICCAI 2024, LNCS 15009 pp. 488-498):**
  - Many recent methods fail to beat the original nnU-Net baseline once validation pitfalls are fixed.
  - The state-of-the-art recipe is CNN U-Nets (including ResNet/ConvNeXt variants) inside the nnU-Net framework, scaled to modern hardware.
  - The paper releases ResEnc presets.

  — [arXiv 2404.09556](https://arxiv.org/pdf/2404.09556); [MICCAI page](https://papers.miccai.org/miccai-2024/562-Paper2847.html). Caveat: the benchmark is 3D CT/MR, not 2D ultrasound.
- nnU-Net supports 2D and 3D and is Apache-2.0 licensed — [GitHub MIC-DKFZ/nnUNet](https://github.com/MIC-DKFZ/nnUNet)
- **SAMUS (arXiv 2309.06824):** SAM ViT-B plus a parallel CNN branch and adapters, input reduced from 1024 to 256. Trained on US30K (about 30k images, 69k masks, 6 categories: thyroid, breast, heart, etc.). The data has **no kidney** (datasets: TN3K, DDTI, TG3K, BUSI, UDIAT, CAMUS, HMC-QU). MIT license; one 24 GB RTX 3090 Ti is "enough" for training — [GitHub xianlin7/SAMUS](https://github.com/xianlin7/SAMUS); [arXiv](https://arxiv.org/abs/2309.06824v2)
- A TU Delft thesis on intra-operative kidney US (robot-assisted partial nephrectomy) used SAMUS. It reports Dice 88.0±2.0% and HD 13.7±3.8 mm, outperforming DeepLabV3+ — [TU Delft repository](https://repository.tudelft.nl/file/File_8f281697-5527-41d1-bb0b-ba9682498625). This is a thesis, not peer-reviewed, and uses intra-operative probe images.
- **UltraSam (arXiv 2411.16222):**
  - SAM ViT-B trained on US-43d: 43 open datasets, about 282k images, 58 structures, including KidneyUS with 487 images.
  - Point and box prompts.
  - Beats SAM variants (for example BUS-BRA point-prompt mAP 67.1 vs Med-SA 64.4 vs SAMUS 51.8).
  - No kidney-specific results.
  - The paper does not state a model license.

  — [arXiv html v2](https://arxiv.org/html/2411.16222v2)
- **USFM (Jiao et al., arXiv 2401.00153):** pretrained on more than 2M US images from 12 organs with spatial-frequency dual masked image modeling. Claims robust performance using only 20% of the annotations — [arXiv](https://arxiv.org/abs/2401.00153v2). Publication venue (Medical Image Analysis) is UNVERIFIED.
- **UltraBench 2 (arXiv 2609.28610, 2026):** abstract says ultrasound-specific pretraining "still leads on classification", while state-of-the-art general-purpose models "have drawn level on segmentation" — [arXiv abs](https://arxiv.org/abs/2609.28610). Whether nnU-Net was compared was not visible in the abstract.
- **MedSAM (bowang-lab):** Apache-2.0. Includes a PyQt5 GUI (`gui.py`) for box-prompted segmentation. LiteMedSAM is claimed to be "10x faster" — [GitHub bowang-lab/MedSAM](https://github.com/bowang-lab/MedSAM). MedficientSAM reports about 0.9-1.1 s per 2D image on an Intel i9-10900K CPU — [GitHub medficientsam](https://github.com/hieplpvip/medficientsam)
- SAM struggles with low-contrast, faint-boundary medical targets — CC-SAM, per [search summary, ECCV 2024](https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/06124.pdf)
- **SAMUSA (MICCAI 2025):** SAM2 adapted for ultrasound annotation. Notes that weak US boundaries degrade point prompts — [MICCAI 2025 paper](https://papers.miccai.org/miccai-2025/paper/3015_paper.pdf)
- In a 286-image abdominal US study, pretraining SAMed on a larger public US dataset made transfer learning reliable for small data — per search snippet, [SHTI250209](https://journals.sagepub.com/doi/reader/10.3233/SHTI250209). UNVERIFIED details.
- **MedicoSAM (arXiv 2501.11734)** compares SAM variants with nnU-Net trained on the same splits, but its US experiments were 3D — [arXiv](https://arxiv.org/pdf/2501.11734)

### Inferences
- **Attention UNet, TransUNet, Swin-UNet:** I found no kidney-US-specific evidence that they consistently beat a tuned CNN U-Net. Given nnU-Net Revisited, architecture changes are unlikely to help as much as better labels, augmentation and nnU-Net-style training (deep supervision, Dice+CE loss, 5-fold CV, ensembling). This is an inference, not a direct kidney-US result.
- The existing UNet (base_c=32) is roughly a small nnU-Net 2D without the training recipe. Its architecture is not the bottleneck; labels and training pipeline are.

### Gaps
- I found no head-to-head of nnU-Net 2D vs MedSAM/SAMUS/UltraSam on a kidney US dataset.
- The UltraSam weights license is unknown.
- USFM code and weights availability and license were not checked.

## 3. Annotation efficiency and how many labels are needed

### Takeaway
Use a SAM-family prompt tool (MedSAM GUI box prompts, or CVAT with SAM) to draft whole-kidney, liver and spleen masks quickly. Sinus and lesion borders still need manual correction. Train iteratively (label → train nnU-Net → pre-label → correct). I found no published "minimum N" for kidney US. Published whole-kidney models range from about 400 images (Kim et al. pediatric; KidneyUS with 487) to thousands, and USFM claims good results with 20% of the labels.

### Cited Findings
- Expert labeling cost is 10-15 min per image — [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)
- The MedSAM GUI supports box-prompted segmentation for drafting masks — [GitHub MedSAM](https://github.com/bowang-lab/MedSAM)
- MONAI Label is free and open source, focused on 3D (3D Slicer, OHIF clients) and CT/MR radiology apps. CVAT integration is documented mainly for endoscopy and pathology through Nuclio-served models — [MONAI Label](https://monai.io/label.html); [NVIDIA docs](https://docs.nvidia.com/launchpad/ai/monai-label/latest/monai-endoscopy-app.html)
- Point prompts degrade on weak US boundaries, so box prompts are preferred — [SAMUSA MICCAI 2025](https://papers.miccai.org/miccai-2025/paper/3015_paper.pdf)
- Dataset sizes in published kidney US work range from 487 images (KidneyUS) to 700 (YSegNet), 744 (Fast-UNet++), 1,380 (Biomolecules 2023) and 7,350+ — [UltraSam](https://arxiv.org/html/2411.16222v2); [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/); [PMC10604927](https://pmc.ncbi.nlm.nih.gov/articles/PMC10604927)

### Inferences
- A practical pilot is about 150-300 annotated images (patient-level split, covering both kidneys, multiple views and abnormal cases) for kidney plus sinus. Add liver and spleen where visible, then grow by active pre-labeling. This range is my estimate, not a published threshold.
- CVAT's built-in SAM interactor and Label Studio's SAM backend exist from my prior knowledge, but I did not verify them in this session (UNVERIFIED). CVAT can export masks directly, and both run on Windows through Docker.

### Gaps
- I found no learning-curve study of Dice vs number of labeled images for kidney US.
- I found no MONAI Label 2D ultrasound app.

## 4. Practicality: speed, licenses, Windows

### Takeaway
nnU-Net (Apache-2.0), MedSAM (Apache-2.0) and SAMUS (MIT) are all permissively licensed, but **OKUD data is CC BY-NC-SA (non-commercial)**. A 512x512 2D U-Net runs comfortably on CPU. SAM ViT-B encoders are heavier, about 1 s per image on CPU (LiteMedSAM/MedficientSAM figures).

### Cited Findings
- **nnU-Net:** Apache-2.0 — [GitHub](https://github.com/MIC-DKFZ/nnUNet)
- **MedSAM:** Apache-2.0 — [GitHub](https://github.com/bowang-lab/MedSAM); MedSAM2 is also reported as Apache-2.0 via a mirror — [gitee mirror](https://gitee.com/Heconnor/MedSAM2) (verify against the official repo)
- **SAMUS:** MIT; trained with SAM ViT-B weights — [GitHub](https://github.com/xianlin7/SAMUS)
- **OKUD:** CC BY-NC-SA 4.0 — [arXiv](https://arxiv.org/abs/2206.06657v2)
- **CPU timing:** MedficientSAM runs 2D inference in about 0.9-1.1 s on an i9-10900K CPU — [GitHub](https://github.com/hieplpvip/medficientsam)
- **Original SAM / SAM2 (Meta):** Apache-2.0 — UNVERIFIED in this session (from prior knowledge; check [facebookresearch/segment-anything](https://github.com/facebookresearch/segment-anything) and [facebookresearch/sam2](https://github.com/facebookresearch/sam2) LICENSE files).

### Inferences
- nnU-Net v2 generally runs on Windows; its docs historically recommend Linux, and Windows may need `nnUNet_n_proc_DA` or worker settings adjusted (UNVERIFIED). For deployment, the trained 2D nnU-Net can be exported, or the inference predictor called directly. A single 512x512 2D forward pass on CPU is typically under 1 s. Disabling nnU-Net's default test-time mirroring and 5-fold ensembling cuts CPU time about 5-10x.
- Inherited licenses on weights matter more than code licenses. Check UltraSam and USFM weights before any commercial or regulatory use.

### Gaps
- nnU-Net's official Windows guidance and CPU benchmarks were not retrieved (the GitHub README fetch did not show them).

## 5. Multi-class vs separate models; final recommendation

### Takeaway
Use **one multi-class 2D nnU-Net for anatomy** (background, kidney parenchyma, renal sinus/CEC, liver, spleen). Treat lesions (cyst, stone, hydronephrosis/dilated collecting system) as a later, separate model or label set. Recommendation: **keep the existing 512 UNet only as an interim whole-kidney model and pre-labeler; replace it for the new tasks with nnU-Net 2D**, using a SAM-family tool (MedSAM/SAMUS box prompts) for annotation, not for deployment.

### Cited Findings
- Precedent for liver and kidney in one pipeline: Fast-Unet segmentation of kidney (Dice 94%) and liver (Dice 97%), with the liver ROI placed at the same depth as the renal ROI to correct depth attenuation for the hepatorenal index — [ESR presentation](https://connect.myesr.org/?p=42230) (conference abstract, less rigorous)
- Cha et al. 2021 (Ultrasonography): a deep CNN segments organs, followed by Gaussian mixture ROI selection for automated HRI. ICC vs radiologists was about 0.92 for the liver and kidney measures and 0.73 for HRI, in 294 living-donor candidates. Performance was best in normal or mild fatty liver — [PMC8446496](https://pmc.ncbi.nlm.nih.gov/articles/PMC8446496); [DOAJ](https://doaj.org/article/de59266c5a5c4b958d1513baaace0d4f)
- Philips patent US 12026886 covers automatic HRI with liver and renal-cortex ROIs in Morison's pouch views — [Google Patents](https://patents.google.com/patent/US12026886). This is a patent with no validation data, and it is an IP awareness point.
- The hydronephrosis literature segments kidney plus dilated collecting system and uses area ratios (HARP, fluid-to-kidney ratio) — [DOAJ ICU 2022](https://doaj.org/article/c9dce30c0180466cb814415804e833b1)

### Inferences
- **Multi-class model:**
  - Kidney, sinus, liver and spleen are mutually exclusive, large regions in the same images, so softmax multi-class training shares features and enforces non-overlap.
  - Use **mutually exclusive labels**: parenchyma and sinus as separate classes, with whole kidney = union. This avoids overlapping-label problems.
  - nnU-Net also supports region-based training for nested labels.
- **Lesions:** cysts and stones are small, rare and sometimes inside the sinus. Stones show acoustic shadowing, so detection or classification may fit better than segmentation. Train them later as additional classes once enough examples are labeled, or as a separate model, to avoid class imbalance hurting anatomy. Hydronephrosis can be derived from an enlarged, anechoic sinus/collecting-system class.
- **Kidney length:** compute from the whole-kidney mask (longest Feret diameter or principal-axis length) using the DICOM pixel spacing. Validate against sonographer calipers (Bland-Altman). Only longitudinal views are valid, so a view classifier or rule is needed.
- **Liver/spleen echogenicity:** do not use the whole organ mask. Place fixed-size ROIs in the parenchyma at the depth of the renal cortex ROI, as the Fast-Unet HRI work does, and avoid vessels, the capsule and shadowing. Same-image comparison is only valid when liver or spleen are in the same frame (right kidney with liver, left kidney with spleen).
- **Keep / fine-tune / replace:**
  - **Keep:** the current 512 UNet as a production whole-kidney fallback and as a pre-labeler for generating draft masks for correction.
  - **Fine-tune:** possible (change the final layer to 5 classes and fine-tune), but its training recipe lacks nnU-Net's augmentation, deep supervision and CV. Effort is similar to switching.
  - **Replace (recommended):** nnU-Net v2 2D (default or ResEnc-M) multi-class, trained with 5-fold CV on patient-level splits. Benchmark it against the existing UNet on the same test set. Optionally compare a SAMUS or UltraSam fine-tune if a GPU is available. Discard the 1024 UNet.
- **Keep largest connected component post-processing:** keep it per class for kidney and liver/spleen. Not for cysts or stones (multiple instances).

### Gaps
- No published multi-class (kidney + sinus + liver + spleen) US model was found for direct benchmarking.
- Spleen ultrasound segmentation evidence was not searched in depth.
- The claim that Attention UNet, TransUNet and Swin-UNet give no consistent gain on kidney US is an inference from general (3D CT/MR) evidence, not a kidney-US head-to-head.
