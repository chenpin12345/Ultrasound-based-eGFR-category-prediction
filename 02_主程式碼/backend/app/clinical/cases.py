"""Per-image case data (schema 1) and append-only case data versions.

Values come only from what a person typed on A or B. Nothing is inferred from file
names or folders, and "unknown" diabetes is never converted to "no".
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..core.errors import AppError
from . import store

CASE_SCHEMA=1
MAX_CASE_BYTES=4096
LABELS={'age':'年齡','has_diabetes':'糖尿病狀態（有／無）'}
EDITABLE=('age','has_diabetes','diabetes_status','exam_name','exam_time','notes','patient_ref','patient_name')
_CONTROL=re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def _text(value,*,multiline=False):
    if value is None: return None
    value=value.strip()
    if not value: raise ValueError('空白欄位請省略')
    if _CONTROL.search(value) or (not multiline and '\n' in value): raise ValueError('含有不允許的控制字元')
    return value


def _time(value):
    if value is None: return None
    try: datetime.fromisoformat(value)
    except ValueError: raise ValueError('檢查時間須為 ISO 8601 格式，例如 2026-10-13T09:30') from None
    return value


class CaseData(BaseModel):
    """Transferred case data. Strict: no type coercion, no unknown fields."""
    model_config=ConfigDict(extra='forbid',strict=True)
    case_code: str=Field(min_length=1,max_length=40)
    patient_ref: str|None=Field(default=None,max_length=40)
    patient_name: str|None=Field(default=None,max_length=60)
    age: int|None=Field(default=None,ge=0,le=130)
    diabetes: Literal['yes','no','unknown']|None=None
    side: Literal['left','right','both','unspecified']='unspecified'
    exam_name: str|None=Field(default=None,max_length=80)
    exam_time: str|None=Field(default=None,max_length=32)
    notes: str|None=Field(default=None,max_length=500)

    @field_validator('case_code','patient_ref','patient_name','exam_name')
    @classmethod
    def single_line(cls,value): return _text(value)

    @field_validator('notes')
    @classmethod
    def multiline(cls,value): return _text(value,multiline=True)

    @field_validator('exam_time')
    @classmethod
    def iso_time(cls,value): return _time(value)


class CaseUpdate(BaseModel):
    """Physician edit on B. Patient identity fields are only for demo cases."""
    model_config=ConfigDict(extra='forbid')
    title: str=Field(min_length=1,max_length=200)
    side: Literal['left','right','both','unspecified']='unspecified'
    age: float|None=Field(default=None,ge=0,le=130)
    diabetes: Literal['yes','no','unknown']|None=None
    exam_name: str|None=Field(default=None,max_length=80)
    exam_time: str|None=Field(default=None,max_length=32)
    notes: str|None=Field(default=None,max_length=500)
    patient_ref: str|None=Field(default=None,max_length=40)
    patient_name: str|None=Field(default=None,max_length=60)

    @field_validator('title','patient_ref','patient_name','exam_name')
    @classmethod
    def single_line(cls,value): return _text(value)

    @field_validator('notes')
    @classmethod
    def multiline(cls,value): return _text(value,multiline=True)

    @field_validator('exam_time')
    @classmethod
    def iso_time(cls,value): return _time(value)

    @field_validator('age')
    @classmethod
    def finite(cls,value):
        if value is not None and not math.isfinite(value): raise ValueError('年齡必須是有限數值')
        return value


def canonical(raw):
    return json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(canonical(raw)).hexdigest()


def parse(raw):
    """Validate one manifest case exactly as sent; the digest covers the raw form."""
    if not isinstance(raw,dict) or len(canonical(raw))>MAX_CASE_BYTES:
        raise AppError(422,'CASE_INVALID','案例資料格式錯誤或超過 4 KB。')
    try: return CaseData.model_validate(raw)
    except ValidationError as exc:
        fields=sorted({'.'.join(str(p) for p in e['loc']) for e in exc.errors()})
        raise AppError(422,'CASE_INVALID','案例資料欄位不符合規格：'+'、'.join(fields)) from None


def diabetes_fields(status):
    if status=='yes': return {'diabetes_status':'yes','has_diabetes':1}
    if status=='no': return {'diabetes_status':'no','has_diabetes':0}
    return {'diabetes_status':'unknown'} if status=='unknown' else {}


def transfer_payload(case: CaseData):
    payload={'case_code':case.case_code,'source':'transfer','identity_verified':False}
    for key in ('patient_ref','patient_name','age','exam_name','exam_time','notes'):
        if getattr(case,key) is not None: payload[key]=getattr(case,key)
    payload.update(diabetes_fields(case.diabetes))
    return payload


def edited_payload(exam,update: CaseUpdate):
    if exam['kind']=='patient' and (update.patient_ref is not None or update.patient_name is not None):
        raise AppError(422,'PATIENT_IDENTITY_FIXED','正式病人檢查的病人身分由病人紀錄決定，不能在案例資料中修改。')
    payload={k:v for k,v in exam['payload'].items() if k not in EDITABLE}
    for key in ('age','exam_name','exam_time','notes','patient_ref','patient_name'):
        if getattr(update,key) is not None: payload[key]=getattr(update,key)
    payload.update(diabetes_fields(update.diabetes))
    return payload


def diabetes_status(payload):
    if payload.get('diabetes_status') in ('yes','no','unknown'): return payload['diabetes_status']
    return {1:'yes',0:'no'}.get(payload.get('has_diabetes')) if not isinstance(payload.get('has_diabetes'),bool) else None


def missing(payload,required):
    result=[]
    for key in required:
        value=payload.get(key)
        valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
        if key=='age': valid=valid and 0<=value<=130
        if key=='has_diabetes': valid=valid and value in (0,1)
        if not valid: result.append(key)
    return result


def record_version(db,exam_id,revision,title,side,payload,source,actor):
    db.execute('INSERT INTO exam_basic_versions VALUES(?,?,?,?,?,?,?,?,?)',
               (exam_id,revision,title,side,store.dumps(payload),hashlib.sha256(store.dumps(payload).encode()).hexdigest(),source,actor,time.time()))


def update_exam(db,exam,title,side,payload,source,actor):
    revision=exam['revision']+1
    db.execute('UPDATE exams SET title=?,side=?,payload=?,revision=? WHERE id=? AND revision=?',
               (title,side,store.dumps(payload),revision,exam['id'],exam['revision']))
    record_version(db,exam['id'],revision,title,side,payload,source,actor)
    return revision
