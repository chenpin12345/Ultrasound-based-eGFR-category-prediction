from sqlalchemy.orm import DeclarativeBase


class SystemBase(DeclarativeBase):
    """system.sqlite3：工作階段、人員名單、設定、背景工作、稽核、回收桶。"""


class ResearchBase(DeclarativeBase):
    """research.sqlite3：批次、影像、病人、標註、切分、資料集版本。"""


class ClinicalBase(DeclarativeBase):
    """clinical.sqlite3：醫師端（M3 才加入資料表）。"""


BASES = {'system': SystemBase, 'research': ResearchBase, 'clinical': ClinicalBase}
