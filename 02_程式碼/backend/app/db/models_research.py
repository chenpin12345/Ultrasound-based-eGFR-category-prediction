from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import ResearchBase


class Batch(ResearchBase):
    """匯入批次。B0000 是 IMG_original（只登記、不複製）。"""

    __tablename__ = 'batches'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(16))  # original / inbox / clinical
    source_label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))  # running / completed / failed
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    counts_json: Mapped[str] = mapped_column(Text, default='{}')
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class SourceMap(ResearchBase):
    """影像 ID ↔ 原始檔案。原始檔名可能含有答案（eGFR），只有 data.importer 與 data.patients 可以讀。"""

    __tablename__ = 'source_map'
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id', ondelete='CASCADE'), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'))
    original_relpath: Mapped[str] = mapped_column(Text)


class LayoutTemplate(ResearchBase):
    __tablename__ = 'layout_templates'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    machine: Mapped[str] = mapped_column(String(60))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    regions_json: Mapped[str] = mapped_column(Text)  # 要遮蓋的區域（百分比）
    readers_json: Mapped[str] = mapped_column(Text)  # OCR 與深度尺讀取位置（百分比）
    updated_at: Mapped[str] = mapped_column(String(32))
    updated_by: Mapped[str] = mapped_column(String(80), default='')

    __table_args__ = (UniqueConstraint('width', 'height', name='uq_template_size'),)


class Patient(ResearchBase):
    __tablename__ = 'patients'
    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # P-0001
    source_ref: Mapped[str] = mapped_column(String(80), default='')
    sex: Mapped[str | None] = mapped_column(String(4), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_diabetes: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    egfr: Mapped[float | None] = mapped_column(Float, nullable=True)
    egfr_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    has_fatty_liver: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # r0002；脂肪肝會讓肝變亮，影響皮質／肝比值
    created_at: Mapped[str] = mapped_column(String(32))


class Image(ResearchBase):
    __tablename__ = 'images'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), index=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    phash: Mapped[str] = mapped_column(String(16), default='')
    patient_id: Mapped[str | None] = mapped_column(ForeignKey('patients.id'), nullable=True, index=True)
    machine: Mapped[str] = mapped_column(String(60), default='')
    template_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)  # right / left
    side_source: Mapped[str] = mapped_column(String(16), default='')  # ocr / manual
    view: Mapped[str | None] = mapped_column(String(16), nullable=True)  # long / short / oblique
    pixel_spacing_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    spacing_check: Mapped[str] = mapped_column(String(16), default='')  # ok / mismatch / missing
    sonographer_length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    sonographer_width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_sex: Mapped[str | None] = mapped_column(String(4), nullable=True)
    scan_params_json: Mapped[str] = mapped_column(Text, default='{}')
    caliper_pixels: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), index=True)  # usable / pending_review / excluded
    review_reasons_json: Mapped[str] = mapped_column(Text, default='[]')
    exclude_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deid_check: Mapped[str] = mapped_column(String(16), default='unchecked')  # pass / residual / unchecked
    created_at: Mapped[str] = mapped_column(String(32))


class MaskAnnotation(ResearchBase):
    __tablename__ = 'mask_annotations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id', ondelete='CASCADE'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    annotator: Mapped[str] = mapped_column(String(80))
    relpath: Mapped[str] = mapped_column(Text)
    shapes_json: Mapped[str] = mapped_column(Text, default='[]')
    flags_json: Mapped[str] = mapped_column(Text, default='{}')
    status: Mapped[str] = mapped_column(String(16), default='done')  # draft / done / reviewed
    reviewer: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # r0002：遮罩來源與人工確認。測試集只接受 manual 或經人工確認（verified_by 有值）的遮罩
    source: Mapped[str] = mapped_column(String(16), default='manual')  # manual / legacy / medsam / rule / model
    verified_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verified_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (UniqueConstraint('image_id', 'version', name='uq_mask_version'),)


