"""clinical.sqlite3：醫師端（M3，實作企劃 §5、決策 D38–D45）。

- 雙機展示模式只存病例代碼；超音波模式另存姓名、病歷號（受限欄位，只在醫師端頁面回傳，D39）。
- 年齡、性別、糖尿病記在每次檢查上（會隨時間改變）。
- 分析紀錄與報告版本建立後不可修改（D45 的 B8）；報告 PDF 只保留最新一份（D42）。
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import ClinicalBase


class ClinicalPatient(ClinicalBase):
    __tablename__ = 'clinical_patients'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # CP-{nnnn}
    case_code: Mapped[str] = mapped_column(String(40), unique=True)  # 病例代碼（雙機展示）或系統編號
    mode: Mapped[str] = mapped_column(String(16), default='demo')  # demo（雙機展示）／device（超音波機器）
    name: Mapped[str | None] = mapped_column(String(60), nullable=True)  # 受限：只有超音波模式
    mrn: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 受限：病歷號，只有超音波模式
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ClinicalExam(ClinicalBase):
    __tablename__ = 'clinical_exams'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # EX-{YYYYMMDD}-{nnn}
    patient_id: Mapped[str] = mapped_column(ForeignKey('clinical_patients.id'), index=True)
    mode: Mapped[str] = mapped_column(String(16), default='demo')
    source: Mapped[str] = mapped_column(String(16), default='upload')  # upload／demo_pack／device
    upload_batch_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    title: Mapped[str] = mapped_column(String(80), default='腎臟超音波')
    # receiving、analyzing、needs_data、layout_mismatch、ready、partial、failed、signed（報告簽核後）
    status: Mapped[str] = mapped_column(String(24), default='receiving')
    age: Mapped[float | None] = mapped_column(Float, nullable=True)  # 當次檢查的年齡
    sex: Mapped[str | None] = mapped_column(String(1), nullable=True)  # M／F
    diabetes: Mapped[str] = mapped_column(String(8), default='unknown')  # yes／no／unknown（不明不當成無）
    clinical_source: Mapped[str] = mapped_column(String(16), default='')  # upload／demo_list／manual
    latest_analysis_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    overrides_json: Mapped[str] = mapped_column(Text, default='{}')  # 醫師修改：{right|left: {length_mm, grade}}（c0003）
    relpath: Mapped[str] = mapped_column(Text, default='')  # 05_醫師端/02_影像/{檢查}
    received_at: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ClinicalImage(ClinicalBase):
    __tablename__ = 'clinical_images'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # CI-{16 位十六進位}
    exam_id: Mapped[str] = mapped_column(ForeignKey('clinical_exams.id', ondelete='CASCADE'), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    template_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)  # right／left；None＝未指定側別
    side_source: Mapped[str] = mapped_column(String(16), default='')  # bodymark／ocr／demo_list／manual
    pixel_spacing_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    spacing_source: Mapped[str] = mapped_column(String(16), default='')  # ruler／demo_list／none
    status: Mapped[str] = mapped_column(String(24), default='ok')  # ok／layout_mismatch／residual／excluded
    exclude_reason: Mapped[str] = mapped_column(String(120), default='')
    deid_json: Mapped[str] = mapped_column(Text, default='{}')  # 去識別化的缺項與原因（不含個資）
    raw_relpath: Mapped[str] = mapped_column(Text, default='')  # 受限區 01_原始
    relpath: Mapped[str] = mapped_column(Text, default='')  # 去識別化影像
    created_at: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint('exam_id', 'sha256', name='uq_clinical_image_sha'),)  # 同一筆檢查內重複的略過


class ClinicalAnalysis(ClinicalBase):
    """一次分析的不可修改紀錄（B8）：用了哪些模型、輸入、各步驟結果。重新分析是新增一筆。"""

    __tablename__ = 'clinical_analyses'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # AN-{YYYYMMDD}-{nnn}
    exam_id: Mapped[str] = mapped_column(ForeignKey('clinical_exams.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(16), default='queued')  # queued／running／completed／partial／failed
    models_json: Mapped[str] = mapped_column(Text, default='{}')  # 每區：模型 ID、階段、合約版本、雜湊
    inputs_json: Mapped[str] = mapped_column(Text, default='{}')  # 臨床資料、像素間距來源
    steps_json: Mapped[str] = mapped_column(Text, default='{}')  # 各步驟：狀態、訊息、缺什麼
    results_json: Mapped[str] = mapped_column(Text, default='{}')
    candidate: Mapped[bool] = mapped_column(Boolean, default=False)  # 有結果來自候選模型（D40）
    device: Mapped[str] = mapped_column(String(16), default='')
    retry_of: Mapped[str | None] = mapped_column(String(24), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ClinicalEdit(ClinicalBase):
    """工作區的修改紀錄（B6）：誰、何時、改前、改後。"""

    __tablename__ = 'clinical_edits'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey('clinical_exams.id', ondelete='CASCADE'), index=True)
    image_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))  # exclude／include／length／grade／side／clinical／reanalyze
    before_json: Mapped[str] = mapped_column(Text, default='null')
    after_json: Mapped[str] = mapped_column(Text, default='null')
    reason: Mapped[str] = mapped_column(String(200), default='')
    actor: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))


class ClinicalReport(ClinicalBase):
    __tablename__ = 'clinical_reports'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # RP-{YYYYMMDD}-{nnn}
    exam_id: Mapped[str] = mapped_column(ForeignKey('clinical_exams.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(16), default='draft')  # draft／pending／signed／void
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    analysis_id: Mapped[str | None] = mapped_column(String(24), nullable=True)  # 報告固定引用的那一次分析
    signed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    signed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    void_reason: Mapped[str] = mapped_column(String(200), default='')
    pdf_relpath: Mapped[str] = mapped_column(Text, default='')  # 只保留最新一份（D42）
    pdf_sha256: Mapped[str] = mapped_column(String(64), default='')
    pdf_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    trashed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ClinicalReportVersion(ClinicalBase):
    """每次儲存一個不可修改的版本；簽核、作廢時凍結內容（B8）。"""

    __tablename__ = 'clinical_report_versions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey('clinical_reports.id', ondelete='CASCADE'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    payload_json: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    acknowledged_json: Mapped[str] = mapped_column(Text, default='[]')  # 簽核前檢查清單中勾選「已知悉」的項目（B9）
    actor: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint('report_id', 'version', name='uq_report_version'),)


class ReceiverSession(ClinicalBase):
    """雙機展示的接收（D38）：一次「開始接收」到「停止接收」。配對碼只存雜湊。"""

    __tablename__ = 'receiver_sessions'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # RS-{16 位十六進位}
    address: Mapped[str] = mapped_column(String(64))
    port: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(95), default='')
    code_hash: Mapped[str] = mapped_column(String(64), default='')
    code_expires_at: Mapped[str] = mapped_column(String(32), default='')
    status: Mapped[str] = mapped_column(String(16), default='active')  # active／ended／interrupted
    started_by: Mapped[str] = mapped_column(String(80), default='')
    started_at: Mapped[str] = mapped_column(String(32))
    ended_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ReceiverBatch(ClinicalBase):
    """一次傳送＝一筆檢查（上傳批次）；每張的狀態、雜湊、耗時寫在 items_json（傳送摘要用，不含檔名）。"""

    __tablename__ = 'receiver_batches'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # RB-{16 位十六進位}
    session_id: Mapped[str] = mapped_column(ForeignKey('receiver_sessions.id'), index=True)
    exam_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default='receiving')  # receiving／finished／cancelled
    items_json: Mapped[str] = mapped_column(Text, default='[]')
    created_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
