"""One process-wide inference/training lease. Resolve auto BEFORE scheduling."""
from contextlib import contextmanager
import threading
import time

gpu_lock = threading.Lock()
clinical_lock = threading.Lock()
_session_lock = threading.Lock()
_session = None

def reserve_session(owner,key,lifetime=300):
    from ..core.errors import AppError
    global _session
    with _session_lock:
        if _session and _session['key']!=key and (_session['expires']>time.time() or clinical_lock.locked()):
            raise AppError(409,'CLINICAL_SESSION_BUSY','另一個醫師分析會話仍在使用，請先停止來源。')
        _session={'owner':owner,'key':key,'expires':time.time()+lifetime}

def release_session(owner,key=None):
    global _session
    with _session_lock:
        if _session and _session['owner']==owner and (key is None or _session['key']==key): _session=None


def session_active(owner, key):
    with _session_lock:
        return bool(_session and _session['owner']==owner and _session['key']==key and _session['expires']>time.time())


def any_session_active():
    with _session_lock:
        return bool(_session and _session['expires']>time.time())


def resolve_device(value='auto'):
    import torch
    if str(value or 'auto') == 'auto':
        return 'cuda' if torch.cuda.is_available() else 'cpu'
    if str(value).startswith('cuda') and not torch.cuda.is_available():
        # Not transient: "cannot analyze", never a busy/retryable state. Still a
        # ValueError for callers that already convert it themselves.
        from ..core.errors import AppError
        class DeviceUnavailable(AppError,ValueError): pass
        raise DeviceUnavailable(422,'DEVICE_UNAVAILABLE','CUDA 無法使用；請明確選擇 CPU 或自動裝置。')
    return str(value)


@contextmanager
def clinical_lease(device):
    from ..core.errors import AppError
    if not clinical_lock.acquire(blocking=False):
        raise AppError(409, 'ANALYSIS_BUSY', '另一項分析正在執行。')
    locked = False
    try:
        if device.startswith('cuda'):
            locked = gpu_lock.acquire(blocking=False)
            if not locked:
                raise AppError(409, 'GPU_BUSY', 'GPU 正由研究工作使用，請稍後分析。')
        yield
    finally:
        if locked:
            gpu_lock.release()
        clinical_lock.release()
