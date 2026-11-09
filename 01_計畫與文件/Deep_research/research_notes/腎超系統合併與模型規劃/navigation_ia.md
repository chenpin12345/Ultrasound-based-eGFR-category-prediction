# Navigation & Information Architecture for a Merged Kidney-Ultrasound AI Platform (Research + Clinical)

> Scope: how established tools structure navigation, role-based navigation, navigation guidelines, report/AI-output UI evidence, and a proposed merged navigation tree.
> Labels used: **[Evidence]** = documented guideline/peer-reviewed/official doc; **[Opinion]** = vendor/expert opinion or my inference. Research date: 2026-10. Some sources (RSNA Radiology: AI full text, Material 3 page, CVAT manual page) could not be fetched in full; noted in Gaps.

---

## Q1. How do established tools structure navigation/workflow?

### Takeaway
Mature ML tools organise top-level navigation by **object/container** (Projects, Datasets, Pipelines, Models, Endpoints), and put the step-by-step workflow *inside* a container (runs, tasks, jobs). Clinical imaging tools organise by **worklist → case viewer (mode) → report**, where the per-case workflow is a mode/route launched from the list, not a set of sidebar items.

### Cited Findings
- **ClearML** [Evidence]: current WebApp sidebar has ~6 modules: Projects ("the main experimentation page"), Datasets, Pipelines, Model Endpoints, Orchestration (workers/queues/autoscaling), Apps. Older versions also had Dashboard and Reports. Pipelines are shown as cards; clicking opens that pipeline's runs table. — [ClearML WebApp overview](https://clear.ml/docs/latest/docs/webapp/webapp_overview/); [Pipeline page](https://clear.ml/docs/latest/docs/webapp/pipelines/webapp_pipeline_page); [Datasets page](https://clear.ml/docs/latest/docs/webapp/datasets/webapp_dataset_page/)
  - Note: Datasets was moved to its own sidebar button "just under Projects" (users initially could not find their data) — evidence that relocating items confuses existing users. — [ClearML FAQ](https://faq.clear.ml/question/1523706241937838080/hi-i-ve-been-using-your-saas-platform-for-over-a-month-now-but-today-i-suddenly-noticed-most-of-my-data-is-missing-i-see-that-i-have-40-tasks-in-my-data-project-from-the-dashboard-as-it-should-be-but-inside-the-project-i-can-only-see-6-i-couldn-t-fin?desc=false)
- **MLflow UI** [Evidence]: Experiment = group of runs/models for a task; Runs are searchable/comparable by params/metrics; a "Models" tab lists models within an experiment; Model Registry is a separate area for registered models (versioning/stages). Training monitoring = run view, not a separate top-level page. — [MLflow Tracking docs](https://mlflow.org/docs/latest/ml/tracking/)
- **CVAT** [Evidence]: hierarchy Project → Task → Job. A project groups tasks with shared labels; a task holds data + label schema; jobs are subdivisions of a task assignable to different annotators. Top-level pages: Projects, Tasks, Jobs (plus Cloud storages/Models in workspace docs). — [CVAT workspace docs](https://docs.cvat.ai/docs/workspace/); [Tasks page](https://docs.cvat.ai/docs/workspace/tasks-page/); [key concepts summary](https://www.mintlify.com/cvat-ai/cvat/key-concepts)
- **Label Studio** [Evidence]: Project is the basic unit with its own settings, data and annotations; the Data Manager is the per-project table for tasks; labeling interface configured per project from templates. — [Label Studio overview](https://docs.heartex.com/guide/get_started); [Create and configure projects](https://docs.humansignal.com/guide/setup_project)
- **OHIF Viewer** [Evidence]: Study List (worklist) is the default landing page; a **Mode** is "a viewer app configured to perform a specific task" (e.g., segmentation, lesion tracking) tied to a route; modes available for a study appear in the study list; modes compose reusable extensions (panels, layout, data source). Study list query limit default 101. — [OHIF Modes](https://docs.ohif.org/platform/modes/); [OHIF Extensions](https://docs.ohif.org/platform/extensions/); [OHIF architecture](https://docs.ohif.org/development/architecture)
  - Community note [Opinion]: worklist launches a single study per mode. — [OHIF community](https://community.ohif.org/t/custom-modes-for-an-alternative-study-list/878)
- **MONAI Label** [Evidence]: server–client architecture; AI "apps" exposed over HTTP; clients are plugins in 3D Slicer, OHIF, QuPath; supports interactive models (DeepGrow/DeepEdit) and active learning (suggest next sample to annotate, retrain on new labels). I.e., annotation ↔ training loop lives inside the viewer, not as separate nav pages. — [MONAI Label PyPI](https://pypi.org/project/monailabel/0.2.0); [noze.it overview (secondary)](https://www.noze.it/en/insights/monai-label-ai-annotation/)
- **PACS/worklist → viewer → report** [Evidence, by analogy]: in the JAMIA study of Veye Lung Nodules, the AI ran in the PACS background and placed results into the original diagnostic series, needing no extra steps; earlier CAD required opening a separate app, locating the study and running analysis manually, and "many radiologists found it cumbersome and often skipped it." — [Farič et al., JAMIA 2024;31(1):24–34](https://pmc.ncbi.nlm.nih.gov/articles/PMC10746311/)

### Inferences
- [Opinion] Merge "training monitor" into the training run detail (MLflow/ClearML pattern) rather than a separate page in two areas.
- [Opinion] Per-case clinical steps (segmentation → grade → lesions → report) should be one **exam workspace** opened from a worklist (OHIF "mode" pattern), not 6 sidebar items.
- [Opinion] Per-step processing pages (image processing, mask generation, feature extraction) match ClearML's "Pipelines → runs → step" pattern: one Pipelines entry, steps as stages inside it; keep standalone step pages only for power users.
- [Opinion] The "feedback to annotation" loop maps to MONAI Label/CVAT: clinician-corrected masks/grades create annotation **tasks/jobs** in a review queue.

### Gaps
- Could not fetch W&B, Encord, V7 navigation docs within the tool budget; no verified description of their sidebars here.
- 3D Slicer module navigation not researched (it is a desktop module-selector paradigm, less applicable to web nav).

---

## Q2. Role-based navigation & clinician-facing AI (HCI / medical informatics evidence)

### Takeaway
Evidence strongly supports putting AI output **inside the clinician's existing workflow with no extra steps** and treating AI as an assistive "second reader"; automation-bias studies show incorrect AI suggestions sharply degrade accuracy even for experts, so AI output should be secondary, reviewable and attributable. No peer-reviewed study was found that directly compares "separate areas" vs "role-based visibility" navigation.

### Cited Findings
- [Evidence] AI integrated into PACS (no separate app) caused little workflow disruption; separate-app CAD was often skipped. Radiologists used it as a "second reader"; experts reviewed images first, then checked AI output, and discounted known false positives; experts worried novices may over-rely. Authors recommend treating AI as assistive with clinician retaining responsibility, educating users on strengths/limitations, and accounting for local workflows. — [Farič et al., JAMIA 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10746311/)
- [Evidence] Radiology CDS/AI is poorly integrated into radiologist workflow; interventions grouped around exam-centric time points. — [Burns et al., PLOS Digital Health 2024 (DOAJ record)](https://doaj.org/article/2c879528afe14b67a7f57248058eff45)
- [Evidence] Automation bias: 27 radiologists, 50 mammograms; with incorrect purported-AI BI-RADS suggestions, inexperienced readers' accuracy fell from ~80% to <20%, very experienced (>15 y) from 82% to 45.5% (Dratsch et al., Radiology, May 2023). Authors call for safeguards. — [RSNA news](https://www.rsna.org/news/2023/may/ai-bias-may-impair-accuracy); [AuntMinnie](https://www.auntminnie.com/clinical-news/womens-imaging/breast/article/15633344/breast-radiologists-impacted-by-automation-bias-when-using-ai)
- [Evidence] Pathologists (n=21) wanted upfront **global** information about the AI (known strengths/limitations, what it was optimized for) before case-level output, akin to judging a colleague's second opinion ("Hello AI", Cai et al., PACM HCI/CSCW 2019). — [ResearchGate PDF](https://www.researchgate.net/profile/Lauren_Wilcox2/publication/337135587_Hello_AI_Uncovering_the_Onboarding_Needs_of_Medical_Practitioners_for_Human-AI_Collaborative_Decision-Making/links/5e1ac19ba6fdcc28376bb0be/Hello-AI-Uncovering-the-Onboarding-Needs-of-Medical-Practitioners-for-Human-AI-Collaborative-Decision-Making.pdf)
- [Evidence] Workflow-integration design work in pathology (xPath, NaviPath) emphasises fitting AI into existing diagnostic navigation. — [xPath arXiv](https://arxiv.org/pdf/2006.12683); [NaviPath arXiv](https://arxiv.org/pdf/2302.07309)
- [Evidence] Case study on responsible AI workflow integration in radiology (feeding tube qualification). — [arXiv 2405.05299](https://arxiv.org/pdf/2405.05299) (not read in full)

### Inferences
- [Opinion] Use **two workspaces (Clinical / Research)** with a top-level switcher, and **role-based visibility** (clinician accounts see only Clinical; researchers see both). Rationale: clinicians' path must be short and free of research tools (Farič: extra steps → non-use); researchers need access to clinical outputs for feedback.
- [Opinion] A clinician-facing "Model info / 模型說明" panel (intended use, validation metrics, known failure modes such as cyst vs. hydronephrosis confusion) satisfies "Hello AI" onboarding needs — place it in the exam workspace, not in the research model center.
- [Opinion] Clinician should be able to form an impression before seeing AI grade (optional "reveal AI" toggle or AI panel collapsed by default) to mitigate automation bias (Dratsch); flag as design hypothesis, untested here.

### Gaps
- No direct empirical comparison of separate-area vs role-filtered navigation in clinical apps found.
- Alert-fatigue literature (CDS interruptive alerts) not fetched within budget.

---

## Q3. Navigation design guidelines (items per group, grouping, depth, global vs local settings/trash, wizard vs page-per-step)

### Takeaway
Left vertical nav suits growing IAs; 5–10 top-level items with group headers and ≤2 levels is the standard guidance; Settings goes in the footer; >7–9 items is acceptable if prioritized. Long multi-step processes that span sessions → task-list (hub) pattern, not a page per step in the sidebar.

### Cited Findings
- [Evidence] NN/g: vertical nav is "an excellent choice for sites where the navigation is likely to grow"; keep it visible (don't hide in hamburger on desktop); more than 7–9 top-tier categories is OK if planned — put less important items lower; use text labels, left-aligned, front-loaded keywords ("a word is worth a thousand pictures"). — [NN/g Left-Side Vertical Navigation](https://www.nngroup.com/articles/vertical-nav/); [NN/g: How many items in a nav menu (it's not 7)](https://www.nngroup.com/videos/number-items-navigation-menu/)
- [Evidence] Microsoft Fluent NavigationView: use left nav for **5–10 equally important top-level categories** (top nav for ≤5); use ItemHeaders to label groups and Separators to group; Settings item at the bottom by default; FooterMenuItems for items like Account/Help; "we recommend keeping your app's navigation hierarchy shallow. We believe **two levels** is ideal." — [Microsoft Learn NavigationView](https://learn.microsoft.com/en-us/windows/apps/design/controls/navigationview)
- [Evidence] PatternFly: use vertical nav for ≥5 primary items; group related items under a non-interactive group header, or use expandable nesting. — [PatternFly navigation guidelines](https://www.patternfly.org/components/navigation/design-guidelines/)
- [Evidence] Material 3 (via SAP Fiori summary): navigation drawer for five or more destinations; being superseded by expanded navigation rail in M3 Expressive. — [SAP Fiori M3 navigation drawer](https://www.sap.com/design-system/fiori-design-android/v25-8/components/m3-standard-components/navigation-drawer/usage) (official m3.material.io page could not be rendered)
- [Evidence] Queensland Health design system: very long vertical menus push content below the fold. — [QLD Health vertical nav](https://www.design-system.health.qld.gov.au/components/navigation-vertical/tabs/overview)
- [Evidence] GOV.UK "Complete multiple tasks" (task list): only for longer transactions done over several sessions; first try to simplify; group related activities into verb-named tasks; statuses (Completed, Incomplete, In progress, Cannot start yet, There is a problem) — keep the set small; let users complete tasks in any order where possible. — [GOV.UK task list pattern](https://design-system.service.gov.uk/patterns/complete-multiple-tasks/)

### Inferences
- [Opinion] Research area's 13+ flat items exceeds the 5–10 per level guidance; group into 3–4 headed groups of 2–4 items each.
- [Opinion] Trash: one **global** trash (footer) with a type filter (dataset/model/exam/report) instead of three area-specific bins; Settings: one global footer entry with tabs (system / devices / models-in-production / users). Supported by Fluent's footer pattern; consolidation itself is inference.
- [Opinion] The new 8-step clinical workflow → GOV.UK-style **status list** inside the exam workspace (Import ✓ → QC ✓ → Segmentation ✓ → Echogenicity/Grade ✓ → Lesions ⚠ → Patient integration → Draft report → Sign), not 8 sidebar items. One-click pipeline for research → same stepper with run status.

### Gaps
- No quantitative study found on optimal items per sidebar group for B2B/scientific apps; guidance is heuristic.

---

## Q4. Radiology report / structured reporting UI and showing AI probabilities

### Takeaway
Structured reporting with AI-prefilled fields (radiologist reviews and signs) is faster and rated higher quality in one 2024 study; the RSNA/IHE ecosystem standardises templates (RadReport, MRRT, RadElement). Evidence on showing probabilities is mixed: confidence scores did not improve, and may increase over-reliance compared with plain categorical/text output.

### Cited Findings
- [Evidence] RSNA RadReport: free library of peer-reviewed templates using RadLex terminology and RadElement CDEs (with ACR); API for vendors; IHE MRRT defines HTML5-based template format. — [RSNA RadReport](https://www.rsna.org/practice-tools/data-tools-and-standards/radreport-reporting-templates); [RSNA 2019 redesign news](https://www.rsna.org/news/2019/june/radreport-redesign); [IHE MRRT proposal](https://wiki.ihe.net/index.php/Management_of_Radiology_Report_Templates_-_Detailed_Proposal_-_2012-2013)
- [Evidence] ESR (2018 white paper) on structured reporting: standardised structures aid completeness/comparability; enable automatic functions and integration with clinical parameters; vendor integration essential. A later ESR update notes routine implementation still lacking and names LLMs as a potential aid (per Busch et al. 2025 review; year of update not verified). — [ESR statement PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5825315); [ESR AI blog tag](https://app.myesr.org/ai-blog-tag/structured-reporting/)
- [Evidence] Jorg et al., Insights into Imaging 2024 (doi 10.1186/s13244-024-01660-5): pipeline auto-prepopulates structured chest X-ray reports with commercial AI results; reporting faster than free-text or conventional structured reporting, and quality rated higher. — [ESR AI blog summary](https://www.myesr.org/ai-blog/novel-reporting-workflow-for-automated-integration-of-ai-results-into-structured-radiology-reports/)
- [Evidence, partially verified] Radiology: AI paired-reader study (10 radiologists): text-only AI output improved AUC vs no AI (0.87 vs 0.82, P<.001); adding the AI confidence score gave no further performance difference. — [Radiology: AI ryai.220079](https://pubs.rsna.org/doi/epdf/10.1148/ryai.220079) (full text 403; figures from search snippet — verify)
- [Evidence] Johns Hopkins (Radiology): specific AI explanations increased accuracy/efficiency but fostered misplaced trust when AI was wrong. — [JHU CS news](https://www.cs.jhu.edu/news/explain-yourself-designing-ai-for-better-human-machine-teaming/)
- [Evidence, preliminary] Duke 2023 poster: interpretable (prototype-based) explanation + confidence UI increased readers' confidence and accuracy (preliminary). — [Duke poster](https://cs.duke.edu/sites/cs.duke.edu/files/documents/UI-Communicate-Interpretable-AI-Radiologists-poster2023.pdf)
- [Evidence, preprint] Breast cancer AI-explanation study on clinician trust/accuracy. — [arXiv 2412.11298](https://arxiv.org/pdf/2412.11298) (not read in full)
- [Unverified] A search snippet described a 28-healthcare-professional experiment where high confidence scores increased trust and over-reliance; exact source not confirmed — see Gaps.

### Inferences
- [Opinion] Report editor: structured template (kidney size, cortical echogenicity Grade 0–3, cyst/stone/hydronephrosis per side, impression) with AI-prefilled values visually marked "AI 建議" until the clinician confirms/edits; sign-off locks the report; every edited field logged as feedback (diff AI vs signed) → annotation queue.
- [Opinion] Show categorical grade + key evidence (overlay, measured echogenicity ratio) prominently; put raw probabilities behind an expander/tooltip ("details"), consistent with ryai.220079 finding no added value from confidence scores.
- [Opinion] Map fields to RadLex/RadElement where possible for future interoperability.

### Gaps
- No kidney-ultrasound-specific structured reporting template verified on RadReport within budget.
- Original source of the "28 HCP confidence-score over-reliance" claim not confirmed.

---

## Q5. Proposed navigation tree for the merged system

### Takeaway
Two workspaces (臨床 Clinical / 研究 Research) via a top-bar switcher + role-based visibility; Clinical = 4 sidebar items built around a worklist → exam workspace → report; Research = 4 headed groups (資料 / 流程 / 模型 / 分析) with 10 items; global footer = 任務 Jobs, 回收桶 Trash, 設定 Settings. All [Opinion], grounded in the evidence above.

### Cited Findings (supporting principles)
- 5–10 top-level items with group headers, ≤2 levels; Settings in footer — [Microsoft Learn NavigationView](https://learn.microsoft.com/en-us/windows/apps/design/controls/navigationview)
- Worklist → task-specific mode — [OHIF Modes](https://docs.ohif.org/platform/modes/)
- Container-first ML nav (Projects/Datasets/Pipelines/Models) — [ClearML WebApp](https://clear.ml/docs/latest/docs/webapp/webapp_overview/); runs/registry — [MLflow](https://mlflow.org/docs/latest/ml/tracking/)
- AI in-workflow, no extra steps, assistive — [Farič JAMIA 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10746311/)
- Multi-step status list — [GOV.UK task list](https://design-system.service.gov.uk/patterns/complete-multiple-tasks/)

### Proposed tree [Opinion]

**Global top bar**: Workspace switcher（臨床 Clinical ｜ 研究 Research；臨床帳號只看到 Clinical）· Global search (patient ID / exam / dataset / model) · 背景任務指示器 (running jobs badge) · 通知 · 使用者

**A. 臨床工作台 Clinical（4 items + footer）**
1. 工作清單 Worklist — home；exam rows with status chips: 接收中 Received → 處理中 Processing → AI 完成 AI ready → 草稿 Draft → 已簽核 Signed；filters: 今日 / 待我簽核 / 有異常 (lesion flagged)
   - → **檢查工作區 Exam workspace** (detail page, not in sidebar): 左 viewer（image/video, segmentation overlay），右 status list：匯入 → 品質篩選 QC → 分割 → 回音度量化 & Grade 0–3 → 病灶偵測（cyst/stone/hydronephrosis）→ 病人層級整合 → 報告草稿；「模型說明」 drawer
   - → **報告編輯 Report editor**: structured template, AI-prefilled fields marked, 編輯 → 簽核 Sign；edits auto-sent to feedback queue
2. 影像接收 Acquisition — 超音波儀器接收；「雙機示範 Demo」as a mode/toggle on this page (not a separate nav item)
3. 病人與檢查 Patients & Exams — patient-level history, prior exams, trend of Grade
4. 報告中心 Reports — 待簽核 / 已簽核 / 退回；export

**B. 研究工作台 Research（4 groups, 10 items）**
- 群組 資料 Data
  1. 總覽 Overview (dashboard: datasets, running jobs, latest model metrics)
  2. 資料集 Datasets — tabs: 影像 / 病人對應 Patient mapping / 資料切分 Splits / 版本
  3. 標註與回饋 Annotation & Feedback — queue of clinician corrections (mask/grade/lesion diffs) + annotation tasks (CVAT/MONAI-Label-style)
- 群組 流程 Pipeline
  4. 流程執行 Pipelines — one-click pipeline wizard & run list; stages: 品質篩選 → 影像處理 → 分割/遮罩 → 特徵擷取 → 推論
  5. 影像處理與遮罩 Preprocessing & Masks — standalone step tools (merge image processing + mask generation; power users)
  6. 特徵擷取 Features
- 群組 模型 Models
  7. 訓練 Training — new run; run detail includes 即時監控 Training monitor (removes duplicate)
  8. 實驗與評估 Experiments & Evaluation — compare runs/models (merges experiments + evaluation & comparison)
  9. 模型庫 Model Registry — filter by type: 判讀模型 Judgment (eGFR/Grade) / 輔助模型 Auxiliary (segmentation, lesion) ；stage: 研究 / 候選 / 臨床上線 (replaces clinician analysis plans = which model versions are deployed to Clinical)
- 群組 分析 Analysis
  10. AI 分析 AI Analysis — one page, input mode toggle: 僅影像 Image-only ｜ 影像＋臨床資料 Image + clinical (merges two AI analysis pages)

**C. Global footer (both workspaces, role-filtered)**
- 任務紀錄 Jobs & Logs — job history + logs/job monitor (merges research job history, clinical logs & job monitor, training website job history)
- 回收桶 Trash — single global bin, filter by object type (merges 3 bins)
- 設定 Settings — tabs: 一般 / 裝置 Devices / 使用者與角色 / 系統

**Item count**: Clinical 4 + footer 3 = 7 visible; Research 10 + footer 3 = 13 visible but in 4 headed groups of 2–3 (within Fluent 5–10 top-level guidance if group headers count as the top level). Previous: 14 + 8 + 7 + 11 = 40 items → ~17 unique destinations.

**Mapping of merged training website (11 items)**: dashboard → 總覽；datasets → 資料集；image processing + mask generation → 影像處理與遮罩；feature extraction → 特徵擷取；training + training monitor → 訓練；AI inference → AI 分析 / 流程執行；model management → 模型庫；job history → 任務紀錄；settings → 設定.

### Inferences / naming notes
- [Opinion] Use verb/task-neutral nouns with front-loaded keywords (NN/g) and keep English technical term in parentheses only where ambiguous (e.g., "分割 Segmentation").
- [Opinion] Keep old routes as redirects to avoid the ClearML "where did my data go" effect.
- [Opinion] "Model Center" disappears as a separate area: researchers manage models under 研究 > 模型; clinicians see only the active model's info card inside the exam workspace.

### Gaps
- No usability testing of this tree; recommend card sorting / tree testing with 5–8 users per role before implementation (NN/g method, not fetched here).
