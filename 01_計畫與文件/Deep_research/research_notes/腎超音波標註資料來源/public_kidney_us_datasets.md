# Public Annotated Kidney (and Liver/Spleen) Ultrasound Datasets for Segmentation / Echogenicity Pretraining

Research date: 2026-10-23. About 20 tool calls were made. Several primary pages (Nature/Scientific Data, figshare, MDPI, Roboflow) returned HTTP 403/redirects to the fetch tool, and PDF text extraction was not possible (no Python/poppler), so several details are marked **UNVERIFIED (from memory)** and must be checked by hand.

## Q1. Open Kidney Ultrasound Data Set (Singla et al., UBC): exact contents, classes, license, access

### Takeaway
This is the only verified public 2D B-mode kidney ultrasound dataset with multi-class (fine-grained) masks. It has about 514 images from about 500 or more patients, native and transplant kidneys, two sonographer annotation sets, and PNG plus VIA CSV polygon files. It is licensed **CC BY-NC-SA 4.0** and access is by **Qualtrics registration with manual approval**. Non-commercial academic use in Taiwan is allowed under the licence. It has **no liver or spleen masks and no eGFR labels**.

### Cited Findings
- Paper: Singla R., Ringstrom C., Hu G., Lessoway V., Reid J., Nguan C., Rohling R. "The Open Kidney Ultrasound Data Set." ASMUS workshop (MICCAI 2023 satellite), LNCS pp. 155–164, Springer, 2023. arXiv 2206.06657 — [GitHub rsingla92/kidneyUS](https://github.com/rsingla92/kidneyUS); [arXiv](https://arxiv.org/abs/2206.06657v2)
- "Over 500" 2D B-mode abdominal US images, one image per patient. Native and transplanted kidneys. Data collected retrospectively over a 5-year period. Mean age 53.2 ± 14.7 y, BMI 27.0 ± 5.4. Most common primary diseases are diabetes, IgA nephropathy and hypertension — [arXiv abstract](https://arxiv.org/abs/2206.06657v2); [GitHub](https://github.com/rsingla92/kidneyUS)
- A dataset atlas counts 534 files / 514 unique patients and images, and lists access as "Application" — [open-medical-ultrasound-datasets atlas](https://github.com/eliasstenhede/open-medical-ultrasound-datasets)
- Annotations: two independent sets of polygon annotations, each by an "expert sonographer", exported from the VGG Image Annotator (VIA) as CSV. Four segmentation classes. Each image also has a view label and a kidney-type label (native/transplant) — [GitHub](https://github.com/rsingla92/kidneyUS)
- The 4 classes are kidney capsule, cortex, medulla and central echogenic complex (sinus). A secondary paper describes the dataset this way — [SBBD paper (SBC)](https://sol.sbc.org.br/index.php/sbbd/article/download/44038/43801/). The same group's transplant speckle paper uses cortex/medulla/central echogenic complex region masks with nnU-Net — [arXiv 2206.06654](https://arxiv.org/pdf/2206.06654)
- Machines: Philips, GE, Acuson, Siemens, Toshiba and SonoSite. A transducer-info spreadsheet is included where available. Images are PNG and the original DICOMs are not shared — [GitHub](https://github.com/rsingla92/kidneyUS)
- License: CC BY-NC-SA 4.0 (non-commercial, share-alike) — [arXiv](https://arxiv.org/abs/2206.06657v2); [GitHub](https://github.com/rsingla92/kidneyUS)
- Access: fill in a Qualtrics registration form, and the maintainer reviews each request by hand (hours to days). Evaluation scripts are in `/src/` — [GitHub](https://github.com/rsingla92/kidneyUS)
- Benchmark: the arXiv v1 reported capsule Dice 0.74, and v2 / the published version reports capsule Dice **0.85** with a "state-of-the-art algorithm" — [arXiv v2](https://arxiv.org/abs/2206.06657v2); [SOTAVerified](https://sotaverified.org/papers/the-open-kidney-ultrasound-data-set)
- Other benchmark: a 2025 study (MAT-UNet, MDPI Diagnostics 15(15):1978) reports DSC of 84.34% for the central echo complex, 66.34% for the medulla and 58.93% for the cortex. The search snippet does not confirm which dataset was used (the page returned 403) — [MDPI Diagnostics 2025](https://www.mdpi.com/2075-4418/15/15/1978/htm)
- A 2025 comparative study benchmarks semantic segmentation models on this dataset — [ResearchGate: Comparative study using Open Kidney US Dataset](https://www.researchgate.net/publication/394332845_A_Comparative_Study_of_Deep_Learning_Semantic_Segmentation_Models_for_Kidney_Segmentation_in_Ultrasound_Images_Using_the_Open_Kidney_Ultrasound_Dataset)
- The same UBC group used capsule segmentation to measure kidney length and width automatically, and notes intra- and inter-rater variability in manual measurement — [J. Med. Imaging 10(3):034003](https://biomedicaloptics.spiedigitallibrary.org/journals/journal-of-medical-imaging/volume-10/issue-03/034003/Automatic-measurement-of-kidney-dimensions-in-two-dimensional-ultrasonography-is/10.1117/1.JMI.10.3.034003.full)

### Inferences
- Its class set (capsule / cortex / medulla / central echo complex) maps almost exactly to the student's targets: whole kidney, parenchyma (cortex + medulla merged), and sinus. It is the best candidate for pretraining or fine-tuning a kidney sub-region segmenter.
- Its machines include Toshiba but not specifically the Canon Aplio 300, so expect a domain shift. Fine-tuning on a small set of locally labelled images (for example 30–50 with corrected pseudo-labels) is advisable.
- The masks are polygons, so cortex/medulla boundaries are approximate. Medulla and cortex Dice scores are known to be much lower than capsule/sinus scores (consistent with the 58–66% figures above), which suggests label noise and ambiguity at the corticomedullary boundary. Merging cortex and medulla into "parenchyma" is likely more reliable for a grey-level ratio.
- The images are not cropped to the kidney, and liver or spleen often appears in them, but it is **not labelled**. The student would need to annotate a liver/spleen ROI themselves (a simple rectangle or polygon ROI at the same depth is the usual practice for a cortex-to-liver echogenicity ratio).
- Because of ShareAlike, any derived dataset (for example masks redistributed with added labels) must use the same licence. Model weights are a grey zone, so cite and keep the work non-commercial.
- Steps for Taiwan: (1) fill in the Qualtrics form with an institutional email and a statement of the research purpose; (2) wait for manual approval; (3) cite the ASMUS 2023 paper; (4) do not redistribute the data; (5) check with the local IRB whether external public data needs mention in the protocol.

### Gaps
- The exact image count (514 vs 534 files), the view categories (long axis vs transverse vs other), the resolution, the per-class nnU-Net Dice scores for cortex/medulla/CEC, and the inter-sonographer Dice could not be extracted from the PDF (binary-only fetch). **UNVERIFIED (from memory):** the paper reports nnU-Net-style baselines and inter-rater agreement per class, and most views are longitudinal. Verify against Table/Fig. in arXiv 2206.06657v2.
- The download size is not stated.

## Q2. Other kidney ultrasound datasets (stones, hydronephrosis, CKD/eGFR, transplant, CT-derived/synthetic, multi-organ)

### Takeaway
Besides Open Kidney, the verified public kidney US resources are: TRUSTED (3D US+CT, kidney masks, 48 patients); a large Mendeley stone/normal classification set (CC BY 4.0, no masks); CT2US (CT-derived kidney masks for synthetic-US transfer); a Roboflow kidney/liver/spleen instance-segmentation set (1,080 images, provenance unclear); and USenhance 2023 (kidney among organs, enhancement only). **No public dataset pairing kidney US with eGFR/CKD labels or echogenicity grades was found, and no public pediatric hydronephrosis image dataset was found.**

### Cited Findings
**TRUSTED (Scientific Data, 2025)**
- Paired 3D transabdominal US and CT from 48 patients (96 kidneys), with kidney segmentations and anatomical landmarks by two experienced radiographers. Benchmarks four DNN segmentation methods, and US performance was more variable than CT. Only 59 US images were successfully segmented and included. Hosted on figshare (~14.89 GB) — [Scientific Data article](https://www.nature.com/articles/s41597-025-04467-1); [figshare](https://springernature.figshare.com/articles/dataset/TRUSTED_The_Paired_3D_Ultrasound_and_CT_Human_Data_for_Kidney_Segmentation_and_Registration_Research/27981050); [HAL record](https://hal-sfo.ccsd.cnrs.fr/ISIR_MLIA/hal-05475413v1)
- Described as free to use for developing and validating segmentation/registration methods. The research group appears French-linked — [HAL](https://hal-sfo.ccsd.cnrs.fr/ISIR_MLIA/hal-05475413v1)

**Kidney Ultrasound Images "Stone" and "No Stone" (Mendeley Data, 2024)**
- Gurjeet Kaur, Sukhwinder Singh (Punjabi University, India). 9,416 images: Normal 4,414 and Stone 5,002. Machines: Samsung RS85, HS60, RS80A, HS70A and others. **CC BY 4.0**. Published 27 Aug 2024, DOI 10.17632/h6jc4xm4py.1. No segmentation masks mentioned — [Mendeley Data](https://data.mendeley.com/datasets/h6jc4xm4py/1)

**CT2US (Song et al., Ultrasonics 2022)**
- "CT2US: Cross-modal transfer learning for kidney segmentation in ultrasound images with synthesized data". A Hugging Face mirror holds 4,586 (4.59k) paired image/mask samples at 256×256, licence GPL-2.0, from the original Kaggle release — [HF MedOtter/CT2USforKidneySeg](https://huggingface.co/datasets/MedOtter/CT2USforKidneySeg); [search summary](https://huggingface.co/datasets/MedOtter/CT2USforKidneySeg)
- It is a kidney-only dataset. Nothing found ties CT2US to AbdomenAtlas or provides liver/spleen labels.

**Ultrasound Normal Kidney Image (Roboflow Universe)**
- 1,080 images for abdominal organ instance segmentation with kidney, liver and spleen classes. Listed as Open, licence not stated in the atlas, and the page returned 403 — [atlas](https://github.com/eliasstenhede/open-medical-ultrasound-datasets); [Roboflow](https://universe.roboflow.com/jeevaws/ultrasound-normal-kidney-image)

**WD-KUS (Khan et al., Interdisciplinary Sciences: Computational Life Sciences, 2024)**
- Kidney US segmentation dataset reported as 44,880 images. The hosting repository and licence were not confirmed — [Springer article](https://link.springer.com/article/10.1007/s12539-024-00620-3)

**USenhance 2023 (MICCAI challenge)**
- 1,050 training pairs and 364 test inputs, 109 patients. Covers thyroid, carotid, liver, kidney and breast. Low-to-high image enhancement only, no masks. CC BY-SA — [atlas](https://github.com/eliasstenhede/open-medical-ultrasound-datasets); [Grand Challenge](https://ultrasoundenhance2023.grand-challenge.org/datasets/)

**Clinical Ultrasound Image Repository (AWS Open Data)**
- 2,000 studies (abdominal, cardiac, OB/GYN) for representation learning. Unlabelled, so useful only for self-supervised pretraining — [AWS registry](https://registry.opendata.aws/clinical-ultrasound-image-data/)

**Hydronephrosis / CKD (no public data found)**
- Smail et al. 2020 (Frontiers in Pediatrics): 2,420 sagittal images from 673 patients, SFU grade CNN, 94% correct or within one grade. No public release found — [Frontiers](https://www.frontiersin.org/articles/10.3389/fped.2020.00001/text)
- Song et al. 2022 (Investig Clin Urol): segmentation for a hydronephrosis-to-parenchyma ratio, 195 pediatric patients, institutional — [PMC9262488](https://pmc.ncbi.nlm.nih.gov/articles/PMC9262488)
- Alexa et al. 2024 (Eur Urol Open Sci): AI hydronephrosis detection in adult renal colic — [PDF](https://www.opendata.uni-halle.de/bitstream/1981185920/119497/1/1-s2.0-S2666168324002507-main.pdf)

**Liver-only US datasets useful for liver ROI / echogenicity reference**
- B-mode fatty liver dataset (Byra et al., 550 images / 55 patients, steatosis labels): [Zenodo 1009146](https://zenodo.org/records/1009146)
- Annotated Ultrasound Liver images (735 images, liver/mass segmentation): [Zenodo 7272660](https://zenodo.org/records/7272660)
- BEHSOF (1,669 images / 113 individuals, NAFLD grading): [figshare](https://figshare.com/articles/dataset/BEHSOF/26389069)
- liver_ultrasound (400 images, 14-class detection): [Roboflow](https://universe.roboflow.com/joe-klepich/liver_ultrasound)
- Source for all of the above: [open-medical-ultrasound-datasets atlas](https://github.com/eliasstenhede/open-medical-ultrasound-datasets)

**Survey / registries**
- npj Digital Medicine 2025 review on public dissemination of ultrasound datasets/models — [npj Digit Med](https://www.nature.com/articles/s41746-025-02162-4)
- Ultrasound Open Access Datasets registry — [nidusai](https://ultrasound-open-access.nidusai.ca/)
- UltraSam (2024) aggregates open US segmentation datasets ("US-43d") — [arXiv 2411.16222](https://arxiv.org/pdf/2411.16222)

### Inferences
- For the cortex-to-liver ratio, the realistic open route is: Open Kidney (kidney sub-regions) plus a liver/spleen segmenter trained on the Roboflow kidney/liver/spleen set or on synthetic CT-derived data, or simple manual liver ROIs.
- The Mendeley stone set (CC BY 4.0, Samsung machines) is usable as an auxiliary stone classifier or for self-supervised pretraining. It provides no masks.
- None of these datasets has eGFR, so the student's 975-image eGFR cohort itself is unique and is the asset to publish.

### Gaps
- **AbdomenUS / US simulation & segmentation (Vitale et al., IJCARS 2020, Kaggle "ignaciorlando/ussimandsegm")**: **UNVERIFIED (from memory)**. About 926 synthetic US images ray-cast from CT with masks for liver, kidney, spleen, pancreas, vessels, gallbladder and bones, plus about 617 real abdominal US images, with a small annotated subset. It is not checked in this session, so verify the Kaggle page and licence.
- The TRUSTED licence string (likely CC BY 4.0 as a Scientific Data figshare item) could not be verified because the page returned 403.
- The Roboflow kidney/liver/spleen set's licence, provenance (possibly web-scraped) and annotation quality are unknown.
- The WD-KUS access route is unknown.
- No public renal-transplant-only US dataset was found besides the transplant subset of Open Kidney.
- No public dataset has echogenicity grades.

## Q3. Asian / Taiwanese datasets

### Takeaway
No kidney ultrasound segmentation dataset from Taiwan, China, Korea or Japan was found. The only Asian kidney-US public set found is the Indian Mendeley stone dataset (classification only).

### Cited Findings
- A targeted search returned no Asian-origin kidney US segmentation dataset, only Open Kidney (Canada) and TRUSTED (France) — [arXiv Open Kidney](https://arxiv.org/abs/2206.06657v2); [HAL TRUSTED](https://hal-sfo.ccsd.cnrs.fr/ISIR_MLIA/hal-05475413v1)
- Indian kidney stone set: [Mendeley](https://data.mendeley.com/datasets/h6jc4xm4py/1)
- Chinese multi-organ US image-text archive (breast, thyroid, liver; not kidney): [GitHub LijunRio/Ultrasound-Report-Generation](https://github.com/LijunRio/Ultrasound-Report-Generation)

### Inferences
- Taiwanese CKD-ultrasound deep-learning work (for example the NTUH/CGMH-type studies) appears to rely on institutional data. The student's dataset would likely be among the first Taiwan kidney-US cohorts with eGFR labels.

### Gaps
- Searches were not performed in Chinese, Korean or Japanese, or on Taiwan-specific repositories (for example the Taiwan Biobank or NHRI). A follow-up search is recommended.

## Q4. Quality caveats and realistic usability for a non-commercial academic project in Taiwan

### Takeaway
Open Kidney is usable (CC BY-NC-SA, registration). The Mendeley stone set (CC BY 4.0), CT2US (GPL-2.0 on HF) and TRUSTED (figshare, open) are usable with attribution. The Roboflow sets are usable for experiments but have unverified provenance. All of them carry domain shift relative to Canon Aplio 300/Toshiba images, and their annotation protocols differ.

### Cited Findings
- Open Kidney spans 6 vendors, exports PNG only (no DICOM, so no calibrated pixel spacing or raw grey-level metadata), and uses polygon annotations by 2 sonographers — [GitHub](https://github.com/rsingla92/kidneyUS)
- In Open Kidney, the capsule is the most reliably segmented class (Dice 0.85). Lower reported DSC for the medulla (66%) and cortex (59%) versus the CEC (84%) in a later study suggests that internal boundaries are harder or noisier — [arXiv](https://arxiv.org/abs/2206.06657v2); [MDPI](https://www.mdpi.com/2075-4418/15/15/1978/htm)
- TRUSTED's US segmentation performance was more variable than CT's, and it is 3D rather than 2D B-mode long-axis — [Scientific Data](https://www.nature.com/articles/s41597-025-04467-1)
- CT2US is only 256×256 and derived from CT. It is a synthetic-domain source, not real speckle — [HF](https://huggingface.co/datasets/MedOtter/CT2USforKidneySeg)

### Inferences
- **Grey-level ratio caveat**: PNG exports from different vendors use different gain, TGC, dynamic range and post-processing maps. Absolute grey levels are not comparable across datasets. The cortex-to-liver ratio must be computed only on the student's own images, with liver and kidney at matched depth. Public data should be used only to train the segmenters, not to calibrate echogenicity.
- Recommended pipeline: (1) pretrain or fine-tune nnU-Net or a SAM-family model (for example UltraSam, MedSAM) on Open Kidney with 3 classes (capsule, parenchyma = cortex + medulla, sinus = CEC); (2) pseudo-label the 975 local images; (3) have the student, ideally with a sonographer's brief spot-check, correct about 50–100 images; (4) use a rectangular liver/spleen ROI or a liver segmenter; (5) report Dice on a held-out set of locally corrected images.
- Use the Mendeley stone set only for an optional stone classifier. For cysts or hydronephrosis there is no public mask data, so a rule-based anechoic-region detection inside the sinus or capsule, or local labelling, is needed.
- Licence compliance: keep everything non-commercial, cite each paper, do not redistribute Open Kidney images, and apply ShareAlike to derivatives.

### Gaps
- Pixel spacing and resolution are not stated in any verified source for Open Kidney.
- No quantitative cross-vendor domain-shift study on kidney US segmentation was found in this session.
