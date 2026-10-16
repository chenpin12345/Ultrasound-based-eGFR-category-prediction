export interface EvaluationRequest {
  model_id:string;dataset_id:string;split:string;device:string;source_evidence:string
  input_sources:{images:{kind:'dataset'|'job';id:string}}
  expected_preflight_sha256?:string
}
export interface EvaluationMetrics {
  accuracy?:number|null;macro_f1?:number|null;macro_defined_class_count?:number
  confusion_matrix?:number[][];per_class?:{class_index:number;support:number;precision:number|null;recall:number|null;f1:number|null}[]
  macro_per_image?:{dice:number|null;iou:number|null};micro_pixel_counts?:{dice:number|null;iou:number|null}
  undefined_reason?:string|null;sample_count:number;metric_version:string
}
export interface EvaluationSnapshot {
  model_name:string;weight_sha256:string;configuration_sha256:string;class_schema:{class_count:number;class_names:string[];sha256:string}
  dataset_name:string;split:string;sample_count:number;device:string;source_evidence:string;scope:string
  leakage:{cross_split_image_groups:number;cross_split_patient_groups:number;samples_without_patient_id:number;warning:string}
  request:EvaluationRequest
}
export interface EvaluationRecord {
  id:string;job_id:string;model_id:string;model_name:string;dataset_id:string;dataset_name:string;task:string;status:string;split:string
  sample_count:number;completed_count:number;cohort_sha256:string;metric_version:string;retry_of_id:string|null
  created_at:string;completed_at:string|null;snapshot?:EvaluationSnapshot
  result:{metrics?:EvaluationMetrics|null;complete_cohort:boolean;actual_device?:string;reason?:string;errors?:{sample_id:string;reason:string}[]}|null
}
export interface EvaluationPreflight {snapshot:EvaluationSnapshot;preflight_sha256:string}
