"""Versioned, memory-only image analysis. No inference input from file names."""
from __future__ import annotations

import hashlib
import io
import json
import math
import shutil
import time
from pathlib import Path
from functools import lru_cache

from PIL import Image
from ..core.errors import AppError
from . import store
from .resources import clinical_lease, resolve_device

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 16_000_000
_segmenters = {}

@lru_cache(maxsize=12)
def _verify_file(path,mtime,size,expected):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:
        raise AppError(409,'PLAN_INVALID','封存模型內容已變更，已停止分析。')

def verify_plan(plan):
    for model in plan['snapshot']['models'].values():
        path=store.managed(model['path'])
        try:
            stat=path.stat(); _verify_file(str(path),stat.st_mtime_ns,stat.st_size,model['sha256'])
            manifest=json.loads((path.parent/'model_metadata.json').read_text(encoding='utf-8'))
            if manifest!=model['manifest']: raise ValueError()
        except (OSError,ValueError): raise AppError(409,'PLAN_INVALID','模型方案檔案缺失或不一致。')


def decode(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise AppError(413, 'IMAGE_SIZE', '圖片大小必須介於 1 byte 與 32 MB。')
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in {'JPEG', 'PNG'} or im.width*im.height > MAX_PIXELS or getattr(im, 'n_frames', 1) != 1:
                raise ValueError()
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            return im.convert('RGB'), im.format
    except Exception:
        raise AppError(422, 'INVALID_IMAGE', '只接受可完整解碼的單張 JPEG／PNG，最多 1600 萬像素。')


def create_plan(name, model_id, segmenter_id, profile, device, actor):
    from ..db.models import ModelRecord
    from ..db.session import get_session_factory
    from ..core.config import get_settings
    from ..core.security import safe_resolve
    if profile.get('mode') not in {'unknown', 'legacy', 'prepared'}:
        raise AppError(422, 'PROFILE_INVALID', '前處理類型錯誤。')
    if profile['mode'] != 'unknown' and (not profile.get('evidence') or not profile.get('width') or not profile.get('height')):
        raise AppError(422, 'PROFILE_UNVERIFIED', '請記錄來源尺寸及前處理確認依據。')
    identifier = store.uid()
    destination = store.root() / 'bundles' / identifier
    destination.mkdir(parents=True)
    snapshot = {'device': device, 'models': {}}
    try:
        with get_session_factory()() as db:
            for role, mid in [('classifier', model_id), ('segmenter', segmenter_id)]:
                if not mid:
                    continue
                record = db.get(ModelRecord, mid)
                expected = 'classification' if role == 'classifier' else 'segmentation'
                if not record or record.task != expected or record.status not in {'ready', 'completed'}:
                    raise AppError(422, 'MODEL_REQUIRED', '請選擇可用且相容的模型。')
                source = safe_resolve(get_settings().models_dir, record.weights_path)
                manifest_path = safe_resolve(get_settings().models_dir, record.metadata_path)
                manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                if digest != record.sha256:
                    raise AppError(409, 'MODEL_CHANGED', '模型權重雜湊不符。')
                folder = destination / role; folder.mkdir()
                shutil.copyfile(source, folder/'weights.pth')
                (folder/'model_metadata.json').write_text(store.dumps(manifest), encoding='utf-8')
                snapshot['models'][role] = {'sha256': digest, 'manifest': manifest,
                    'path': (folder/'weights.pth').relative_to(store.root()).as_posix(), 'architecture': record.architecture}
        if 'classifier' not in snapshot['models']:
            raise AppError(422, 'MODEL_REQUIRED', '需要分類模型。')
        if 'mlp' in snapshot['models']['classifier']['architecture'] and 'segmenter' not in snapshot['models']:
            raise AppError(422, 'MODEL_REQUIRED', 'MLP 需要分割模型。')
        from ..ml.inference import read_model_metadata
        metadata=read_model_metadata(destination/'classifier'/'weights.pth')
        if metadata.class_count not in (2,3,5): raise AppError(422,'MODEL_CLASSES','只支援二／三／五分類。')
        snapshot['manifest_sha256']=hashlib.sha256(store.dumps(snapshot['models']).encode()).hexdigest()
        with store.transaction() as db:
            db.execute('INSERT INTO plans VALUES(?,?,?,?,?)', (identifier, name, store.dumps(profile), store.dumps(snapshot), time.time()))
            store.audit(db, actor, 'create_plan', identifier)
        return identifier
    except BaseException:
        # Only remove the newly-created, verified managed bundle directory.
        if destination.resolve().is_relative_to((store.root()/'bundles').resolve()):
            shutil.rmtree(destination)
        raise


def preprocess(image, fmt, profile, original_data=None):
    import cv2
    import numpy as np
    from ..ml.processing import _rb_mask
    if profile['mode'] == 'unknown':
        raise AppError(422, 'PROFILE_UNVERIFIED', '來源前處理尚未確認；僅可預覽。')
    if image.size != (profile['width'], profile['height']):
        raise AppError(422, 'SOURCE_SIZE_CHANGED', '影像尺寸不符合來源設定，已停止分析。')
    array = cv2.imdecode(np.frombuffer(original_data,dtype=np.uint8),cv2.IMREAD_COLOR) if original_data else cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    if profile['mode'] == 'legacy':
        if image.size != (1600,1200):
            array = cv2.resize(array,(1600,1200),interpolation=cv2.INTER_LANCZOS4)
        array = array[90:1114,235:1259]
        suffix = '.jpg' if fmt == 'JPEG' else '.png'
        array = cv2.imdecode(cv2.imencode(suffix,array)[1],cv2.IMREAD_COLOR)
        array = cv2.inpaint(array,_rb_mask(array),3,cv2.INPAINT_TELEA)
        array[:40,:]=0; array[-100:,:]=0; array[:,:25]=0
        array[400:485,20:40]=0; array[50:105,800:920]=0; array[0:105,1000:1024]=0
        array = cv2.imdecode(cv2.imencode(suffix,array)[1],cv2.IMREAD_COLOR)
    return array


def infer(data, plan, basic):
    import cv2
    import numpy as np
    import torch
    from torchvision import transforms
    from ..ml.contracts import IMAGENET_MEAN, IMAGENET_STD, normalize_metadata, classification_labels
    from ..ml.features import calculate_features_array
    from ..ml.inference import DEFAULT_MODEL_CACHE, read_model_metadata
    from ..ml.models import image_transform, single_image_probabilities
    from ..ml.segmentation import load_unet, refine_mask
    image, fmt = decode(data)
    verify_plan(plan)
    profile, snap = plan['profile'], plan['snapshot']
    device = resolve_device(snap['device'])
    start = time.perf_counter()
    with clinical_lease(device):
        processed = preprocess(image, fmt, profile, data)
        rgb = Image.fromarray(cv2.cvtColor(processed,cv2.COLOR_BGR2RGB))
        model_info = snap['models']['classifier']
        model_path = store.managed(model_info['path'])
        metadata = read_model_metadata(model_path)
        model = DEFAULT_MODEL_CACHE.get(model_path,metadata,torch.device(device))
        mlp = 'mlp' in metadata.architecture
        values = {k:basic[k] for k in ('age','has_diabetes') if k in basic}
        mask = None
        features = {}
        if mlp:
            for key in ('age','has_diabetes'):
                try:
                    val = float(values[key])
                    if not math.isfinite(val) or val < 0 or (key == 'has_diabetes' and val not in (0,1)):
                        raise ValueError()
                except (ValueError,KeyError,TypeError):
                    raise AppError(422,'METADATA_REQUIRED','MLP 需要有效年齡與糖尿病狀態，不自動補值。')
        if 'segmenter' in snap['models']:
            segmenter = snap['models']['segmenter']
            key = (segmenter['sha256'],device)
            if key not in _segmenters:
                _segmenters.clear()
                _segmenters[key] = load_unet(store.managed(segmenter['path']),device)
            tensor = transforms.Compose([transforms.Resize((512,512)),transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN,IMAGENET_STD)])(rgb).unsqueeze(0).to(device)
            with torch.inference_mode():
                raw = _segmenters[key](tensor)['out'].argmax(1).squeeze().cpu().numpy()
            mask = refine_mask(raw)
            feature_mask = cv2.resize((mask*255).astype('uint8'), (rgb.width,rgb.height), interpolation=cv2.INTER_NEAREST)
            if np.count_nonzero(feature_mask) < 100:
                raise AppError(422,'INVALID_MASK','分割區域不足，無法分析。')
            features=calculate_features_array(processed,feature_mask)
            if features['Length_px'] <= 0 or not all(math.isfinite(float(v)) for v in features.values()):
                raise AppError(422,'INVALID_FEATURES','影像特徵無效。')
            if mlp: values.update(features)
        with torch.inference_mode():
            tensor = image_transform()(rgb).unsqueeze(0).to(device)
            if mlp:
                mt = torch.tensor(normalize_metadata(values,metadata.train_stats),dtype=torch.float32,device=device).unsqueeze(0)
                logits = model(tensor,mt)
            else:
                logits = model(tensor)
            probs,predicted=single_image_probabilities(logits,metadata.class_count,metadata.coral)
            if not torch.isfinite(probs).all() or torch.any(probs<0) or torch.any(probs>1):
                raise AppError(422,'INVALID_PROBABILITIES','模型輸出無效，已停止分類。')
        labels = metadata.class_names or classification_labels(metadata.class_count)
        result = {'plan_id':plan['id'],'model_sha256':model_info['sha256'],'profile':profile,
                  'has_mask':mask is not None,
                  'probabilities':[{'label':labels[i],'probability':float(v)} for i,v in enumerate(probs.cpu())],
                  'predicted_class':labels[predicted],'features':values if mlp else features,
                  'processing_ms':round((time.perf_counter()-start)*1000,2),'device':device}
        artifacts = {'processed':rgb}
        if mask is not None:
            base = rgb.resize((512,512),Image.Resampling.BILINEAR)
            tint = Image.new('RGB',base.size,(245,180,40))
            alpha = Image.fromarray((mask*90).astype('uint8'))
            artifacts['overlay'] = Image.composite(tint,base,alpha)
            artifacts['mask'] = Image.fromarray((mask*255).astype('uint8'))
        return result, artifacts
