# 腎超工作台：後端

> 最後更新：2026-10-29。接手請先讀 [01_計畫與文件/README.md](../../01_計畫與文件/README.md)。
> 架構細節見[系統架構](../../01_計畫與文件/系統架構.md)，API 見[API規格](../../01_計畫與文件/API規格.md)，資料表與資料夾見[資料庫與檔案設計](../../01_計畫與文件/資料庫與檔案設計.md)。

FastAPI＋SQLAlchemy＋SQLite（三個資料庫），Python 3.12。訓練使用 PyTorch（CUDA 12.8 版）。

## 安裝與啟動

- 第一次使用：執行根目錄的 `setup.bat`。它會：
  - 建立 `.venv`；
  - 安裝 `requirements.txt`，再安裝 `requirements-gpu.txt`（torch 2.11＋cu128、torchvision、nnunetv2、transformers）；
  - 建置前端。
- 啟動：`start.bat`（`02_程式碼/scripts/run_server.py`），監聽 127.0.0.1:8000，同時提供前端；停止用 `stop.bat`。
- **請一律使用 `.venv/Scripts/python`**。系統的 `python` 可能是 Windows 的捷徑，不是真的 Python。

## 測試

```bash
.venv/Scripts/python -m pytest
```

- 測試使用暫存的工作區與程式產生的合成影像（`tests/synthetic.py`），不會讀寫 `IMG_original` 或真實的 `03_資料`。測試模式必須設定 `KIDNEY_WORKSPACE_ROOT`，否則程式拒絕啟動。
- 主要測試檔：
  - `test_core.py`：工作階段、CSRF、路由登記；
  - `test_deid_import.py`：去識別化、OCR、匯入；
  - `test_research.py`：病人對照、切分、洩漏、標註；
  - `test_drafts.py`：草稿；
  - `test_training.py`：訓練引擎、停止恢復、模型庫、流程、特徵、實驗；
  - `test_jobs.py`：背景工作；
  - `test_side_filter.py`：側別篩選；
  - `test_workspace.py`：M2.5 資料夾整理（索引不含個資、遮罩分桶、空資料夾清理、依任務搬移、開啟資料夾）；
  - `test_circling.py`：醫師圈選（批次、匯出、比對差異法、標籤 PNG、顏色對照、匯入、測試集保護）；
  - `test_egfr.py`：eGFR 2／3／5 類、臨床資料、純臨床基準、比較組、兩兩比較、匯出、三區分開（20 位合成病人）；
  - `test_masksets.py`：交叉預測遮罩組、特徵匯出、學習曲線；
  - `test_mask_channels.py`：④ 160 mm 裁切與遮罩通道、同步增強、4 通道模型、比較組一起評估固定測試集；
  - `test_trash_runs.py`：訓練與模型移入回收桶、還原、永久刪除（資料列、檔案、空資料夾）、切分與資料集版本的永久刪除；
  - `test_startup.py`：在新的程序裡開各頁與做常用操作，確認網頁請求不會載入 PyTorch；
  - `test_clinical_plan.py`：M3 醫師端資料表與資料夾、分析方案、模型保護、醫師端佇列。
- **`test_docs_sync.py`（文件檢查）**：程式中的每個 `/api` 路由、資料表、`App.tsx` 路徑、背景工作種類都必須寫在 `01_計畫與文件` 的對應文件，缺少時測試失敗並說明要補在哪裡。

## 模組地圖（`app/`）

