# Renal ultrasound: standard protocols, image-quality criteria, and beginner learning resources

Research date: 2026-10-23. Link check: each URL was checked with curl (HTTP 200 unless noted). Radiopaedia returns HTTP 406 to automated requests, so its pages could **not** be machine-verified. 5minsono.com, efsumb.org, wfumb.info, tsum.org.tw and sono.org.tw timed out or refused the connection (status 000) from this environment. They may still work in a normal browser, but they are unverified.

## Q1. Standard examination and reporting protocols (required images, measurements, report items)

### Takeaway
The governing US document is the ACR–AIUM–SPR–SRU Practice Parameter for ultrasound of the abdomen and/or retroperitoneum. The current revision is 2026; the previous one was 2021. For each kidney, the operational requirements are:
- longitudinal images (lateral, mid, medial) or a medial-to-lateral cine sweep
- transverse images (upper pole, mid, lower pole) or a superior-to-inferior cine sweep
- a **renal length** measurement
- comparison of cortical echogenicity with the adjacent liver (right) or spleen (left)
- assessment of hydronephrosis, stones, cysts and masses, plus longitudinal and transverse bladder views

I found no free, verified RSNA RadReport renal-US template. The report items below come from institutional protocols and the practice-parameter image library.

### Cited Findings
- AIUM lists "Abdomen or Retroperitoneum (2026)" (article: https://onlinelibrary.wiley.com/doi/epdf/10.1002/jum.70430) with a free **image library PDF**. It also lists "Native Renal Vessels (2023)" (https://onlinelibrary.wiley.com/doi/10.1002/jum.16353) and "Urology (2012)" with its own image library — [AIUM Practice Parameters](https://www.aium.org/resources/practice-parameters)
- The ACR portal copy is titled "ACR–AIUM–SPR–SRU Practice Parameter for the Performance of an Ultrasound Examination of the Abdomen and/or Retroperitoneum", "Revised 2026 (Resolution 10)". It has sections "H. Kidneys", "VI. Documentation" and "VII. Equipment Specifications". The body text could not be extracted automatically, so the user should open it manually — [ACR PPTS DocId=189](https://gravitas.acr.org/PPTS/GetDocumentView?docId=189). The older 2021 PDF is at https://www.acr.org/-/media/ACR/Files/Practice-Parameters/US-Abd-Retro.pdf; it now redirects and could not be fetched.
- The AIUM abdomen **image library** gives labeled example images: "Comparison View Liver/Right Kidney", "Spleen/Left Kidney", "Long-axis Right Kidney", "Transverse Right Kidney", "Renal Length", "Renal Cortical Thickness", and "Renal Pelvis, Cortex and Sinus". This makes it a good visual reference for the "standard planes" — [AIUM abdomen image resources PDF](https://aium.s3.amazonaws.com/guidelines/abdomen/imageResources.pdf)
- ACR accreditation exam requirements for the **Renal** exam (the same as the Kidneys part of Abdomen Complete):
  - Longitudinal, option A: "at least three gray scale images to include lateral, mid without measurement, medial".
  - Longitudinal, option B: a longitudinal cine clip from medial to lateral through both kidneys, plus at least one static mid-kidney longitudinal image without measurement.
  - Transverse: upper pole, mid without measurement, and lower pole, or a superior-to-inferior cine clip plus one static mid transverse image.
  - **Renal length is required.**
  - "Complete documentation" means "a series of several images throughout the entire organ in two planes". Anatomy should be "intentionally imaged in an organized fashion and correctly labeled".
  - Source: [ACR Accreditation Support – Exam Requirements: General Ultrasound](https://accreditationsupport.acr.org/support/solutions/articles/11000062867-exam-requirements-general-ultrasound)
- University of Wisconsin Radiology renal protocol (dated 5/20/2024; references ACR–AIUM–SPR–SRU 2021):
  - **Equipment and position:** curvilinear or sector transducer, 2–7 MHz; supine, decubitus or prone.
  - **Evaluation:** longitudinal lateral, mid and medial; transverse superior, mid and inferior poles; cortical thickness and echogenicity "compare to adjacent liver or spleen"; renal pelvis; hydronephrosis, stones, masses/cysts, perfusion abnormalities; renal and perirenal abnormalities.
  - **Bladder:** longitudinal and transverse planes, wall thickness, diverticula or masses, distal ureters/UVJ if dilated, volume and post-void residual if indicated.
  - **Full image set per kidney:** long lateral, mid and medial; length measurement; color perfusion; lateral-to-medial cine; transverse superior, mid and inferior; color hilum; superior-to-inferior cine.
  - **Abbreviated protocol:** cine sweeps plus length and color perfusion, used when CT or MR was done within 24 hours.
  - **Tips:** power Doppler for pyelonephritis; "twinkle" artifact for stones; narrow sector and depth plus harmonics for cysts and masses.
  - Source: [UW Radiology Wiki – Final Renal protocol PDF](https://wiki.radiology.wisc.edu/images/8/8a/Final_Renal.pdf)
- A pediatric renal US reporting template was designed because "renal US requests and reports are inadequate" (Pediatr Radiol 2011) — [Springer s00247-011-2259-0](https://link.springer.com/article/10.1007/s00247-011-2259-0)
- In contrast-enhanced ultrasound (CEUS) of cystic renal lesions, structured reports allowed complete information extraction in 100% of cases, compared with 82% for free-text reports — [Diagnostics 2021, 11(2):313](https://www.mdpi.com/2075-4418/11/2/313)
- RadReport (RSNA) is reachable and hosts free peer-reviewed templates. I could not confirm a specific renal-US template ID, because the site renders client-side — [radreport.org](https://radreport.org/)
- POCUS 101's free renal guide covers a step-by-step protocol, hydronephrosis grading (with a free pocket-card PDF), stones compared with CT, cyst and mass evaluation, and renal Doppler — [POCUS 101 – Renal Ultrasound Made Easy](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/)

### Inferences
- **Reading checklist** (synthesized from the ACR, AIUM and UW sources above). For each kidney, in this order:
  1. Side and plane label (RT/LT, LONG/TRANS).
  2. Whole kidney visible.
  3. Length in cm (maximal long-axis).
  4. Contour: smooth or lobulated, any scarring.
  5. Cortical thickness.
  6. Cortical echogenicity compared with liver or spleen.
  7. Corticomedullary differentiation (pyramids distinct from cortex).
  8. Renal sinus and pelvis: hydronephrosis absent, or present with a grade.
  9. Stones (echogenic focus with shadowing or twinkle).
  10. Cysts (anechoic, thin wall, posterior enhancement) compared with solid masses.
  11. Perirenal fluid or collection.
  12. Doppler perfusion, if available.
  13. Bladder: wall, contents, volume or post-void residual.
- **Mapping to AI labels:** the AIUM image-library view names (Long-axis, Transverse, Liver/RK comparison, Spleen/LK comparison, Renal Length) form a natural view taxonomy for a view classifier.

### Gaps
- Verbatim 2026 kidney-section text (frequencies, exact documentation wording) was not extractable. Read it on Wiley (jum.70430) or the ACR portal.
- I could not verify a specific RadReport renal US template (name or ID).
- The commonly quoted adult normal ranges (for example, length about 10–12 cm) were not verified from a primary source in this session.

## Q2. Image-quality criteria and image selection/exclusion in kidney US AI studies

### Takeaway
I found no widely adopted, validated image-quality *score* for kidney US. AI studies use pragmatic rules instead:
- keep images showing the **maximal long-axis length**, often identified by the presence of length **calipers**
- or use 3-level (Good/Bad/Null) or 4-level (unacceptable/poor/fair/good) expert quality labels

Calipers and overlays are both a selection signal and a confound that needs handling.

### Cited Findings
**Kuo et al. 2019, npj Digital Medicine** (Taiwan, China Medical University Hospital):
- The cohort started with 8,281 pre-ESRD patients and 203,353 images. eGFR had to be within ±4 weeks of the ultrasound.
- Only post-2014 GE LOGIQ E9 and P3 images were kept, for image quality (37,696 images).
- Images showing the **maximum kidney length** were chosen. **Template matching found the length-annotation (caliper) markers, and images without them were removed.**
- The final set was 4,505 images from 1,446 studies of 1,299 patients.
- The crop was centered at the caliper midpoint, with side length equal to the caliper distance, resized to 224×224. `findContours` was used to separate the kidney from logos and other content.
- Augmentation: shift ±10%, rotation ±40°, horizontal flip.
- Patient-level 90/10 split. Results: Pearson r 0.741, MAE 17.6; CKD (eGFR<60) accuracy 85.6%, AUC 0.904.
- Sources: [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/); [Nature](https://www.nature.com/articles/s41746-019-0104-2)

**Scientific Reports 2025, automated frame selection in kidney US:**
- Expert labels: **Good** = "clear, well-centered kidneys with complete structures, suitable for diagnostic measurement"; **Bad** = partial kidney visibility, motion blur, or poor contrast; **Null** = kidney not visible or irrelevant content dominates.
- 1,203 frames from 211 patients. A YOLO11x-cls model reached 90% ± 5.9% accuracy in 5-fold CV. All errors were Bad/Null confusions.
- Source: [PMC12647705](https://pmc.ncbi.nlm.nih.gov/articles/PMC12647705/)

**Open Kidney Ultrasound Data Set** (arXiv 2206.06657):
- More than 500 patients over 5 years; native and transplant kidneys.
- Labels include **view** and **quality**, plus multi-class segmentation by two expert sonographers. Capsule Dice was 0.85.
- A search snippet indicated a quality scale of unacceptable/poor/fair/good; the abstract page does not define it.
- Source: [arXiv](https://arxiv.org/abs/2206.06657)

**SickKids "RenalView" poster:**
- An EfficientNetB0 view labeler for pediatric renal US sequences. The authors report that confident predictions help identify high-quality views, and that label uncertainty between views is a challenge.
- Source: [poster PDF](https://stanhua.rbind.io/2024_nature_pch_poster.pdf)

**Zhang et al. 2026 review** (DL in renal US):
- Noise, artifacts and operator variability degrade performance: a 30% SNR drop is reported to cut Dice by 8–12%, and different sonographers cause 5–7% Dice fluctuation.
- Models trained on adults lose about 22% performance on pediatric data.
- Only 32% of hospitals used unified scanning standards.
- It recommends image-quality assessment standards and multicenter external validation.
- Source: [PMC12832298](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832298/)

**Acquisition-related quality cues from protocols:**
- Narrow sector width and depth to raise frame rate; use harmonics; set gain and depth correctly — [UW renal protocol](https://wiki.radiology.wisc.edu/images/8/8a/Final_Renal.pdf)
- In a resident curriculum, "setting gain and depth" and "measuring kidney length with calipers" were explicit checklist skills — [PMC11614398](https://pmc.ncbi.nlm.nih.gov/articles/PMC11614398/)

### Inferences
**Practical usability checklist for a dataset** (synthesized from the sources above; not a validated score). An image is usable when:
1. The entire kidney outline is inside the field: both poles visible, not truncated by the image edge or by rib shadow.
2. The plane is long-axis at maximal length, with the central sinus visible (or transverse at the hilum).
3. Depth puts the kidney in the central part of the image, with focus at kidney level.
4. Gain and TGC are set so the cortex is grey (not saturated or black) and the sinus is bright.
5. No major acoustic shadowing (rib or bowel gas) over the parenchyma, and no motion blur.
6. A side/plane label is present.

Exclude:
- color Doppler, split-screen and CEUS frames (unless intended)
- images with heavy text or measurement overlays crossing the kidney
- non-kidney or "Null" frames

**Caliper handling:** calipers can leak label information (they mark the measured images and also encode length). Options:
- mask or inpaint the caliper and text pixels, or use the paired un-annotated frame
- or explicitly use calipers only for cropping and evaluate on un-annotated images

Report the chosen approach. A model may otherwise learn the caliper position or the vendor overlay. Also restrict to, or stratify by, device or vendor, as Kuo did.

### Gaps
- No published, validated kidney-specific image-quality scoring system was found. The 4-level Open Kidney scale definitions were not verified in full text.
- No study found explicitly reports caliper inpainting for kidney US. This is a recommendation, not a sourced practice.

## Q3. Learning resources, textbooks, curricula and competence numbers (plus a suggested study path)

### Takeaway
The best free, image-rich starting points are:
- POCUS 101 (renal guide)
- ultrasoundcases.info (large free case library with kidney section)
- The POCUS Atlas (renal/GU)
- NephroPOCUS (nephrology-focused)
- Core Ultrasound
- SonoWorld
- 123sonography (partly paid)
- the free AIUM image library
- the free EFSUMB Course Book chapters
- Radiopaedia: an excellent reference, but it could not be machine-verified here

For competence, the published nephrology guidance suggests about **10 directly supervised scans** per application before independent scanning, and **40 adequate scans** for credentialing (aligned with ACEP). A Delphi panel says scan count alone should not define competence.

### Cited Findings
- **POCUS 101 renal guide** (free; step-by-step views, hydronephrosis grading, free pocket card) — [link](https://www.pocus101.com/renal-ultrasound-made-easy-step-by-step-guide/) (HTTP 200)
- **Ultrasound Cases** (free browsable cases, with a kidney section under abdomen/retroperitoneum) — [kidneys section](https://www.ultrasoundcases.info/cases/abdomen-and-retroperitoneum/kidneys/) (HTTP 200)
- **The POCUS Atlas – Renal/GU** (free image and clip atlas) — [link](https://www.thepocusatlas.com/renal) (HTTP 200)
- **NephroPOCUS** (nephrology-oriented POCUS, A. Koratala) — [link](https://www.nephropocus.com/) (HTTP 200)
- **Core Ultrasound** — [link](https://www.coreultrasound.com/) (HTTP 200); **SonoWorld** (IAME medical ultrasound video library) — [link](https://www.sonoworld.com/) (HTTP 200); **123 Sonography** (mostly paid courses) — [link](https://www.123sonography.com/) (HTTP 200)
- **EFSUMB Course Book, 2nd ed.** (ed. C.F. Dietrich): chapters are free to download individually, including "Ultrasound of the kidneys and ureter" and kidney-transplant US. A renal-vessel Doppler chapter is on Issuu. Sources: [EFSUMB](https://efsumb.org/?p=3907) (unverified, timed out); [Issuu ch23](https://issuu.com/efsumb/docs/coursebook-renal_ch23) (HTTP 200). A Student Edition was launched in 2013 — [Ultraschall Med 2013](https://www.thieme-connect.com/products/ejournals/html/10.1055/s-0033-1346840)
- **AIUM image library PDF** (free; labeled standard kidney views) — [link](https://aium.s3.amazonaws.com/guidelines/abdomen/imageResources.pdf)
- **SonoSim renal module** is paid (about US$549 at listing) — [SonoSim](https://store.sonosim.com/renal-core-clinical-module/)
- **Reisinger & Koratala, CJASN 2022:**
  - Training combines psychomotor skill (acquisition) and cognitive skill (normal vs pathologic recognition).
  - About **10 directly supervised scans** per application, judged adequate, before independent scanning.
  - **100% review** of learner studies.
  - **40 adequate scans** per application for credentialing, "aligned with ACEP guidelines".
  - Points to free open-access (FOAMed) resources and the Koratala et al. 2019 AJKD model curriculum.
  - Source: [PMC9528260](https://pmc.ncbi.nlm.nih.gov/articles/PMC9528260/)
- **Ishisaka et al., renal POCUS curriculum** (internal medicine residents, 2-week rotation, Kern 6-step model):
  - Structure: pre-recorded lectures, a hands-on session, and an 18-item checklist (probe orientation, long and short axis of both kidneys, liver/hepatorenal and spleen/splenorenal recesses, bladder, cortex vs pyramids vs calyces, length with calipers, gain and depth, video, normal vs abnormal).
  - The lowest-scoring item was **distinguishing cortex, medullary pyramids and calyces (76.9%)**.
  - The goal of 5 supervised studies was not met (mean 2.25).
  - Errors against radiology included **bowel misidentified as kidney** and a missed right kidney.
  - Source: [PMC11614398](https://pmc.ncbi.nlm.nih.gov/articles/PMC11614398/)
- **Pediatric nephrology Delphi:** experts agreed that a minimum scan count alone is an insufficient measure of competence. Consensus items included kidney size, cortical thickness and hydronephrosis — [Braz J Nephrol / SciELO](https://scielo.br/j/jbn/a/Vc6g9sYLjFWVp8D46WFX84v/?lang=en)
- **Chinese / Taiwanese resources:**
  - The search found no TSUM (中華民國醫用超音波學會) kidney teaching material. Its sites (tsum.org.tw / sono.org.tw) did not respond from this environment.
  - Related finds: a hospital patient-education page on renal US (shows kidney, upper ureter and bladder; checks for stones, obstruction, abscess, cysts, tumors; 10–15 min) — [亞東醫院](https://www.auh.org.tw/NewsInfo/HealthEducationInfo?docid=1382)
  - The Radiological Society of ROC abdominal imaging seminars — [rsroc.org.tw](https://rsroc.org.tw/action/actions_onlinedetail.asp?id=10073)

### Inferences
**Self-testing with answer keys:**
- ultrasoundcases.info and The POCUS Atlas pair each image or clip with a diagnosis, so they work as flashcards (hide the caption).
- Radiopaedia cases have findings and diagnosis, and its site has quiz modes (not verified here).
- The free EFSUMB and AIUM materials are reference material, not quizzes.

**Suggested 6-week path for a CS student** (my synthesis):
- **Week 1:** Anatomy and orientation. Read the POCUS 101 renal guide and the AIUM image-library kidney pages. Learn the views: long, transverse, liver/RK and spleen/LK comparison.
- **Week 2:** Normal appearance. Cortex vs pyramids vs sinus (the hardest item per Ishisaka), echogenicity comparison, length measurement. Read the EFSUMB kidney chapter.
- **Week 3:** Image quality and knobology. Gain, TGC, depth, focus, and rib or bowel shadow artifacts. Sort 50+ images from your own dataset into Good/Bad/Null using the Sci Rep 2025 definitions.
- **Week 4:** Core pathology. Hydronephrosis grades (POCUS 101 card), stones (shadowing, twinkle), simple cysts vs complex cysts or masses.
- **Week 5:** Medical renal disease and CKD signs (increased echogenicity, small kidneys, thin cortex). Read Kuo 2019 and the Zhang 2026 review.
- **Week 6:** Blind self-test on 40+ answer-keyed cases (mirroring the 40-scan credentialing figure) using the reading checklist. Track accuracy per category.

**Textbooks** (from background knowledge; not verified in this session):
- Rumack, *Diagnostic Ultrasound*, kidney chapter: comprehensive pathology reference.
- *Ultrasound: The Requisites*: concise radiology-resident overview.
- Hagen-Ansert, *Textbook of Diagnostic Sonography*: sonographer-oriented, with scanning technique and protocols. Good for "how images are acquired".
- EFSUMB Course Book: free and concise.

### Gaps
- Radiopaedia, 5-Minute Sono, WFUMB and TSUM pages could not be verified (bot block or timeouts). Check them manually.
- I did not identify a specific Coursera/edX renal-US course or a specific YouTube channel with verified links.
- Textbook chapter contents and editions were not verified.
- I found no Traditional-Chinese, image-rich, free renal US teaching site with verification.
