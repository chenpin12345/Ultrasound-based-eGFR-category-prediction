"""Versioned reporting metrics only. Does not participate in training/selection."""
from __future__ import annotations

import math
from collections.abc import Sequence

CLASSIFICATION_VERSION = 'classification-v1-defined-class-macro'
SEGMENTATION_VERSION = 'foreground-v1-both-empty-one'


def evaluation_label(original_five_class: int, class_count: int) -> int:
    if type(original_five_class) is not int or original_five_class not in range(5):
        raise ValueError('A verified original five-class label is required.')
    mappings={2:(0,0,0,1,1),3:(0,0,1,2,2),5:(0,1,2,3,4)}
    if class_count not in mappings:
        raise ValueError('Only 2/3/5 classification is supported.')
    return mappings[class_count][original_five_class]


def _ratio(numerator, denominator):
    return numerator/denominator if denominator else None


def classification_metrics(expected: Sequence[int], predicted: Sequence[int], class_count: int) -> dict:
    if class_count not in (2,3,5) or len(expected)!=len(predicted):
        raise ValueError('Invalid classification cohort.')
    matrix=[[0]*class_count for _ in range(class_count)]
    for truth,guess in zip(expected,predicted):
        if type(truth) is not int or type(guess) is not int or truth not in range(class_count) or guess not in range(class_count):
            raise ValueError('Class indices must follow the model schema.')
        matrix[truth][guess]+=1
    per_class=[]
    for index in range(class_count):
        tp=matrix[index][index]
        support=sum(matrix[index])
        predicted_count=sum(row[index] for row in matrix)
        per_class.append({'class_index':index,'support':support,'predicted_count':predicted_count,
                          'precision':_ratio(tp,predicted_count),'recall':_ratio(tp,support),
                          'f1':_ratio(2*tp,support+predicted_count),
                          'undefined_reason':{'precision':None if predicted_count else 'no_predicted_samples',
                                              'recall':None if support else 'no_reference_samples',
                                              'f1':None if support+predicted_count else 'no_reference_or_predicted_samples'}})
    defined=[row['f1'] for row in per_class if row['f1'] is not None]
    total=len(expected)
    return {'metric_version':CLASSIFICATION_VERSION,'sample_count':total,'unit':'fraction',
            'accuracy':_ratio(sum(matrix[i][i] for i in range(class_count)),total),
            'macro_f1':sum(defined)/len(defined) if defined else None,
            'macro_defined_class_count':len(defined),'macro_rule':'mean_of_defined_class_f1',
            'undefined_reason':None if total else 'no_evaluated_samples',
            'confusion_matrix':matrix,'matrix_rows':'reference','matrix_columns':'prediction','per_class':per_class}


def foreground_counts(reference, prediction) -> dict:
    import numpy as np
    reference=np.asarray(reference)
    prediction=np.asarray(prediction)
    if reference.shape!=prediction.shape or reference.ndim!=2 or not reference.size:
        raise ValueError('Masks must have the same nonempty 2D coordinate grid; resizing is not allowed.')
    if not np.isin(reference,[0,1,False,True]).all() or not np.isin(prediction,[0,1,False,True]).all():
        raise ValueError('Metrics require explicit binary foreground masks.')
    truth,guess=reference.astype(bool),prediction.astype(bool)
    return {'intersection':int((truth&guess).sum()),'reference':int(truth.sum()),'prediction':int(guess.sum()),'pixels':int(truth.size)}


def segmentation_metrics(counts: Sequence[dict]) -> dict:
    def scores(item):
        intersection,reference,prediction=(item[key] for key in ('intersection','reference','prediction'))
        if any(type(item[key]) is not int or item[key]<0 for key in ('intersection','reference','prediction','pixels')) or not item['pixels']:
            raise ValueError('Invalid foreground counts.')
        if intersection>min(reference,prediction) or reference+prediction-intersection>item['pixels']:
            raise ValueError('Foreground counts are inconsistent.')
        denominator=reference+prediction
        return {'dice':2*intersection/denominator if denominator else 1.0,
                'iou':intersection/(denominator-intersection) if denominator else 1.0}
    rows=[scores(item) for item in counts]
    aggregate=scores({key:sum(item[key] for item in counts) for key in ('intersection','reference','prediction','pixels')}) if counts else {'dice':None,'iou':None}
    return {'metric_version':SEGMENTATION_VERSION,'sample_count':len(counts),'unit':'fraction',
            'empty_rule':'both_empty=1; exactly_one_empty=0',
            'macro_per_image':{key:math.fsum(row[key] for row in rows)/len(rows) if rows else None for key in ('dice','iou')},
            'micro_pixel_counts':aggregate,'per_image':rows,
            'undefined_reason':None if rows else 'no_evaluated_samples'}