| 模組 | 內容 |
|---|---|
| `main.py` | 建立 app、啟動時遷移與每日快照、中介層（路由登記 → 工作階段 → CSRF）、掛載路由、提供前端 |
| `core/` | `config.py` 設定與資料夾位置、`session.py` 本機工作階段、`routes_table.py` 路由表、`audit.py` 稽核、`errors.py`（`AppError`）、`ids.py` ID 與時間、`security.py` 檔案路徑安全 |
| `db/` | `models_system.py`、`models_research.py`、`session.py`（`session_scope('system'|'research'|'clinical')`） |
| `data/` | `importer.py` 匯入、`deid.py` 去識別化、`ocr.py`、`bodymark.py` 側別、`templates.py` 版面範本、`patients.py` 病人對照、`splits.py` 切分、`versions.py` 資料集版本、`egfr.py` eGFR 2／3／5 類定義（唯一來源）、`storage.py` 檔案路徑 |
| `clinical/` | M3 醫師端：`plan.py` 分析方案（三區各一個模型、候選標示、用到的模型受保護）、`models_cache.py` 模型快取與預熱（工作 `clinical_warmup`，醫師端佇列）；資料表在 `db/models_clinical.py` |
| `annotation/` | `service.py` 標註、`circling.py` 醫師圈選、`drafts.py` 草稿、`agreement.py` 一致性 |
| `features/` | `service.py` 回音與形態特徵 |
| `ml/` | `data.py` 任務與樣本、`engine.py` 訓練迴圈、`worker.py` 子程序入口、`models.py`、`losses.py`、`augment.py`、`metrics.py`、`runs.py` 訓練、`evaluation.py` 評估、`experiments.py` 實驗、`registry.py` 模型庫（合約 v3）、`pipeline.py` 一鍵流程、`nnunet.py`、`medsam.py`、`pretrained.py`；M2.5：`defaults.py` 訓練預設值（不需要 PyTorch；網頁請求只能用這個，不要 import `engine.py`）、`egfr_compare.py` eGFR 比較組、`masksets.py` 遮罩組、`roi.py` 160 mm 裁切與遮罩通道、`baseline.py` 有序邏輯迴歸基準、`tabular.py` 臨床與量測特徵、`paths.py` 依任務的資料夾 |
| `jobs/` | `manager.py` 背景工作（CPU 執行池＋獨占執行池）、`events.py` |
| `services/` | `settings_store.py` 設定與人員、`backups.py` 每日快照、`doctor.py` 環境檢查、`index.py` 索引 CSV、`workspace.py` 說明檔、空資料夾清理、資料夾搬移、匯出資料夾、開啟資料夾 |
| `trash/` | `service.py` 單一回收桶：切分、資料集版本、遮罩、訓練（連同模型）；永久刪除連檔案、不留空資料夾 |
| `api/routes/` | `system.py`、`jobs.py`、`data.py`、`research.py`、`ml.py`、`circling.py`、`egfr.py`；`api/deps.py` 取得操作者 |

## 常見的修改方式

### 新增 API

1. 在 `app/api/routes/` 的對應檔案加路由。寫入操作用 `audit.record(operator(request), …)` 記稽核；建立資源回 201，排入背景工作回 202。
2. 如果是新的前綴，加到 `app/core/routes_table.py` 的前綴清單，否則中介層回 403（`test_core.py` 會檢查）。
3. 在 `01_計畫與文件/API規格.md` 的對應表格加一列，格式 `` `方法 /api/路徑` ``（`test_docs_sync.py` 會檢查）。
4. 錯誤一律用 `AppError(狀態碼, 'CODE', '中文訊息')`，不回傳路徑或 traceback。

### 新增背景工作

1. 在模組中寫 `@register('種類', exclusive=…, resumable=…, label='中文名稱')` 的函式，接收 `JobContext`：
   - 用 `ctx.config` 讀設定；
   - 用 `ctx.progress(值, 訊息)` 回報進度、`ctx.event(...)` 寫事件；
   - 定期檢查 `ctx.should_stop()`，為真時儲存進度並結束。
2. 用 GPU 或大量記憶體的工作設 `exclusive=True`。
   醫師端的工作設 `pool='clinical'`：走醫師端自己的佇列，不排在訓練後面（M3，D44）。
3. 可以從中斷處繼續的工作設 `resumable=True`，並讓工作能略過已完成的部分。
4. 在 `app/main.py` 的 `_register_job_handlers` 匯入註冊工作的模組（例如 `from .annotation import drafts`），否則重啟後排隊中的工作找不到處理函式。
5. 在 `01_計畫與文件/系統架構.md` §4.2 的表格加一列（`test_docs_sync.py` 會檢查）。

### 新增資料表或欄位

1. 在 `app/db/models_research.py`（或 `models_system.py`）加模型。
2. 新增遷移 `migrations/research/versions/r000N_*.py`，照 `r0002_m2.py` 的寫法：
   - 先 `create_all(checkfirst=True)`；
   - 再逐欄檢查，缺少才 `add_column`；
   - 要能重複執行。
3. 在 `01_計畫與文件/資料庫與檔案設計.md` 第 1 節加表格（`test_docs_sync.py` 會檢查表名）。

### 新增系統設定

在 `app/services/settings_store.py` 的 `DEFAULTS` 加鍵與預設值（不認識的鍵會被拒絕），必要時在 `update` 加檢查，並更新資料庫與檔案設計 §1.2 的設定表。

### 新增資料夾位置

在 `workspace-layout.json` 加鍵，並在 `app/core/config.py` 為新鍵提供預設值：目前缺少任何鍵都會拒絕啟動，舊的工作區會因此打不開。

## 規則

- 不顯示、不回傳原始影像；檔案路徑一律經 `app/data/storage.py` 或 `get_settings().path(...)` 產生。
- API 不回傳 eGFR 數值，只回傳分組；標註相關 API 不回傳臨床資料。
- 開發與測試只用合成影像。
- 改了 API、資料表、背景工作、頁面，就要更新 `01_計畫與文件` 的對應文件。