class GradeLabel(ResearchBase):
    """回音分級。每位醫師對每位病人的每一側腎各一筆；保留所有醫師的原始分級。"""

    __tablename__ = 'grade_labels'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    side: Mapped[str] = mapped_column(String(8))
    image_id: Mapped[str | None] = mapped_column(ForeignKey('images.id'), nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = 無法判斷
    unsure_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rater: Mapped[str] = mapped_column(String(80))
    is_consensus: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint('patient_id', 'side', 'rater', 'is_consensus', name='uq_grade_rater'),)


class ImageGrade(ResearchBase):
    """每張影像的回音分級（決策 D49），來自醫師圈選網站；每位判讀者每張影像一筆。"""

    __tablename__ = 'image_grades'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id'), index=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = 無法判斷
    unsure_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rater: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint('image_id', 'rater', name='uq_image_grade_rater'),)


class ImageLabel(ResearchBase):
    """側別與切面標註（影像品質標註已在 M2.5 移除，決策 D25）。"""

    __tablename__ = 'image_labels'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # side
    value_json: Mapped[str] = mapped_column(Text)
    annotator: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint('image_id', 'kind', 'annotator', name='uq_image_label'),)


class AgreementReport(ResearchBase):
    __tablename__ = 'agreement_reports'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # grade / mask
    raters_json: Mapped[str] = mapped_column(Text)
    metrics_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))


class ClinicalFeedback(ResearchBase):
    __tablename__ = 'clinical_feedback'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[str] = mapped_column(String(32))
    item: Mapped[str] = mapped_column(String(80))
    ai_value: Mapped[str] = mapped_column(String(120))
    doctor_value: Mapped[str] = mapped_column(String(120))
    by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32), default='')  # M3：exclude／length／grade／side（r0005）
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    image_id: Mapped[str | None] = mapped_column(String(24), nullable=True)  # 醫師端影像 ID（CI-）
    reason: Mapped[str] = mapped_column(String(200), default='')
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class DatasetVersion(ResearchBase):
    __tablename__ = 'dataset_versions'
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    note: Mapped[str] = mapped_column(String(200), default='')
    image_count: Mapped[int] = mapped_column(Integer)
    patient_count: Mapped[int] = mapped_column(Integer)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Split(ResearchBase):
    __tablename__ = 'splits'
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    method: Mapped[str] = mapped_column(String(40))
    seed: Mapped[int] = mapped_column(Integer)
    folds: Mapped[int] = mapped_column(Integer)
    test_ratio: Mapped[float] = mapped_column(Float)
    stratify_by: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(200), default='')
    test_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    test_locks_json: Mapped[str] = mapped_column(Text, default='{}')  # 依任務的測試鎖：{"segmentation": {...}, "egfr": {...}}（M2.5）
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class SplitEntry(ResearchBase):
    __tablename__ = 'split_entries'
    split_id: Mapped[str] = mapped_column(ForeignKey('splits.id', ondelete='CASCADE'), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), primary_key=True)
    group: Mapped[str] = mapped_column(String(16))  # test / fold-1..k / prospective

    __table_args__ = (Index('ix_split_entries_group', 'split_id', 'group'),)


# ---- M2：訓練、模型庫、評估、特徵（r0002）----


class FeatureSet(ResearchBase):
    """特徵集：記錄用哪個分割來源、哪個切分、是否交叉擬合，檔案在 04_模型產出/特徵/{id}/。"""

    __tablename__ = 'feature_sets'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # FS-20261024-001
    spec_json: Mapped[str] = mapped_column(Text)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    relpath: Mapped[str] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default='running')
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 跟著分割訓練移入回收桶（r0007）


