# 腎超系統合併策略：把 System A (ISU_AI_KUA) training engine 併入 System B (腎超新)

Context: A = older FastAPI+SQLite+React training engine (UNet 512, ResNet18/MobileNetV2/EfficientNet-B3/MLP-ResNet18, CORAL, K-fold, resume, SSE, background queue). B = newer, richer main body (research / model center / clinician area, patient mapping, protected-compute manifest); B's 60 imported models and mask functions get discarded. Data: 975 images, ~181 patients; old splits were image-level; filename prefix = eGFR label.
Research date: 2026-10-23. All URLs were fetched or seen in search results during this session unless marked otherwise.

## Q1. Strategies for merging two codebases with overlapping functionality

### Takeaway
Use B as the host and bring A's engine in one module at a time. This is the strangler-fig approach: new code grows inside the stronger system and replaces old behaviour step by step. Inside B, put each ported capability behind a port/adapter boundary, using branch by abstraction: an abstraction layer first, then old and new suppliers swapped and compared behind it. Avoid a big-bang rewrite. B is already a single process and single repo, so keep it a modular monolith rather than splitting it into services.

### Cited Findings
- Fowler says replacing a legacy system all at once "go[es] down in flames most of the time": replacements take a long time, users want features now, and existing behaviour is hard to specify. Strangler fig instead grows small additions beside the legacy system and moves behaviour across piece by piece. — [Fowler, StranglerFigApplication (2024-08-22)](https://martinfowler.com/bliki/StranglerFigApplication.html)
- Strangler fig needs "seams" to split a system. It has four activities: define outcomes, decompose, deliver parts, and change the organisation. — [Fowler, StranglerFigApplication](https://martinfowler.com/bliki/StranglerFigApplication.html)
- Risks Fowler lists: much legacy behaviour is unwanted, so reproducing it wastes effort; transitional code is needed for old and new to coexist; and without cultural change the new system decays the same way. — [Fowler, StranglerFigApplication](https://martinfowler.com/bliki/StranglerFigApplication.html)
- Branch by Abstraction has five steps: create an abstraction over the current supplier, move clients onto it, build the new supplier behind it, switch over (feature flags can run both and compare behaviour), then delete the old supplier and optionally the abstraction. The system builds and runs correctly the whole time. — [Fowler, BranchByAbstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)
- Hexagonal (Ports & Adapters) architecture lets an application "equally be driven by users, programs, automated test or batch scripts". Business logic is regression-tested through a test-harness adapter, without a UI or live database. Swapping an adapter, for example the DB, does not change application logic. — [Cockburn, Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)

### Inferences
- **Recommended combination for this project:** B is the host (strangler fig, with B as the "new tree"). Port A's training engine into a `training` module of B behind ports such as `DatasetPort`, `PreprocessPort`, `SegmenterPort`, `ClassifierTrainerPort`, `ModelRegistryPort` and `JobRunnerPort`. A's code becomes the first adapter implementation. Because A runs headless behind ports, A-vs-B numerical comparisons (Q3) can run as scripted tests without the React UI.
- **Branch by abstraction fits B's broken models and mask functions directly.** Put the abstraction in front of B's mask/inference callers, plug A's UNet-512 path in as the new supplier, compare outputs, then delete B's broken suppliers. Do not reproduce their behaviour, which matches Fowler's point that "much legacy behaviour is unwanted".
- **Monorepo / modular monolith (single FastAPI app, single SQLite DB, package-per-module) vs microservices:** for 1–3 people on one Windows machine, separate services add process management, IPC and deployment cost with no scaling benefit. This is engineering judgement. I did not fetch a specific source on modular monoliths this session.
- **Small-team risk:** the transitional "both systems alive" period should be short. A can stay runnable read-only as the reference oracle until the Phase 3 equivalence tests pass, then be archived.

### Gaps
- No peer-reviewed or empirical comparison of merge strategies specifically for research ML platforms was found. The guidance is practitioner literature (Fowler, Cockburn).
- I did not fetch a source on "modular monolith" (for example Fowler's MonolithFirst or Kamil Grzybek's articles). That recommendation is uncited judgement.

## Q2. Module boundaries in research ML platforms; reference architectures

### Takeaway
Mature medical-imaging tooling, MONAI Bundle in particular, packages a model together with a machine-readable contract: input/output tensor format, spatial shape, dtype, value range, channel definitions and library versions. MLOps reference architectures separate data validation, pipeline orchestration, metadata/lineage and the model registry. A good boundary set for B is: `data` (import/dedup/patient mapping) → `preprocess` → `segmentation` → `features` → `training` → `evaluation` → `registry` → `inference` → `clinical` (exams, reports). Each boundary passes a versioned contract, not ad-hoc file paths.

### Cited Findings
- A MONAI Bundle is a directory with a required `LICENSE`, `configs/metadata.json` and `models/model.pt`, plus optional `models/model.ts` / `model.onnx` and `docs/README.md` (a human-readable description of usage and authors). — [MONAI Bundle Specification](https://monai.readthedocs.io/en/latest/mb_specification.html)
- `metadata.json` holds `version` (semver), `monai_version`, `pytorch_version`, `numpy_version`, `required_packages_version`, `task`, `description`, `authors` and an optional `changelog`. `network_data_format` describes each input/output tensor by `type`, `format`, `modality`, `num_channels`, `spatial_shape`, `dtype`, `value_range`, `is_patch_data` and `channel_def`. — [MONAI Bundle Specification](https://monai.readthedocs.io/en/latest/mb_specification.html)
- MONAI Label's bundle loader reads `network_data_format.inputs.<first>.spatial_shape` from metadata to configure inference, so the contract is consumed programmatically, not only documented. — [MONAI Label bundle infer source](https://docs.monai.io/projects/label/en/stable/_modules/monailabel/tasks/infer/bundle.html); [MONAI Bundle Properties](https://monai.readthedocs.io/en/stable/mb_properties.html)
- Hexagonal architecture's primary/driving adapters (GUI, test harness, batch driver) and secondary/driven adapters (DB, notifications) map naturally onto a React UI / CLI / test driver on one side and SQLite / filesystem / GPU on the other. — [Cockburn](https://alistair.cockburn.us/hexagonal-architecture/)

### Inferences
- Suggested B module map (keep technical names):
  - `data`: image import, SHA-256 dedup, patient mapping, label table. Labels must come from a metadata table, never from filenames (see Q6).
  - `preprocess`: JFIF conversion, fixed-geometry crop (resize 1600×1200 → crop 1024×1024 @ (235,90)) and marker removal, as a versioned `PreprocessSpec`.
  - `segmentation`: UNet with an explicit `input_spatial_shape` (512×512 for A's model).
  - `features`: Length_px, GLCM entropy, contrast ratio, with a `FeatureSpec` version.
  - `training`: A's engine (CORAL, K-fold, resume, queue).
  - `evaluation`: patient-level metrics and reports.
  - `registry`: manifest and model cards (Q4).
  - `inference`: refuses to run if the manifest contract mismatches the incoming data.
  - `clinical`: device receiving, exams, PDF reports. It depends only on `inference` and `registry`, never on `training`.
- B's existing "protected compute files" manifest can map one-to-one onto the `preprocess`, `segmentation`, `features` and `inference` modules. Any file change there triggers the golden regression suite from Q3.
- The new direction (Grade 0–3 cortex echogenicity, multi-image patient-level reports, video frame extraction, cyst/stone/hydronephrosis detection) adds new `task` entries and new modules (`video_ingest`, `detection`, `patient_aggregation`). It does not change the existing boundaries. Design `registry.task` as an enum from the start.

### Gaps
- Kaapana, NVIDIA Clara and OHIF architecture docs were not fetched (time budget; MONAI docs host had TLS errors on one domain). Their integration patterns (DICOM/DICOMweb, OHIF as viewer, a Kubernetes-based platform in Kaapana) are heavier than a single Windows machine needs. I can't cite specifics.
- Google's MLOps levels page redirected and was not read, so no citation for the MLOps level 0/1/2 framing.

## Q3. Numerical equivalence when porting training/inference code

### Takeaway
Bitwise equality is not guaranteed even with identical seeds, across PyTorch versions, platforms, or CPU vs GPU. Plan on:
- **Inference/preprocessing/features:** exact or tight-tolerance golden-output tests. These parts are deterministic and should match closely.
- **Training:** statistical equivalence (metrics within a tolerance band across seeds), not bitwise.

Run all of it on the same machine, same PyTorch 2.6 and same CUDA as A.

### Cited Findings
- "Completely reproducible results are not guaranteed across PyTorch releases, individual commits, or different platforms", and CPU and GPU runs may differ even with identical seeds. — [PyTorch 2.6 Reproducibility notes](https://docs.pytorch.org/docs/2.6/notes/randomness.html)
- `torch.manual_seed()` seeds the CPU and CUDA RNGs. Python `random.seed()` and `np.random.seed()` must also be set, and separately created NumPy Generators must be seeded on their own. — [PyTorch randomness notes](https://docs.pytorch.org/docs/2.6/notes/randomness.html)
- `torch.backends.cudnn.benchmark=True` can select different algorithms run to run. Setting it to `False` makes selection deterministic at a possible performance cost. `cudnn.deterministic=True` separately makes the convolution algorithm deterministic. — [PyTorch randomness notes](https://docs.pytorch.org/docs/2.6/notes/randomness.html)
- `torch.use_deterministic_algorithms(True)` uses deterministic implementations and raises a RuntimeError for ops without one (for example CUDA `index_add_`). On CUDA ≥10.2 it requires the `CUBLAS_WORKSPACE_CONFIG` env var. — [PyTorch randomness notes](https://docs.pytorch.org/docs/2.6/notes/randomness.html)
- DataLoader determinism needs `worker_init_fn=seed_worker`, which seeds NumPy and `random` from `torch.initial_seed() % 2**32`, plus a seeded `torch.Generator` passed as `generator=`. — [PyTorch randomness notes](https://docs.pytorch.org/docs/2.6/notes/randomness.html)
- Branch by abstraction allows running old and new suppliers side by side (via flags) to compare behaviour. — [Fowler, BranchByAbstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)

### Inferences
Proposed equivalence ladder (A = oracle, B-ported = candidate; same machine and same env lockfile):
1. **Preprocessing:** for a fixed sample of about 50 images, the output PNG/arrays must be byte-identical, or max abs pixel diff = 0 for uint8. Store SHA-256 of the outputs as golden files.
2. **Masks (UNet 512) inference:** the same weights on the same preprocessed input should give logits within a tight float32 tolerance (for example `torch.testing.assert_close` defaults, or atol around 1e-5). Binary masks should have Dice ≥ 0.999 / exact pixel agreement, with the deterministic flags on and `model.eval()`.
3. **Features:** Length_px exact; GLCM entropy and contrast ratio to relative tol about 1e-6. Watch for differences in skimage/OpenCV versions.
4. **Classifier inference:** with the same checkpoint, predicted class identical on 100% of the golden set, and probabilities within about 1e-5.
5. **Training:** with deterministic flags and the same seed and folds, loss curves should match closely over the first N steps. Over a full run, require per-fold metrics (QWK / MAE / accuracy) within a pre-registered band, for example within the A run-to-run spread over 3 seeds. Bitwise identity is not required (per the PyTorch docs above).
6. **Resume-from-checkpoint:** train k epochs, stop, resume, and compare against an uninterrupted run under the same tolerance. This requires saving optimizer, scheduler, RNG states (torch / cuda / numpy / python) and the sampler/generator state.

Wire these into B's protected-compute manifest as a CI-like `pytest -m golden` command that must pass before any protected file change is accepted.

### Gaps
- Exact `torch.testing.assert_close` default rtol/atol per dtype: the doc page redirected (to 2.14) and was not read. Look this up before fixing tolerances.
- No literature found that quantifies typical GPU nondeterminism magnitude for ResNet18 training. Measure it empirically with A run-to-run variance.
- Golden-master / characterization-testing literature (for example Feathers) was not fetched.

## Q4. Model registry / manifest design to prevent contract mismatches (UNet 512 vs 1024)

### Takeaway
Every model version must carry a machine-checked I/O and preprocessing contract, MONAI-Bundle style: spatial_shape, dtype, value_range, channel_def, preprocessing spec version, library versions. Add lineage (training run, data split, data hash) and a model card. Loaders and inference must refuse a mismatch rather than silently resize. MLflow concepts (registered model, versions, aliases, tags, lineage) are a useful vocabulary, but a JSON manifest in SQLite plus files is enough locally.

### Cited Findings
- MLflow Model Registry:
  - Registered models hold auto-incrementing versions.
  - Aliases (for example `champion`) are mutable pointers to a version, so consumers use `models:/MyModel@champion` and are unaffected by re-pointing.
  - Tags (key-value) record status such as validation state.
  - Each version links to the run that produced it, for lineage and reproducibility.
  - (Unity Catalog) requires a model signature, and `mlflow.models.set_signature()` can add one.
  
  — [MLflow Model Registry docs](https://mlflow.org/docs/latest/ml/model-registry/)
- MONAI Bundle `network_data_format` (`spatial_shape`, `dtype`, `value_range`, `num_channels`, `channel_def`, `is_patch_data`) plus semver `version`, `changelog` and pinned library versions is a concrete, field-level precedent for a model contract. — [MONAI Bundle Specification](https://monai.readthedocs.io/en/latest/mb_specification.html)
- Model Cards (Mitchell et al., FAT* 2019) document intended use context, evaluation procedure, and performance disaggregated across groups. — [arXiv 1810.03993](https://arxiv.org/abs/1810.03993)
- Kapoor & Narayanan propose "model info sheets" to document and mitigate leakage. — [Patterns 2023, PMC10499856](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856)

### Inferences
Suggested extension of A's `model_metadata.json` into a B registry record:
- `model_id`, `task` (`egfr_5class` | `echogenicity_grade_0_3` | `kidney_seg` | `lesion_det`…), `version` (semver), `alias` (`candidate` / `champion` / `archived`), `status_tags`.
- `input_contract`: `spatial_shape` [512,512] or [224,224], `num_channels`, `dtype`, `value_range`, `normalization` (mean/std), `color_space`.
- `preprocess_spec_id` + hash. This is the fixed-geometry crop version, so a model trained on crop v1 can't be served with crop v2.
- `upstream_models`: for example a classifier depends on `kidney_seg@1.0.0` with a 512 contract. Resolving this dependency graph at load time is the direct guard against the UNet 512 vs 1024 mismatch.
- `output_contract`: classes, CORAL thresholds, `channel_def`.
- `training_lineage`: run_id, split_id, split strategy (`patient_stratified_group_kfold`), data manifest hash, seed, git commit/file hashes of protected files, torch/cuda/numpy versions.
- `metrics`: patient-level, per fold, with CIs.
- `model_card.md`: intended use (research only, not diagnostic), limitations, subgroup performance.

Guard rule: `inference.load()` validates the manifest contract against the requested pipeline and raises on mismatch. A registry test should iterate all `champion` models and run a contract check plus a smoke inference.

The full MLflow server is optional. MLflow can run with a local file/SQLite backend, but that was not confirmed in the fetched page (see Gaps). A hand-rolled SQLite table is probably simpler for B.

### Gaps
- The fetched MLflow page did not cover the local file-based backend or input examples. Running MLflow fully offline on Windows is unverified in this research.
- No consensus standard exists for "preprocessing contract" versioning outside MONAI-style bundles. This is a design choice.

## Q5. SQLite schema migration/merge (SQLAlchemy/Alembic) and single-machine job queue + SSE

### Takeaway
Use Alembic with `render_as_batch=True` (batch "move-and-copy" mode) for SQLite, with explicit constraint naming conventions. Import A's data into B's schema with a one-off, idempotent ETL script, keyed on SHA-256 image hashes, not by merging DB files. For jobs:
- FastAPI `BackgroundTasks` is for small in-process tasks only.
- Celery does not officially support Windows.

On one Windows box, the pragmatic options are to keep A's thread/process queue, persisting job state in SQLite, or use Huey with its SQLite storage. GPU training should run in a separate process from the API.

### Cited Findings
- SQLite has very limited ALTER support. Alembic batch mode reflects the table, creates a new one with the changes, copies rows, drops the old table and renames. A plain `add_column` can still be a normal ALTER. Set `render_as_batch=True` in `env.py` `context.configure()` for autogenerate. This is safe because batch behaviour only applies to SQLite by default. — [Alembic batch docs](https://alembic.sqlalchemy.org/en/latest/batch.html)
- Constraint caveats in batch mode:
  - Unnamed FKs need a `naming_convention` to be dropped.
  - Unnamed CHECK constraints are dropped on recreate (Alembic ≥1.20 warns).
  - Batch fails if other tables reference the table being recreated; `PRAGMA foreign_keys` must be off during the migration.
  
  — [Alembic batch docs](https://alembic.sqlalchemy.org/en/latest/batch.html)
- FastAPI `BackgroundTasks` runs after the response, in the same process. The docs recommend bigger tools like Celery for heavy computation that doesn't need to share memory. — [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- Celery FAQ: "Since Celery 4.x, Windows is no longer supported due to lack of resources." It "may still work". — [Celery FAQ](https://docs.celeryq.dev/en/stable/faq.html)
- Huey is a lightweight Python task queue with storage backends Redis, SQLite, Postgres, file system and in-memory. It has process/thread/greenlet worker types, scheduling, retries, priority, locking, timeouts and result storage. — [Huey docs](https://huey.readthedocs.io/en/latest/)

### Inferences
- **Migration plan:**
  1. Freeze B's schema.
  2. `alembic stamp` the current B DB as the baseline.
  3. Add new tables (`training_runs`, `checkpoints`, `model_registry`, `splits`, `split_members`, `job_queue`) via batch-mode migrations.
  4. Write `import_from_A.py`. It reads A's SQLite read-only, maps images by SHA-256 to B's image records (skip duplicates), maps to B patient IDs, and copies run history as `legacy_A` provenance. It must be idempotent (re-runnable), with a dry-run report of counts.
  
  Always back up the `.db` file before migration (SQLite is a single file). Verify with row counts and hash-set equality.
- **Job runner:** Redis and RabbitMQ are extra Windows services, and Celery is unsupported on Windows. That argues against Celery, and against RQ, which also depends on Redis and fork semantics (RQ not fetched; flagged). Huey+SQLite or A's existing queue are the realistic options. Run GPU training in a `multiprocessing`/subprocess worker so a CUDA crash or OOM can't kill the API, and allow one GPU job at a time.
- **SSE:** keep A's SSE. The worker writes progress to SQLite or a progress table/file, and the FastAPI SSE endpoint polls and streams it. This decouples SSE from the worker process and survives API restarts.
- **No consensus:** whether to adopt Huey or keep A's custom queue. Huey adds retries and scheduling. A's queue already works and has stop/resume semantics tied to checkpoints. Recommendation: keep A's queue behind a `JobRunnerPort`, so it can be swapped later.

### Gaps
- RQ / arq / Dramatiq Windows support was not verified this session. (RQ is generally understood to rely on `fork()`, but that is unconfirmed here.)
- No authoritative source fetched on FastAPI SSE patterns (sse-starlette, or `StreamingResponse` with `text/event-stream`).

## Q6. Guardrails against data leakage (patient-level splits, filename label leakage)

### Takeaway
Leakage from splitting one patient's images across train and test is a well-documented cause of inflated results in medical-imaging ML. Use `StratifiedGroupKFold(groups=patient_id)` for patient-level CV, hold out a patient-level test set before any tuning, never derive labels or features from filenames, and add automated leakage assertions. The old image-level A results (and B's 59 classifiers) should be treated as non-comparable and re-benchmarked.

### Cited Findings
- Varoquaux & Cheplygina (npj Digital Medicine, 2022) on leakage and evaluation:
  - Data leakage occurs when "repeated measures of an individual are split across train and test set", so the model learns to recognise the individual.
  - Feature selection on the full dataset before CV inflates results.
  - Researchers tuning against test folds overfit.
  
  They recommend separating test data from the start, before any data transformation; documenting hyper-parameter selection without test data; test sets of several hundred+ samples with confidence intervals; and checking for shortcuts and confounds (for example chest drains in pneumothorax images, skin markings). — [PMC9005663](https://pmc.ncbi.nlm.nih.gov/articles/PMC9005663)
- Kapoor & Narayanan (Patterns 2023) found leakage in 17 fields affecting 294 papers. They give a taxonomy of 8 leakage types and propose model info sheets. The project page has since been updated (May 2024) to a larger count. — [PMC10499856](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856); [project page](https://reproducible.cs.princeton.edu/)
- Kidney-stone CT preprint: patient-wise split gave AUC 0.946 / accuracy 0.905, vs about 0.999 AUC / 0.991 accuracy with image-level splits that had augmented copies in both sets. Not peer-reviewed. — [Research Square preprint](https://www.researchsquare.com/article/rs-10604877/latest)
- Pathology: patient-wise vs random splits quantified across backbones. — [arXiv 1909.06539 "AI slipping on tiles"](https://arxiv.org/pdf/1909.06539)
- Brain MRI: repeated scans per subject leak through CV, and Grad-CAM showed subject-identification features. Recommends subject-wise splits. — [arXiv 2309.00350](https://arxiv.org/abs/2309.00350v1)
- scikit-learn `StratifiedGroupKFold`:
  - Returns folds with non-overlapping groups (each group appears in the test set exactly once) while trying to preserve class proportions.
  - Stratification is best-effort and degrades toward `GroupKFold` when a few groups are large.
  - `shuffle=False` is deterministic; `random_state` matters only with `shuffle=True`, and shuffling is per-class, not global.
  - Requires n_groups ≥ n_splits.
  
  — [scikit-learn StratifiedGroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)

### Inferences
- **Split guardrails** (implement as code-level assertions in `training`):
  1. `splits` table stores `patient_id → fold`, not `image_id → fold`. Assert `set(train_patients) ∩ set(val_patients) = ∅` before every run.
  2. A held-out patient-level test set (for example about 15–20% of ~181 patients, stratified by patient-level eGFR class) is frozen once, hashed, and never used for model selection.
  3. Stratify on the patient-level label. Images of one patient normally share one eGFR, so verify that and flag any patient with conflicting labels.
  4. With ~181 patients and 5 classes, some folds may have very few patients in rare classes. Report per-fold class counts and CIs. Small test sets are a Varoquaux & Cheplygina concern.
- **Filename label-leakage guardrails:**
  - On import, rename stored files to content hash or opaque UUID and keep the original filename only in an audit column.
  - Labels come only from a metadata table.
  - Add a test that fails if any `Dataset.__getitem__` path or feature function reads `original_filename`.
  - Optionally add a "shortcut probe": train a trivial model on metadata such as file size, EXIF and device fields. Near-chance accuracy is expected.
- **Other leakage specific to this pipeline:**
  - SHA-256 dedup catches only exact duplicates. Near-duplicates (re-exports, different JFIF compression of the same frame, consecutive video frames) need perceptual hashing, and must at least stay within the same patient group. This is critical for the future video frame extraction work.
  - Colored-marker removal: markers placed by sonographers could act like the dermatology "skin markings" shortcut. Verify that removal is complete.
  - Normalization statistics and feature scaling must be fit on training folds only.
- **Reporting:** for the new patient-level reports (5–8 images per patient), the evaluation unit should be the patient. Aggregate image predictions inside the patient and compute metrics per patient.

### Gaps
- No peer-reviewed study specific to kidney ultrasound leakage was found. The kidney-stone CT numbers come from a non-peer-reviewed preprint, so treat the magnitude as illustrative.
- The full 8-category Kapoor & Narayanan taxonomy text was not fetched.

## Q7. Recommended phased merge order with completion criteria

### Takeaway
The order follows the strangler-fig and branch-by-abstraction logic above:
1. Freeze and baseline.
2. Data and leakage guardrails.
3. Contracts and registry.
4. Port A's deterministic pieces (preprocess → UNet512 → features) with golden tests.
5. Port the training engine and queue.
6. Evaluation re-baseline on patient splits.
7. Wire the clinician side to the registry.
8. Retire A and B's broken models.
9. Only then the new tasks.

Every phase has a measurable exit gate.

### Cited Findings
- Incremental replacement with seams, transitional coexistence and removal of the old supplier at the end — [Fowler Strangler Fig](https://martinfowler.com/bliki/StranglerFigApplication.html); [Fowler Branch by Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)
- Determinism controls and the limits of reproducibility — [PyTorch 2.6 randomness](https://docs.pytorch.org/docs/2.6/notes/randomness.html)
- Test data separated before any transformation; patient-level splits — [Varoquaux & Cheplygina 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9005663); [sklearn StratifiedGroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)
- Contract metadata fields — [MONAI Bundle spec](https://monai.readthedocs.io/en/latest/mb_specification.html)
- SQLite migrations — [Alembic batch](https://alembic.sqlalchemy.org/en/latest/batch.html)

### Inferences
Proposed plan. This is a synthesis, so adjust durations to the team.

**Phase 0: Freeze and baseline (A = oracle)**
- Snapshot both repos and DBs (git tag plus `.db` copies). Pin the environment (torch 2.6, CUDA, numpy, opencv, skimage) in a lockfile, identical for A and B.
- Generate A golden outputs for about 50 images: preprocessed images, masks, features and classifier probabilities from one A checkpoint. Record A run-to-run metric variance by repeating 3 seeds of one training config.
- *Exit:* golden files plus hashes committed; variance table recorded; `alembic stamp` baseline on B's DB.

**Phase 1: Data layer and leakage guardrails**
- Import A's images and metadata into B via an idempotent ETL keyed on SHA-256. Map all images to patients. Labels come from the metadata table, and files are stored under opaque names.
- Create a `splits` table: a patient-level frozen test set plus `StratifiedGroupKFold` folds.
- *Exit:* 975 images accounted for (imported + dedup-skipped = total); 0 images without patient_id; patient overlap assertion = ∅ for every split; the filename-access test passes; per-fold class counts reported.

**Phase 2: Contracts and registry**
- Implement the registry table plus a manifest schema (input_contract, preprocess_spec_id, upstream_models, lineage, model card). Mark B's 60 imported models as `archived/broken`. Do not delete them yet; B has trash bins.
- *Exit:* `inference.load()` raises on any contract mismatch, with a unit test feeding a 1024-contract UNet into a 512 pipeline; registry lists 0 `champion` models until Phase 4.

**Phase 3: Port deterministic compute (preprocess → UNet512 masks → features) behind ports**
- Branch by abstraction: B's mask/inference callers go through `SegmenterPort`. Plug in A's adapter and delete B's broken mask functions. Add the files to B's protected-compute manifest.
- *Exit:* golden tests pass at the Q3 tolerances: preprocessing byte-identical, mask agreement ≥ 0.999 Dice, features within tolerance, classifier probabilities within about 1e-5 with identical argmax.

**Phase 4: Port training engine, queue and SSE**
- Bring in CORAL, the four backbones, K-fold, checkpoint resume (with full RNG/optimizer state), the job runner in a separate process behind `JobRunnerPort`, and SSE progress.
- *Exit:*
  - The same config, seed and folds (using A's old image-level folds only for this parity test) reproduce A's per-fold metrics within the Phase 0 variance band.
  - Resume test: stop at epoch k and resume, versus an uninterrupted run, within the same band.
  - Kill-the-worker test: API stays up and the job is marked failed or resumable.
  - Concurrency test: a second GPU job queues rather than running in parallel.

**Phase 5: Re-baseline on patient-level splits (evaluation module)**
- Retrain eGFR models on patient-level folds. Report patient-level metrics with CIs, and show the old image-level numbers side by side as "leaky, for reference only". Promote the best to `champion` with a model card.
- *Exit:* evaluation report generated from the registry; every champion has a complete manifest and lineage (split hash, data hash, protected-file hashes).

**Phase 6: Clinician area integration**
- Exams → AI analysis uses only `champion` aliases through `inference`. PDF reports cite model_id and version and carry a research-use disclaimer.
- *Exit:* end-to-end test from a device-received image to a PDF containing the model version; the clinical module has no import of `training`, checked by an import-linter rule.

**Phase 7: Retire A and clean up**
- Archive the A repo (read-only). Permanently remove B's broken models only after explicit human sign-off. Remove transitional abstractions that are no longer needed.
- *Exit:* A not required for any test except archived golden files; protected-compute regression suite green.

**Phase 8: New direction (after the merge stabilises)**
- Echogenicity Grade 0–3 (kidney vs liver/spleen ROI), multi-image patient aggregation, video frame extraction (with near-duplicate/perceptual-hash grouping per patient), cyst/stone/hydronephrosis detection and report drafts. Each is a new `task` in the registry with its own contract and patient-level evaluation.

Areas without consensus or evidence:
- Exact tolerance thresholds. Set them empirically from Phase 0 variance.
- Huey vs a custom queue.
- MLflow vs a hand-rolled registry.
- Whether to keep A's old image-level folds at all (only useful for the Phase 4 parity check).

### Gaps
- No published case study found of merging two research ML web platforms. The plan is synthesised from general software-migration practice and the ML reproducibility and leakage literature.
- Clinical/regulatory guidance (for example FDA/TFDA software validation for clinician-facing AI reports) was out of scope and not researched.
