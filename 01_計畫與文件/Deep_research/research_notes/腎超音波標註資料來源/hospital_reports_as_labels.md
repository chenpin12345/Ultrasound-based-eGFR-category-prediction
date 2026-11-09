# Using existing hospital ultrasound reports as labels (kidney US AI, Taiwan)

Research date: 2026-10-23. Limited budget (~17 searches/fetches); several items rest on search-result snippets rather than full-text reading and are flagged as such.

## Q1. How do kidney ultrasound reports describe echogenicity, CMD, size, cysts, stones, hydronephrosis? Are grades explicit?

### Takeaway
I found no source showing that routine kidney ultrasound reports (in Taiwan or elsewhere) state a numeric Grade 0-3 echogenicity. The research grading systems (cortex vs liver/spleen) are used in **studies**, and even there the reading is visual and qualitative. Report text will most likely give only qualitative phrases ("increased echogenicity", "parenchymal renal disease"), so mapping text to a 4-level grade will be lossy, especially between Grade 0/1 and Grade 2/3.

### Cited Findings
- A Brazilian biopsy study (Araújo et al., BMC Nephrology 2020; n=112) graded cortical echogenicity against the **liver**, using the **spleen** for the left kidney in 6 patients with fatty liver. Grades were 0 (less than reference), 1 (equal) and 2 (higher), so this is a 3-level scheme. The authors say echogenicity was "evaluated visually rather than quantitatively" and that kidneys slightly brighter or darker than the liver may be misclassified as "equal". — [Araújo et al. 2020, PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- The same study weighted kidney length/height by echogenicity grade (factors 1.17 / 1.00 / 0.69). The weighted index gave AUROC 0.812 for eGFR ≤45 and 0.845 for severe chronic histologic change. — [PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- Ultrasound CKD studies commonly record kidney length, cortical/parenchymal thickness and subjective cortical echogenicity relative to the liver, and compare them with serum creatinine. — [Role of Ultrasound in Diagnosis of CKD and Correlation with Serum Creatinine, PMC6516621](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6516621/)
- An older Taiwanese paper (1991, gout nephropathy) listed findings in Chinese: small kidneys (腎臟變小), irregular margins (腎邊緣不規則), thin cortex (腎皮質變薄), increased cortical echo (腎皮質回音強度增加) and cysts (腎水囊). This shows the Chinese descriptive vocabulary but is not current report practice. — [airitilibrary 1991](https://www.airitilibrary.com/Publication/Index/10188940-199106-16-2-183-192-a)
- In the Taiwanese China Medical University study (Kuo et al., npj Digit Med 2019), nephrologists performed and interpreted the kidney ultrasounds, and the images carried on-screen **length calipers**. The authors used those calipers to crop images. They did not use report text. — [Kuo et al. 2019, PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)

### Inferences
- These are inferences, not sourced. Taiwanese reports are usually written in English or mixed English. Typical phrasing likely includes: "Both kidneys: normal size and echogenicity"; "increased renal parenchymal echogenicity" or "increased cortical echogenicity, compatible with parenchymal renal disease (PRD)"; "poor/blurred corticomedullary differentiation"; "renal cyst(s), R't upper pole, 1.2 cm"; "renal stone / echogenic focus with acoustic shadow"; "mild/moderate/severe hydronephrosis". Chinese variants include 腎實質回音增加, 皮髓質分界不清, 腎囊腫, 腎結石, 腎水腫. The student should confirm this by reading a sample of real reports.
- Size (bipolar length in cm, often per side), cysts, stones and hydronephrosis are usually reported explicitly and with laterality. They are therefore better suited to text-derived labels than the echogenicity grade.
- "Equal to renal sinus" (Grade 3) is rarely stated. A report-derived label would probably merge Grades 2 and 3 into "increased echogenicity / PRD".

### Gaps
- I found no published Taiwanese report template and no corpus showing actual Taiwanese renal US report phrasing.
- I did not retrieve an ACR/RSNA RadReport renal ultrasound template in this session.
- I found no study quantifying how often reports state a reference organ (liver or spleen) for echogenicity.

## Q2. Published studies that extracted labels from radiology/ultrasound reports for image-model training

### Takeaway
Rule-based labelers (NegBio, CheXpert) and more recent LLM labelers reach high but category-dependent accuracy. Uncertainty and ambiguous or multi-finding reports are the weak points. LLM extraction has been reported for ultrasound reports (thyroid, RUQ, endometriosis, pediatric hydronephrosis). I found **no kidney-echogenicity or CKD ultrasound model trained on report-derived labels**. Published CKD ultrasound models used eGFR from lab creatinine instead.

### Cited Findings
- **NegBio** (rule-based negation/uncertainty detection): precision 89.8%, recall 85.0%, F1 87.3% on OpenI chest reports, beating NegEx. — [NegBio, arXiv 1712.05898](https://arxiv.org/pdf/1712.05898)
- The **CheXpert labeler** improved on NegBio. On MIMIC-CXR, 687 reports were manually labeled by a radiologist; mention-extraction F1 ranged from 0.462 (enlarged cardiomediastinum) to 0.930 (consolidation). — [MIMIC-CXR-JPG, arXiv 1901.07042](https://arxiv.org/pdf/1901.07042); [CheXpert, arXiv 1901.07031](https://arxiv.org/pdf/1901.07031)
- **CheXbert** (BERT labeler) improved F1 over the CheXpert labeler by 0.055 on MIMIC-CXR. — [CheXbert, arXiv 2004.09167](https://arxiv.org/pdf/2004.09167v2)
- An in-house comparison of automated and manual labels found negation-detection F1 of 0.624–0.981 and uncertainty-detection F1 of only 0.353–0.725. Uncertainty is the hardest category. — per search snippet, [Thieme RöFo 10.1055/a-2234-8268](https://www.thieme-connect.com/products/ejournals/html/10.1055/a-2234-8268)
- A German chest X-ray BERT labeler trained on weak rule-based labels plus a small manual set beat rule-based labeling alone. A pneumothorax image classifier trained on its labels matched one trained on manual labels. — [RöFo 2025;197:55-64](https://thieme-connect.com/products/ejournals/html/10.1055/a-2287-5054)
- **Thyroid US:** GPT-4 assigned U-scores to 14,248 thyroid ultrasound reports and agreed with refined human scores in about 97.7% of cases. Disagreements came from ambiguous wording, multi-nodule reports and documented uncertainty. — per search snippet, [IOS Press](https://ebooks.iospress.nl/volumearticle/73578)
- **Endometriosis transvaginal US** (49 reports): a local 20B LLM reached about 86% accuracy against expert extraction. Most errors were semantic and were not fixed by prompt engineering. — [arXiv 2601.09053](https://arxiv.org/abs/2601.09053v1)
- **RUQ ultrasound:** a locally deployed Llama-3-70B turned 9,555 reports into 42 categorical labels for multitask image-model training. Many categories were rare. The abstract page I fetched did not give label-validation accuracy. — [arXiv 2601.12174](https://arxiv.org/pdf/2601.12174)
- **Pediatric hydronephrosis US reports:** a model fine-tuned on hydronephrosis labels beat GPT-3.5-Turbo by 20–30% in accuracy. A separate abstract reports that zero-shot Llama-2 performed well at reading renal US impressions for hydronephrosis; no figures were in the excerpt. — [SPU 2024 abstract 59](https://fallcongress.spuonline.org/program/2024/59.cgi); [SPU 2024 P22](https://fallcongress.spuonline.org/program/2024/P22.cgi)
- **CT:** LLM-extracted diagnostic labels from reports reached AUC above 96% and were used as "silver-standard" pretraining labels. — [MICCAI 2025 paper 0580](https://papers.miccai.org/miccai-2025/0580-Paper3788.html)
- **Kidney CKD US models used lab labels, not report labels.** Kuo et al. 2019 (China Medical University Hospital, Taiwan; 4,505 images, ~1,300 patients) took eGFR from the creatinine closest to the scan within ±4 weeks. CKD (eGFR<60) accuracy was 85.6% and AUC 0.904, against 60.3–80.1% accuracy for four nephrologists. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- Other Taiwanese kidney US work: the National Taiwan Ocean University / Chang Gung group (GAN + MobileNetV2, 81.9% four-stage accuracy), and a TMU three-hospital study (632 CKD patients) predicting interstitial fibrosis with biopsy as the reference. — [Appl Sci 12:352](https://mdpi-res.com/d_attachment/applsci/applsci-12-00352/article_deploy/applsci-12-00352.pdf); [CGU pure](https://pure.lib.cgu.edu.tw/en/publications/prediction-of-chronic-kidney-disease-stages-by-renal-ultrasound-i-3/); [BMJ Health Care Inform 32:e101192](https://informatics.bmj.com/content/32/1/e101192.full.pdf)

### Inferences
- Pitfalls to design for:
  - **Negation**, e.g. "no hydronephrosis" or "no stone".
  - **Uncertainty**, e.g. "suspect", "r/o", "cannot exclude", "mildly increased?". Treat as a separate class or drop.
  - **Laterality**: bilateral, R't/L't abbreviations, "both kidneys". The label must be attached to the image's side.
  - **Report-image mismatch**: the report covers the whole exam (both kidneys, many frames), but a single stored image may not show the finding. A cyst mentioned in the report may not be visible in the 5 saved frames.
  - **Comparison language**: "stationary compared with previous", "status post".
- A small, locally run LLM or regex pipeline with a manually checked validation subset (for example 100–200 reports) fits the scale of 195 patients. At this size, the student, with a physician spot-checking ambiguous cases, could review every report directly.

### Gaps
- I found no paper validating report-derived **echogenicity** labels against expert re-reading of images.
- I found no published Chinese-language report labeler for ultrasound.

## Q3. Agreement of report-stated echogenicity with expert re-reading or eGFR; inter-observer variability

### Takeaway
Subjective echogenicity correlates only **moderately to weakly** with eGFR (|r| ≈ 0.35–0.57 in small studies). I found no kappa specifically for 4-grade cortical echogenicity grading. Reports are therefore a noisy label, both against an expert re-read and against eGFR.

### Cited Findings
- In 61 patients with echogenic kidneys, echogenicity grade correlated with creatinine (r=0.571) and with eGFR (r=−0.349). — per search snippet, [JNHRC](https://jnhrc.com.np/index.php/jnhrc/article/view/3093)
- In children, an objective echogenicity index correlated with eGFR at r=−0.46, but the correlation did not persist within subgroups. A pediatric biopsy study found r=−0.352 with eGFR. — per search snippets, [BVS mdl-38219260](https://busqueda.bvsalud.org/portal/resource/es/mdl-38219260); [BVS mdl-23103325](https://busqueda.bvsalud.org/portal/resource/es/mdl-23103325)
- In chronic renal failure (Brazil, 2 blinded radiologists), interobserver agreement was 0.754 for cortical thickness, 0.833 for bipolar length and 0.523 for parenchymal thickness. Correlations with GFR were moderate to poor (r=0.478, 0.380, 0.277). — [Radiologia Brasileira v48n1a06](https://www.scielo.br/j/rb/a/VLcHYqjHh8Pv9PWbbrJYXDH/?lang=en)
- Araújo et al. reported **no** inter- or intra-observer statistics because a single operator did all scans, and they admit that echogenicity grading is visual. — [PMC7137523](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137523/)
- Some CKD US studies apply tissue harmonic and speckle-reduction imaging specifically "to reduce the interobserver bias" when grading echogenicity, which implies that bias is acknowledged. — [PMC6516621](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6516621/)
- In Kuo et al., experienced nephrologists reading images alone reached only 60.3–80.1% accuracy for eGFR<60. Visual impressions, and the reports written from them, are therefore imperfect proxies of function. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)

### Inferences
- Report-derived echogenicity labels carry three error sources: inter-reader variability (different radiologists or nephrologists wrote the reports), machine gain/TGC settings, and text-to-grade mapping error. The resulting noise is likely larger than the Grade 0 vs 1 distinction.
- Practical design: use report labels as a coarse binary (normal vs increased echogenicity/PRD) or 3-class label. Have a physician re-grade a subset (for example 50 patients) to measure report-vs-expert kappa. Keep eGFR as the primary objective label.

### Gaps
- I found no published kappa for subjective renal cortical echogenicity grading versus the liver.
- I found no study comparing report text against blinded re-reading for renal echogenicity.

## Q4. Taiwan legal/ethical requirements and data sources

### Takeaway
Retrospective use of existing reports is **human research** under 人體研究法. It needs IRB approval (Art. 5) unless it falls in the MOHW exempt-from-review list. Consent can be waived under the MOHW 免同意 announcement for minimal-risk research using existing data. 個資法 Art. 6(1)(4) allows medical data for academic research if, after the provider processes it, the data can no longer identify a specific person. In practice, a hospital PI must file the IRB application and the hospital's data-release request. A student cannot obtain reports independently.

### Cited Findings
- **人體研究法 Art. 4** defines 去連結 (de-linking) as making research material permanently unlinkable to the person by any means. — [law.moj.gov.tw L0020176](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0020176)
- **Art. 5:** a research plan must be approved by an ethics review committee (審查會) before it starts, unless it is in the scope the competent authority has announced as exempt from review. — [law.moj.gov.tw](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0020176)
- **Art. 12:** consent is required unless the research is in the scope the authority has announced as exempt from consent. — [law.moj.gov.tw](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0020176)
- **Art. 19:**
  - Materials must be destroyed after the study unless consented or de-linked.
  - Use of linked materials beyond the consented scope requires new review and consent.
  - Transferring linked materials abroad needs written consent plus IRB review and approval by the competent authority. This is relevant if a cloud LLM outside Taiwan processes report text.
  - Source: [law.moj.gov.tw](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0020176)
- **MOHW consent-exemption announcement** (衛署醫字第1010265083號, 2012-07-05) lists four exempt situations:
  - evaluating public-policy effectiveness;
  - using de-linked data from a lawful biobank;
  - minimal-risk research where waiving consent does not affect subjects' rights;
  - minimal-risk research that would be impracticable if consent were required.

  Source: [NCCU copy](https://ord.nccu.edu.tw/files/archive/383_9cbeb258.pdf); [Taipei City Hospital waiver form citing the notice](https://www-ws.gov.taipei/001/Upload/446/relfile/22076/9096693/6620ed8c-890d-4b13-a62e-f1ba45459dff.odt). The current version and any amendments were not verified.
- The NTUH ethics center (2024) notes that chart-review studies are a large share of IRB workload. Studies using only **existing retrospective records** typically request a consent waiver, while studies that also collect future follow-up data are usually required to obtain consent. NTUH requires a dedicated 「使用病歷資料進行研究申請表」. — [NTUH 倫理中心季刊 2024 B1](https://www.ntuh.gov.tw/ckfinder_file/RECO/files/%E5%80%AB%E7%90%86%E4%B8%AD%E5%BF%83%E5%AD%A3%E5%88%8A/2024%E5%B9%B4%E5%AD%A3%E5%88%8A%E6%96%87%E7%AB%A0(I1-I4)/01%E6%9C%9F/B1_%E5%A4%A7%E6%95%B8%E6%93%9A%E6%88%96%E7%97%85%E6%AD%B7%E7%A0%94%E7%A9%B6%E5%B8%B8%E8%A6%8B%E5%95%8F%E9%A1%8C%E6%A1%88%E4%BE%8B%E6%8E%A2%E8%A8%8EL.pdf)
- **個資法 Art. 6(1)(4)** covers sensitive data, including medical records and medical data. Public agencies or academic research institutions may collect and use it for medical, health or crime-prevention statistics or research if necessary, **and** if the data, once processed by the provider or as disclosed by the collector, cannot identify a specific person. — [MOJ interpretation 法律字第10603508010號](https://laws.gov.taipei/law/Interpretation/RelatedLaw/FE301780)
- **Constitutional Court 111憲判字第13號 (2022, NHIRD case):** Art. 6(1)(4) is constitutional. However, the absence of an opt-out right when NHI data is used outside its original purpose for research is unconstitutional, and the court ordered amendments within 3 years. — per search snippet, [Judicial Yuan](https://cons.judicial.gov.tw/download/download.aspx?id=456493)
- **NHIRD** is claims-based and historically lacked clinical measurements and labs. The NHIA later added uploaded lab results and examination reports, plus imaging data. Since 2016, analysis has been allowed only at the MOHW Health and Welfare Data Science Center and its branches. Sources conflict on how much report or imaging content is available. — [Research Square, Intro to NHIRD](https://www.researchsquare.com/article/rs-6444/v2); [PubMed 31118821](https://pubmed.ncbi.nlm.nih.gov/31118821/); [PMC6367203](https://pmc.ncbi.nlm.nih.gov/articles/PMC6367203)
- **TMUCRD** (3 TMU hospitals, OMOP CDM) includes unstructured data such as "physicians note, pathology report, image examination, and radiology report". The TMU page gives a 1998–2023 span; the journal paper says 2004–2021. — [TMUCRD, PMC11097871](https://pmc.ncbi.nlm.nih.gov/articles/PMC11097871/); [TMU ODS](https://ods.tmu.edu.tw/Research_papers.php); [OHDSI slides](https://www.ohdsi.org/wp-content/uploads/2022/12/4_Research-using-TMUCRD-Data_Jason-Hsu.pdf)
- The **CGRD** (Chang Gung) is a multi-institutional EHR database. I did not find documentation in this session confirming ultrasound report text fields. — [CGU pure, CGRD paper](https://pure.lib.cgu.edu.tw/en/publications/the-chang-gung-research-databasea-multi-institutional-electronic-/)

### Inferences
- Because the images already exist and carry eGFR, the student's team probably already has an IRB protocol. Adding report text is likely a **protocol amendment (變更案)** to that IRB rather than a new study. The amendment would add a 免同意 justification (minimal risk, impracticable to re-contact) and a data-release request to the hospital's medical records or information office, or clinical data center. Confirm the exact route with the hospital IRB.
- Report text must be de-identified **by the hospital side (the provider)** before release, which matches 個資法 Art. 6(1)(4). Items to remove:
  - name, chart number, ID number, birth date (keep age);
  - exam/accession numbers (replace with study codes);
  - physician and sonographer names;
  - hospital/department names if required;
  - free-text dates (shift them or convert to relative days);
  - any phone numbers or addresses in indications.
- Do not send identifiable report text to overseas cloud LLM APIs. Use a local model, or use only de-linked text and get explicit IRB approval for it (see Art. 19 transfer rule).
- NHIRD and HWDC are not practical for this project. Access is restricted to on-site analysis, and they do not provide matched DICOM images.

### Gaps
- I did not verify the current (2025–2026) text of the MOHW 免審/免同意 announcements, or whether the 個資法 amendments following 111憲判字13號 (e.g., 2023 PDPC establishment, 2025 amendments) changed research-use rules.
- I did not confirm whether NTUH iHi or CGRD release ultrasound report text.

## Q5. Practical recommendations: fields, de-identification, mapping reports to images

### Takeaway
Request the minimal de-linked fields with a study code shared with the image set. Match reports to images on study code, exam date and side. Validate the text-to-label mapping on a manually reviewed subset before trusting it.

### Cited Findings
- Kuo et al. linked lab labels to images using a ±4-week window between creatinine and scan, and split train/test by hashed patient ID to avoid leakage. — [PMC6550224](https://pmc.ncbi.nlm.nih.gov/articles/PMC6550224/)
- LLM ultrasound extraction is strongest for format consistency (dates, numbers) and weakest for semantic or contextual interpretation. Ambiguous and multi-finding reports drive errors. — [arXiv 2601.09053](https://arxiv.org/abs/2601.09053v1); [IOS Press thyroid](https://ebooks.iospress.nl/volumearticle/73578)
- Uncertainty-detection F1 is low (0.35–0.73) even for mature labelers. — [Thieme RöFo](https://www.thieme-connect.com/products/ejournals/html/10.1055/a-2234-8268)

### Inferences
- **Fields to request**, per exam:
  - study code, matching the existing image IDs;
  - exam date, or relative day offset from the first exam;
  - exam type/order code (renal US vs abdominal US);
  - the full findings text and the impression/conclusion text;
  - reporting role (radiologist, nephrologist or sonographer), as a category without names;
  - machine model, if available;
  - nearest creatinine/eGFR date offset.
- **Label schema**, per side (R/L): echogenicity (normal / increased / not mentioned / uncertain), CMD (preserved / poor), length in cm, cyst (Y/N/size), stone (Y/N), hydronephrosis (none / mild / moderate / severe), and "PRD" impression. Keep "not mentioned" separate from "negative".
- **Mapping:** join on study code and same exam date. Assign the side from the DICOM/image annotation (on-screen "RK"/"LK" or "Rt kidney" text) and apply that side's report label. Exclude images whose side cannot be determined. Exclude exams where multiple reports or addenda conflict.
- **Validation:** have a physician (or the student plus a physician on edge cases) hand-label about 100 reports. Report precision and recall per label. Separately, have a physician re-grade images for a subset to quantify report-vs-image agreement (kappa). Present report-derived labels as "weak/silver" labels in the thesis.

### Gaps
- I found no published protocol specific to mapping Taiwanese kidney US reports to stored frames.
