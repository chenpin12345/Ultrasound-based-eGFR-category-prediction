"""設定與路徑。

資料夾位置由工作區根目錄的 workspace-layout.json 決定；環境變數 KIDNEY_WORKSPACE_ROOT
可以把整個工作區指到別處（測試就是這樣隔離資料的）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[4]

LAYOUT_KEYS = (
    'code',
    'source_original',
    'data',
    'databases',
    'raw_archive',
    'deid_images',
    'annotations',
    'model_outputs',
    'dataset_versions',
    'splits',
    'import_records',
    'exports',
    'index',
    'models',
    'clinical',
    'inbox',
    'backups',
    'runtime',
)

# 後來才加的鍵：舊的 workspace-layout.json 沒有也能啟動，使用這裡的預設位置
OPTIONAL_LAYOUT = {
    'index': '03_資料/09_索引',
}


@dataclass(frozen=True)
class Settings:
    root: Path
    layout: dict[str, Path]
    host: str = '127.0.0.1'
    port: int = 8000
    testing: bool = False
    sse_poll_seconds: float = 1.0
    sse_heartbeat_seconds: float = 10.0
    cpu_workers: int = 2
    extra: dict[str, str] = field(default_factory=dict)

    def path(self, key: str) -> Path:
        return self.layout[key]

    @property
    def frontend_dist(self) -> Path:
        return self.path('code') / 'frontend' / 'dist'

    def database_file(self, name: str) -> Path:
        return self.path('databases') / f'{name}.sqlite3'


def load_layout(root: Path) -> dict[str, Path]:
    layout_file = root / 'workspace-layout.json'
    raw = json.loads(layout_file.read_text(encoding='utf-8'))
    raw = {**OPTIONAL_LAYOUT, **raw}
    missing = [k for k in LAYOUT_KEYS if k not in raw]
    if missing:
        raise RuntimeError(f'workspace-layout.json 缺少欄位：{", ".join(missing)}')
    resolved: dict[str, Path] = {}
    root_resolved = root.resolve()
    for key in LAYOUT_KEYS:
        path = (root / raw[key]).resolve()
        if root_resolved not in path.parents and path != root_resolved:
            raise RuntimeError(f'workspace-layout.json 的 {key} 必須位於工作區內')
        resolved[key] = path
    return resolved


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env_root = os.environ.get('KIDNEY_WORKSPACE_ROOT')
    testing = os.environ.get('KIDNEY_TESTING') == '1'
    if testing and not env_root:
        # 測試只能用暫存工作區；測試結束後殘留的背景執行緒也不能退回真實專案資料夾
        raise RuntimeError('測試模式必須設定 KIDNEY_WORKSPACE_ROOT，不能使用真實工作區。')
    root = Path(env_root or DEFAULT_ROOT).resolve()
    return Settings(
        root=root,
        layout=load_layout(root),
        host=os.environ.get('KIDNEY_HOST', '127.0.0.1'),
        port=int(os.environ.get('KIDNEY_PORT', '8000')),
        testing=testing,
        sse_poll_seconds=float(os.environ.get('KIDNEY_SSE_POLL', '1.0')),
    )


def reset_settings() -> None:
    get_settings.cache_clear()


# 醫師端資料夾（M3-8）：01_原始、05_接收暫存 是受限區
CLINICAL_FOLDERS = ('01_原始', '02_影像', '03_報告', '04_分析', '05_接收暫存')
CLINICAL_RESTRICTED = ('01_原始', '05_接收暫存')


def ensure_directories(settings: Settings) -> None:
    """建立系統需要的資料夾。原始影像資料夾只讀，不會建立或修改。"""
    for key in LAYOUT_KEYS:
        if key in {'code', 'source_original'}:
            continue
        settings.path(key).mkdir(parents=True, exist_ok=True)
    deid = settings.path('deid_images')
    for sub in ('影像', '計算用', '縮圖'):
        (deid / sub).mkdir(exist_ok=True)
    ann = settings.path('annotations')
    for sub in ('遮罩', '匯出', '一致性報告'):
        (ann / sub).mkdir(exist_ok=True)
    for sub in ('待匯入', '處理中', '已完成', '失敗'):
        (settings.path('inbox') / sub).mkdir(exist_ok=True)
    for sub in ('每日資料庫', '完整備份紀錄'):
        (settings.path('backups') / sub).mkdir(exist_ok=True)
    for sub in CLINICAL_FOLDERS:
        (settings.path('clinical') / sub).mkdir(exist_ok=True)
    for sub in ('日誌', '暫存', '交易紀錄', 'run'):
        (settings.path('runtime') / sub).mkdir(exist_ok=True)
