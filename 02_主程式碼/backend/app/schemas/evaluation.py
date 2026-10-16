from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..services.workflow_service import InputSources


class EvaluationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model_id: str = Field(min_length=1,max_length=36)
    dataset_id: str = Field(min_length=1,max_length=36)
    input_sources: InputSources
    split: Literal['all','train','val','test'] = 'test'
    device: Literal['cpu','cuda','auto'] = 'cpu'
    source_evidence: str = Field(min_length=10,max_length=4000)
    expected_preflight_sha256: str | None = Field(default=None,pattern='^[a-f0-9]{64}$')


class ReferenceMaskRegistration(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    dataset_id: str = Field(min_length=1,max_length=36)
    sample_id: str = Field(min_length=1,max_length=36)
    source: str = Field(min_length=10,max_length=4000)
    reviewer: str = Field(min_length=1,max_length=200)
    annotation_method: Literal['manual_annotation','external_reference']
    independent_of_evaluated_model: Literal[True]
    coordinate_mapping: Literal['identity']
    expected_preflight_sha256: str | None = Field(default=None,pattern='^[a-f0-9]{64}$')