class Experiment(ResearchBase):
    """實驗：一組可比較的訓練（例如消融實驗 A0–A5、隨機初始化 vs ImageNet）。"""

    __tablename__ = 'experiments'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # EXP-20261024-001
    name: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(String(40), default='custom')
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    note: Mapped[str] = mapped_column(String(400), default='')
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class TrainingRun(ResearchBase):
    __tablename__ = 'training_runs'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # RUN-20261024-001
    task: Mapped[str] = mapped_column(String(24))  # segmentation / grade / egfr
    name: Mapped[str] = mapped_column(String(120), default='')
    experiment_id: Mapped[str | None] = mapped_column(ForeignKey('experiments.id'), nullable=True, index=True)
    split_id: Mapped[str] = mapped_column(ForeignKey('splits.id'))
    dataset_version_id: Mapped[str | None] = mapped_column(ForeignKey('dataset_versions.id'), nullable=True)
    config_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default='queued')
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, default='{}')  # 各折最佳 epoch 的指標與平均
    relpath: Mapped[str] = mapped_column(Text)  # 04_模型/01_訓練紀錄/{id}
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ModelEntry(ResearchBase):
    """模型庫：註冊後檔案不可修改；階段可升級（研究 → 候選 → 臨床上線 → 退役）。"""

    __tablename__ = 'models'
    id: Mapped[str] = mapped_column(String(120), primary_key=True)  # egfr/hybrid@1.0.0
    task: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(24))
    stage: Mapped[str] = mapped_column(String(16), default='research')  # research / candidate / clinical / retired
    run_id: Mapped[str | None] = mapped_column(ForeignKey('training_runs.id'), nullable=True)
    relpath: Mapped[str] = mapped_column(Text)
    manifest_json: Mapped[str] = mapped_column(Text)
    stage_history_json: Mapped[str] = mapped_column(Text, default='[]')
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 和來源訓練一起移入回收桶（M2.5 #109）

    __table_args__ = (UniqueConstraint('task', 'name', 'version', name='uq_model_version'),)


class Evaluation(ResearchBase):
    __tablename__ = 'evaluations'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # EVAL-20261024-001
    model_id: Mapped[str | None] = mapped_column(ForeignKey('models.id'), nullable=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey('training_runs.id'), nullable=True)
    target: Mapped[str] = mapped_column(String(16))  # oof（交叉驗證）／ test（固定測試集，只能一次）
    metrics_json: Mapped[str] = mapped_column(Text)
    relpath: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))


class CirclingBatch(ResearchBase):
    """醫師圈選批次（M2.5，決策 D16、D20）：一次交給醫師的一組影像。"""

    __tablename__ = 'circling_batches'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # CB-20261102-001
    kind: Mapped[str] = mapped_column(String(16))  # test（測試集每側 1 張）／ train（訓練影像）
    split_id: Mapped[str] = mapped_column(String(16))
    round: Mapped[int] = mapped_column(Integer, default=0)  # 訓練批次的第幾批；測試集為 0
    note: Mapped[str] = mapped_column(String(200), default='')
    exported_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    export_relpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    include_original: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))


class CirclingItem(ResearchBase):
    """批次中的一張影像與它的圈選進度。"""

    __tablename__ = 'circling_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('circling_batches.id', ondelete='CASCADE'), index=True)
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id'), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # 清單.csv 的序號
    status: Mapped[str] = mapped_column(String(16), default='pending')  # pending／exported／parsed／imported／needs_redraw
    circler: Mapped[str] = mapped_column(String(40), default='')  # 圈選者代號（選填）
    return_kind: Mapped[str] = mapped_column(String(16), default='')  # color／label
    parse_json: Mapped[str] = mapped_column(Text, default='{}')  # 參考影像、各構造面積、警告、錯誤
    structures_json: Mapped[str] = mapped_column(Text, default='{}')  # 各構造狀態：drawn／absent／unlabeled
    parsed_relpath: Mapped[str | None] = mapped_column(Text, nullable=True)  # 轉出的標籤 PNG（不含個資）
    mask_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(200), default='')
    updated_at: Mapped[str] = mapped_column(String(32), default='')

    __table_args__ = (UniqueConstraint('batch_id', 'image_id', name='uq_circling_item'),)


class MaskSet(ResearchBase):
    """交叉預測遮罩組（M2.5，決策 D26）：分割訓練替資料集版本的每張影像預測的遮罩。"""

    __tablename__ = 'mask_sets'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # MS-20261110-001
    seg_run_id: Mapped[str] = mapped_column(ForeignKey('training_runs.id'))
    split_id: Mapped[str] = mapped_column(String(16))
    dataset_version_id: Mapped[str] = mapped_column(String(16))
    spec_json: Mapped[str] = mapped_column(Text, default='{}')
    rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default='queued')  # queued／running／completed／failed
    relpath: Mapped[str] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
