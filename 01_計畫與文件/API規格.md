# API 規格

> 版本 v2.1（2026-10-29）。依實際程式（`02_程式碼/backend/app/api/routes/*.py`）重寫；v2.1 起 M2.5 全部端點已實作（§9）。
> 文件導覽見 [README](README.md)；資料表見[資料庫與檔案設計](資料庫與檔案設計.md)；背景工作見[系統架構](系統架構.md) §4。
>
> **狀態標記**：【已實作】程式已有；【M2.5 規劃】本里程碑要做；【M3 規劃】醫師端，尚未實作；【已取消】曾經規劃但不做。
>
> **文件檢查**：`backend/tests/test_docs_sync.py` 會確認程式裡的每個 `/api` 路由都出現在本文件。新增 API 時，請在對應的表格加一列，格式為 `` `方法 /api/路徑` ``；路徑參數用 `{名稱}`。

---

## 1. 共通規則【已實作】

### 1.1 位址與前綴

- 後端只監聽本機：`http://127.0.0.1:8000`（`KIDNEY_HOST`、`KIDNEY_PORT` 可改）。
- 所有 API 都以 `/api` 開頭；其他路徑交給前端（單頁應用，見系統架構 §2）。
- 每個 `/api` 路由都必須登記在 `app/core/routes_table.py` 的前綴清單，否則中介層一律回 403（`API_NOT_REGISTERED`）。測試 `tests/test_core.py::test_every_api_route_is_registered` 會檢查。

### 1.2 工作階段與標頭（不登入）

| 標頭 | 何時需要 | 說明 |
|---|---|---|
| `X-Local-Init: 1` | `GET /api/session/challenge`、`POST /api/session` | 只有本機前端會送，用來擋掉其他網站的跨站請求 |
| Cookie（工作階段） | 除了公開路由以外的全部 API | `POST /api/session` 成功後設定；伺服器重啟後全部失效（綁定 `boot_id`） |
| `X-CSRF-Token` | 所有非 GET 的請求 | 值來自 `POST /api/session` 或 `GET /api/session` 的回應 |
| `X-Operator` | 選用；寫入稽核與標註時使用 | 右上角選的操作者姓名（URL 編碼）；沒送時為「本機」。存檔遮罩、確認或退回草稿需要真的選人，否則回 422 |

- 公開路由（不需工作階段）：`GET /api/health`、`GET /api/session/challenge`、`POST /api/session`。
- 挑戰碼一次性、120 秒過期；建立工作階段每分鐘最多 30 次。
- 沒有帳號、密碼與角色（決策 D12（改））；舊版文件的「權限」欄已移除。

### 1.3 狀態碼

| 狀態碼 | 意義 |
|---|---|
| 200 | 成功 |
| 201 | 已建立資源（訓練、切分、資料集版本、模型、實驗、特徵集…） |
| 202 | 已排入背景工作，回應含 `job_id`；進度用 `GET /api/jobs/{job_id}` 查詢 |
| 403 | 路由沒有登記在路由表（`API_NOT_REGISTERED`） |
| 401 | 沒有有效的工作階段（`SESSION_REQUIRED`）；寫入時缺少 CSRF token 回 403（`CSRF_REQUIRED`）；非本機來源回 403（`LOCAL_ONLY`、`ORIGIN_REJECTED`） |
| 429 | 建立工作階段太頻繁 |
| 404 | 找不到資源 |
| 409 | 狀態衝突（例如工作仍在執行、測試集已鎖定、同一份權重正在下載） |
| 422 | 輸入不正確（欄位格式、不認識的任務、缺少操作者） |

### 1.4 錯誤格式

```json
{ "error": { "code": "TASK_NOT_FOUND", "message": "找不到這個標註任務。", "details": {} }, "request_id": "…" }
```

- `message` 一律是繁體中文，不回傳檔案路徑或 traceback。
- `details` 只有在有補充資料時才會出現。
- 錯誤由 `app/core/errors.py` 的 `AppError` 產生。

### 1.5 稽核

表格中「稽核」欄打 ✓ 的 API，會用 `app/core/audit.py` 的 `audit.record(操作者, 動作, 對象類型, 對象 ID, 細節)` 寫入 `system.sqlite3` 的 `audit_log`，可在設定頁「稽核」查看。

---

## 2. 系統、工作階段、人員【已實作】

| 方法與路徑 | 參數／內容 | 回傳與說明 | 稽核 |
|---|---|---|---|
| `GET /api/health` | — | `{ok}`；公開 | |
| `GET /api/session/challenge` | 標頭 `X-Local-Init` | 一次性挑戰碼 | |
| `POST /api/session` | 挑戰碼 | 設定工作階段 cookie，回傳 CSRF token | |
| `GET /api/session` | — | 目前工作階段與 CSRF token | |
| `DELETE /api/session` | — | 撤銷工作階段 | |
| `GET /api/system/info` | — | 版本、Python、torch、GPU、資料夾位置 | |
| `GET /api/system/doctor` | — | 環境檢查：Python、套件、RapidOCR、CUDA 版 PyTorch、MedSAM 權重、GPU、IMG_original、寫入權限、資料庫版本、前端建置、磁碟空間 | |
| `GET /api/settings` | — | 所有設定值（`app/services/settings_store.py` 的 `DEFAULTS`） | |
| `PUT /api/settings` | `{鍵: 值}`；不認識的鍵回 422；`primary_split_id` 必須是存在的切分 | 更新設定 | ✓ |
| `GET /api/people` | — | 醫師與操作者名單 | |
| `POST /api/people` | `{name, kind: physician|operator}` | 新增人員（201） | ✓ |
| `PATCH /api/people/{person_id}` | `{active}` | 啟用或停用 | ✓ |
| `GET /api/audit` | `limit`（1–1000，預設 200） | 最新的稽核紀錄 | |
| `GET /api/backups` | — | 每日資料庫快照清單 | |
| `POST /api/backups/snapshot` | — | 立即建立資料庫快照（同步執行，含完整性檢查與 `manifest.json`） | ✓ |
| `GET /api/overview` | — | 總覽頁的數字與提醒（待確認影像、未對應影像、失敗工作、待處理回饋），`clinical`：醫師端事件（§10.1） | |
| `GET /api/docs` | — | FastAPI 自動產生的互動式文件（Swagger） | |
| `GET /api/openapi.json` | — | OpenAPI 定義 | |
| `POST /api/system/index` | — | 重新產生 `03_資料/09_索引/` 的 CSV（不含個資）；回傳寫入與略過（檔案被 Excel 開著時）的檔名。匯入、訓練等背景工作結束後也會自動更新 | ✓ |
| `POST /api/system/open-folder` | `{kind, id}`；kind：`run`、`model`、`evaluation`、`index`、`exports`、`models`、`annotations`、`model_outputs`、`relpath` | 在檔案總管開啟資料夾；只允許專案內，受限區（原始封存、IMG_original、資料庫、備份 `07_備份`）回 403（備份為 M3 #113 補上） | |
| `GET /api/system/folder-migration` | — | 預覽：哪些訓練、模型、評估資料夾要移到 eGFR／分割／回音分級 子資料夾 | |
| `POST /api/system/folder-migration` | — | 執行搬移並更新資料庫路徑；訓練中的略過；搬完寫 `摘要.txt` | ✓ |

---

## 3. 背景工作【已實作】

| 方法與路徑 | 參數／內容 | 回傳與說明 | 稽核 |
|---|---|---|---|
| `GET /api/jobs` | `status`、`limit`（1–500，預設 100） | 工作清單，新的在前 | |
| `GET /api/jobs/{job_id}` | — | 單一工作：狀態、進度、訊息、結果、錯誤 | |
| `GET /api/jobs/{job_id}/events` | `after`（事件編號） | SSE 串流：每秒輪詢、每 10 秒心跳、結束時送 `event: end`。前端目前改用輪詢 `GET /api/jobs/{job_id}` | |
| `POST /api/jobs/{job_id}/stop` | — | 要求停止（工作每秒檢查停止旗標） | ✓ |
| `POST /api/jobs/{job_id}/resume` | — | 從中斷處恢復（只限可恢復的工作種類） | ✓ |
| `POST /api/jobs/{job_id}/retry` | — | 以相同設定建立新工作，`retry_of` 指向原工作 | ✓ |
| `POST /api/jobs/delete` | `{ids: [...]}`（1–1000 筆） | **永久刪除**已結束工作的紀錄與事件，排隊中或執行中的會略過；回傳 `{deleted, skipped}`。只刪紀錄，不影響影像、遮罩、訓練結果與模型（決策：回收桶原則的例外，見 M2 #77） | ✓ |

---

## 4. 匯入、影像、版面範本【已實作】

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/inbox` | — | `06_匯入區/待匯入/` 裡可以匯入的資料夾 | | |
| `POST /api/imports/preview` | `{source: original|inbox, folder?}` | 預覽：張數、機型、重複、缺少的病人資料 | | |
| `POST /api/imports` | 同上 | 開始匯入，回傳 `batch_id`、`job_id`（202） | `import` | ✓ |
| `GET /api/imports` | — | 匯入批次清單 | | |
| `GET /api/imports/{batch_id}` | — | 匯入報表（已匯入、待確認、重複略過、原因統計） | | |
| `GET /api/images` | `status`、`machine`、`side`（`left`／`right`／`unknown`）、`batch_id`、`patient_id`、`unmatched`、`offset`、`limit`（1–500，預設 60） | 影像清單與總數 | | |
| `GET /api/images/stats` | — | 依機型 × 尺寸 × 狀態的張數 | | |
| `GET /api/images/{image_id}` | — | 影像詳細：側別與來源、切面、像素間距與檢查結果、技師量測、掃描參數、caliper 像素數、病人（只給分組）、遮罩版本 | | |
| `GET /api/images/{image_id}/file` | `kind`：`model`（模型用）／`calc`（計算用）／`thumb`（縮圖） | 去識別化影像檔；**永遠不提供原始影像** | | |
| `PATCH /api/images/{image_id}` | `{status?, exclude_reason?, side?, view?}` | 排除或恢復、修正側別與切面（來源記為 manual） | | ✓ |
| `POST /api/images/bulk-status` | `{image_ids, status: usable|excluded, exclude_reason?}` | 批次排除或恢復 | | ✓ |
| `POST /api/images/bulk-side` | `{image_ids, side}` | 批次設定側別 | | ✓ |
| `POST /api/images/redeid` | `{template_id?, batch_id?}` | 依目前範本重新去識別化（202）；人工標註不受影響 | `redeid` | ✓ |
| `POST /api/images/reread-side` | — | 用體表示意圖重新判斷全部影像的側別（202） | `reread_side` | ✓ |
| `GET /api/templates` | — | 版面範本清單（依機型與尺寸） | | |
| `GET /api/templates/{template_id}` | — | 範本內容：遮蓋區域與 6 個讀取框（標頭、參數、量測、側別、深度尺、體表示意圖） | | |
| `PUT /api/templates/{template_id}` | `{regions, readers}` | 儲存範本，版本 +1 | | ✓ |
| `GET /api/templates/{template_id}/samples` | `limit`（1–12，預設 6） | 同尺寸的範例影像 ID | | |
| `POST /api/templates/{template_id}/preview` | `image_id`（查詢參數）＋ `{regions, readers}` | 用尚未儲存的範本預覽去識別化結果（模糊預覽） | | |

---

## 5. 病人、切分、資料集版本【已實作】

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/patients` | — | 病人清單：P-編號、性別、年齡、糖尿病、脂肪肝、**eGFR 分組**（不回傳 eGFR 數值）、影像數 | | |
| `POST /api/patients/tables` | multipart：CSV 或 XLSX | 上傳病人表，存成 `01_原始封存/病人表/T-{16 碼}.xlsx|csv`（201） | | ✓ |
| `POST /api/patients/match-preview` | `{table_id}` | 對照預覽：依 eGFR 與 OCR 年齡（±1）、性別分組；病歷號分組只在記憶體中使用 | | |
| `POST /api/patients/match` | `{table_id}` | 執行對照；空白欄位用病人表回填（年齡、糖尿病、脂肪肝、日期） | | ✓ |
| `GET /api/patients/review` | — | 需要人工確認的影像組與候選病人 | | |
| `POST /api/patients/review/rematch` | — | 用刪去法重新比對待確認的組（202） | `rematch_patients` | ✓ |
| `POST /api/patients/review/resolve` | `{table_id, image_ids, row_key}` | 人工指定這組影像屬於哪位病人 | | ✓ |
| `GET /api/splits` | — | 切分清單 | | |
| `POST /api/splits/preview` | `{seed, folds, test_ratio, note}` | 預覽各組人數與 eGFR 分組分布 | | |
| `POST /api/splits` | 同上 | 建立病人層級切分（201） | | ✓ |
| `GET /api/splits/{split_id}` | — | 切分內容與各組統計 | | |
| `POST /api/splits/{split_id}/extend` | `{mode: folds|prospective, note}` | 新病人分到各折或放前瞻集，舊病人組別不變（201） | | ✓ |
| `GET /api/splits/{split_id}/leakage` | — | 洩漏檢查：跨組影像內容向量相關 ≥ 0.95 的組合（M2 #65） | | |
| `GET /api/dataset-versions` | — | 資料集版本清單 | | |
| `POST /api/dataset-versions` | `{note}` | 凍結資料集版本：影像、病人臨床欄位、每張的遮罩版本與來源（201） | | ✓ |

---

## 6. 標註與草稿【已實作】

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/annotation/tasks` | — | 標註任務摘要：遮罩、回音分級（含雙人數）、側別（品質任務已移除，D25） | | |
| `GET /api/annotation/queue/{task}` | `rater` | 標註佇列，回傳全部項目（M2.5 移除 200 筆上限）；畫面不含 eGFR | | |
| `GET /api/annotation/state/{task}/{key}` | `rater` | 這位標註者在此項目的標註（遮罩：自己最新的版本，沒有時用最新、未退回的版本），用來在編輯器中還原 | | |
| `PUT /api/annotation/masks/{image_id}` | `{shapes, flags, status: draft|done}` | 存遮罩，每次都是新版本；需要操作者。形狀依固定順序疊放（肝／脾 → 腎實質 → 腎竇）。`flags` 只接受 `occluded`、`no_reference`，其他旗標由系統產生（不沿用草稿）。修改醫師圈選的遮罩時來源為 `edited_upload`，保留構造狀態與圈選者代號，完成時記錄確認者 | | ✓ |
| `GET /api/annotation/masks/{image_id}` | — | 這張影像的全部遮罩版本 | | |
| `PUT /api/annotation/grades` | `{patient_id, side, grade?, unsure_reason?, rater, image_id?}` | 回音分級（一個病人側一筆；rater 是醫師名單中的醫師） | | ✓ |
| `PUT /api/annotation/labels/{image_id}` | `{kind: side, value: {side, view}}` | 側別與切面標籤；`kind=quality` 回 422（D25） | | |
| `GET /api/annotation/agreement` | — | 最新的一致性報告（分級 kappa、遮罩 Dice） | | |
| `POST /api/annotation/agreement` | — | 重新計算一致性 | | ✓ |
| `POST /api/annotation/drafts/legacy` | `{folder}` | 匯入舊程式遮罩成草稿，自動分出腎竇（202） | `legacy_masks` | ✓ |
| `POST /api/annotation/drafts/medsam` | — | MedSAM 重畫腎臟（選用比較，202） | `medsam_kidney` | ✓ |
| `POST /api/annotation/drafts/organs` | — | 規則產生肝／脾草稿（202） | `organ_drafts` | ✓ |
| `POST /api/annotation/drafts/regenerate` | `{folder}` | 把未確認的舊程式與規則草稿移入回收桶（同一組），再依新規則重做（202） | `regenerate_drafts` | ✓ |
| `POST /api/annotation/drafts/delete` | `{sources: [...]}`（1–10 個） | 依來源把待確認、被退回、已被修改的草稿移入回收桶，每個來源一組；不認識的來源回 422 | | ✓ |
| `GET /api/annotation/drafts/queue` | `only_needed`、`limit`（1–500）、`offset` | 草稿確認佇列，需要確認的排前面 | | |
| `GET /api/annotation/drafts/stats` | — | 各來源的草稿數、接受、修改、退回、接受率、可重新產生數 | | |
| `POST /api/annotation/drafts/{mask_id}/decision` | `{decision: accept|reject, reason}` | 接受（記錄確認者與時間）或退回；需要操作者 | | ✓ |
| `GET /api/feedback` | — | 臨床回饋清單：檢查、項目、AI 值、醫師值、`kind`（exclude／include／side／length／grade）、側別、影像、原因、模型、決定者（不含臨床資料） | | |
| `POST /api/feedback/{item_id}/{decision}` | `decision`：`accept`／`reject` | 處理一筆臨床回饋（記錄決定者與時間） | | ✓ |

---

## 7. 訓練、實驗、模型、評估、特徵、流程【已實作】

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/pretrained` | — | 預訓練權重清單與下載狀態（resnet18-imagenet、resnet34-imagenet、medsam-vit-base） | | |
| `POST /api/pretrained/{name}/download` | — | 下載權重（202）；同一份正在下載時回 409 | `download_pretrained` | ✓ |
| `GET /api/training/tasks` | — | 可訓練的任務、類別與預設設定 | | |
| `GET /api/training/runs` | `task` 或 `experiment_id`（至少一個，否則 422；三區分開，D28） | 訓練清單 | | |
| `POST /api/training/runs` | `{task, name, dataset_version_id, split_id, config, start}` | 建立訓練（201）；`start=true` 時同時排入工作。eGFR 的 `config` 可帶 `egfr_classes`（2／3／5）、`inputs`（image、clinical、measures、mask_channels 的組合）、`mask_set_id`、`roi_mm`；`arch=logreg`（純臨床、純量測基準）改排 `train_baseline`。遮罩組必須已完成且和訓練同一個切分（409 `MASK_SET_SPLIT`） | `train`、`train_baseline` | ✓ |
| `GET /api/training/runs/{run_id}` | — | 訓練詳細：設定、各折歷程、摘要、最新的交叉驗證評估（`latest_evaluation`）與最新的固定測試集評估（`latest_test`，M2.5） | | |
| `POST /api/training/runs/{run_id}/start` | — | 開始或從 checkpoint 恢復（202）；基準模型重新計算 | `train`、`train_baseline` | ✓ |
| `POST /api/training/runs/{run_id}/evaluate` | — | 用 OOF 預測產生交叉驗證評估報告 | | ✓ |
| `GET /api/training/compare` | `a`、`b` | 兩個訓練的各折差異與 Nadeau-Bengio 校正 t 檢定（需同一切分） | | |
| `POST /api/training/nnunet` | `{dataset_version_id, split_id, epochs: 100|250|1000}` | nnU-Net v2 分割基準（202） | `nnunet_train` | ✓ |
| `GET /api/experiments` | `task`（必填） | 分割或回音分級的實驗清單；eGFR 比較組不在這裡（見 §9.3） | | |
| `POST /api/experiments` | `{name, template: init|ablation|custom, task, dataset_version_id, split_id, base_config, feature_set_id, note}` | 建立實驗與草稿訓練（201） | | ✓ |
| `GET /api/experiments/{exp_id}` | — | 實驗內的訓練與比較 | | |
| `POST /api/experiments/{exp_id}/start` | — | 依序排入全部訓練（202） | `train` | ✓ |
| `GET /api/models` | `task`（必填） | 模型清單（只列該任務） | | |
| `POST /api/models` | `{run_id, name, version, note}` | 註冊模型（201）；ID 為 `{任務}/{名稱}@{版本}`。manifest 為合約第 3 版（記錄類別數、輸入方式、通道數、臨床欄位、裁切方式、遮罩組與分割訓練）；純臨床、純量測基準不能註冊（409 `BASELINE_NOT_REGISTRABLE`） | | ✓ |
| `GET /api/models/{model_id}` | — | 模型詳細、模型卡、評估紀錄（路徑參數允許 `/`） | | |
| `POST /api/models/{model_id}/stage` | `{stage: research|candidate|clinical|retired, confirm_name, approver}` | 變更階段；升為臨床要輸入模型名稱並選核准醫師，同任務舊的臨床模型自動降為候選 | | ✓ |
| `GET /api/models/{model_id}/test-readiness` | — | 固定測試集是否可以評估：這個任務的測試鎖（分任務，D27）；分割另列缺少醫師遮罩的測試病人側（每側至少 1 張）；eGFR、回音分級另列測試影像缺少的模型輸入（`missing_masks`：④ 遮罩組的遮罩；`missing_features`：⑤ 量測特徵） | | |
| `POST /api/models/{model_id}/test` | `{confirm}`（輸入模型 ID） | 固定測試集評估（202）；**先鎖定這個任務的測試集**，只能一次，不影響其他任務。分割只評估有確認遮罩的影像；標成「不在影像中」的構造報告偽陽性比例。測試影像缺少遮罩或量測特徵時回 409 `TEST_INPUTS_MISSING`（在鎖定前檢查） | `evaluate_test` | ✓ |
| `GET /api/evaluations` | `model_id`、`run_id` | 評估紀錄（只在所屬的訓練或模型頁顯示，不提供跨任務清單）；回收桶裡的訓練、模型的評估不列出 | | |
| `GET /api/features` | — | 特徵集清單（含來源、遮罩組、資料夾 `relpath`） | | |
| `POST /api/features` | `{source: masks|run|mask_set, run_id?, mask_set_id?, note}` | 擷取回音與形態特徵（201，背景執行）；`mask_set` 用遮罩組，涵蓋全部影像（⑤⑥ 使用） | `extract_features` | ✓ |
| `GET /api/features/{fs_id}` | `limit`（1–2000） | 特徵表、依側別的 Spearman 分析、腎長 Bland-Altman | | |
| `POST /api/features/{fs_id}/export` | — | 匯出到 `08_匯出/{日期}_特徵_{FS-ID}/`：`特徵.csv`（逐張）、`Spearman.csv`、`腎長BlandAltman.csv`、`說明.txt`；病人只用 P-編號、不含 eGFR 數值（M2.5）。回傳 `folder` | | ✓ |
| `POST /api/pipelines` | `{seg_model_id, classifier_ids, image_ids?}` | 一鍵流程或 AI 分析（202）。需要量測或遮罩通道的模型必須同時選分割模型，且必須是它訓練時用的分割訓練註冊的（否則工作失敗，`CONTRACT_MISMATCH`）；臨床欄位取自病人資料 | `pipeline` | ✓ |
| `GET /api/pipelines/{job_id}` | — | 流程結果（依病人 × 側別整合） | | |
| `GET /api/pipelines/{job_id}/masks/{image_id}` | — | 預測遮罩疊圖 PNG | | |

---

## 8. 回收桶【已實作】

| 方法與路徑 | 參數／內容 | 回傳與說明 | 稽核 |
|---|---|---|---|
| `GET /api/trash` | `kind`（run、split、dataset_version、mask、clinical_exam） | 回收桶群組清單（訓練與模型、切分、資料集版本、遮罩、醫師端檢查）。訓練組裡可能另有跟著移入的遮罩組（mask_set）、特徵集（feature_set）、比較組（experiment） | |
| `POST /api/trash` | `{kind: split|dataset_version|mask|run|clinical_exam, id, reason}` | 移入回收桶（201）；`run` 等同下面的 `POST /api/training/runs/trash` 只放一個；`clinical_exam` 連同報告一起，有已簽核報告回 409 `REPORT_SIGNED`（只能作廢），還在分析回 409 `EXAM_BUSY` | ✓ |
| `POST /api/trash/{group_id}/restore` | — | 整組還原（訓練與它的模型一起回來）；更新索引 | ✓ |
| `POST /api/trash/{group_id}/purge` | `{confirm: "永久刪除"}` | 永久刪除資料列與檔案，回傳 `removed`（刪掉的檔案或資料夾）。訓練：刪訓練、評估、模型資料夾與分割的 OOF 預測遮罩（最後一個 nnU-Net 訓練另刪 nnU-Net 共用資料夾）；切分：刪 `06_資料切分/{id}.json`；資料集版本：刪 `05_資料集版本/{id}/`；遮罩：刪 PNG 並移除變空的資料夾，醫師圈選匯入的遮罩被刪時圈選項目回到「已轉換，待檢查」；醫師端檢查：刪資料列、去識別化影像、分析結果、報告 PDF、受限區的原始檔（整個上傳批次資料夾）、沒傳完的接收暫存、研究端關於它的臨床回饋，沒有其他檢查的病例代碼一併刪除。2026-11-09 起（M3 #127–#139）：訓練另刪遮罩組、特徵集、用這些模型跑的一鍵流程結果、沒有訓練使用的 nnU-Net 訓練器結果、成員都刪掉的比較組；刪掉主切分時清除設定。只刪物件自己的資料夾，標準資料夾與工作區絕不刪。切分或資料集版本還被訓練或遮罩組使用時回 409 `IN_USE`；遮罩組、特徵集還被其他訓練使用時回 409 `RUN_IN_USE`；**有檔案被其他程式開著時回 409 `FILE_IN_USE`，什麼都不刪**（先把每個要刪的檔案改名確認，全部成功才改資料庫） | ✓ |

---

## 9. M2.5 新增與修改【已實作】

M2.5 的端點全部已實作；測試見 `tests/test_circling.py`、`test_masksets.py`、`test_egfr.py`、`test_mask_channels.py`。

### 9.1 醫師圈選【已實作】

程式：`app/annotation/circling.py`、`app/api/routes/circling.py`。批次只從主切分（設定 `primary_split_id`，沒設定時用最新的切分）選影像。

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/circling/batches` | — | 批次清單（各狀態張數）與進度：測試集病人側完成數、訓練影像已有醫師遮罩的張數 | | |
| `POST /api/circling/batches` | `{kind: test|train|all, size, note}` | 建立批次（201）。all：全部影像（圈選網站用），排除 `excluded` 與已有醫師遮罩的影像，測試集排最前面（D47）。test：每位測試病人每側 1 張（長軸、技師量過腎長、最長者優先），已在批次中的病人側略過；train：預設 100 張，依折、eGFR 分組、機型、側別輪流抽樣，排除測試病人、已在批次中或已有醫師遮罩的影像，優先選還沒涵蓋到的病人側。沒有可加入的影像時回 409 | | ✓ |
| `GET /api/circling/batches/{batch_id}` | — | 批次與每張影像的狀態（pending、exported、parsed、imported、needs_redraw）、轉換結果（參考影像、各構造面積、警告、錯誤）、構造狀態 | | |
| `POST /api/circling/batches/{batch_id}/export` | `{include_original, confirm}` | 匯出（202）：去識別化影像（檔名＝影像 ID）、`清單.csv`、`圈選說明.txt`、zip，放在 `08_匯出/{日期}_醫師圈選_{批次}/`；已匯入的不再匯出。`include_original=true` 時 `confirm` 必須等於「我了解原始影像含有個資」，原始影像改名為影像 ID 存到受限區 `01_原始封存/醫師圈選匯出/` | `circling_export` | ✓ |
| `POST /api/circling/batches/{batch_id}/upload` | `{folder, circler}` | 讀取醫師傳回的資料夾（含子資料夾，依檔名中的影像 ID 對應；202）。有 `圈選結果.json`（圈選網站輸出）時，項目狀態、每張圈選者、備註以它為準，基本四項以外的圈選存進遮罩 `flags.site.extras`；每張完成的影像在這一步就寫入回音分級（`image_grades`）；和已匯入遮罩完全相同的影像略過（結果的 `unchanged`）；格式不對時工作失敗。**側別與能否使用以網站為準（D52）**：和主系統不同時改成網站的值（側別來源記為 circling；「不能用」排除並附原因、圈選項目改為 `unusable`；「完成」改成可用），改了什麼列在結果的 `site.applied` 與每張的提示，並寫入稽核。結果另列 `site.unusable`、`site.no_label`、`site.label_file_missing` 的影像 ID。標籤 PNG（0–4）直接讀取；彩色圈選用比對差異法（和去識別化影像、勾選原始影像時也和原始影像比較，取差異最小者），只取掃描扇形區內、差異 > 30 且顏色在對照中的像素，封閉輪廓填滿、小缺口補起、未封閉者警告。尺寸不符、沒設定顏色對照、沒有任何圈選列為錯誤。傳回的原檔：去識別化版本存 `03_人工標註/醫師圈選回傳/{批次}/原檔/`，原始影像版本存受限區；轉換結果存 `…/解析/`。結果：matched、parsed、errors、not_in_batch | `circling_parse` | ✓ |
| `GET /api/circling/items/{item_id}/overlay` | — | 去識別化影像＋轉換結果的疊圖 PNG（不顯示醫師傳回的原檔） | | |
| `PATCH /api/circling/items/{item_id}` | `{structures: {kidney|sinus|liver|spleen: absent|unlabeled}}` | 修改沒有圈到的構造的狀態；已畫的不能改、沒畫的不能設為已畫（422） | | ✓ |
| `POST /api/circling/items/{item_id}/reject` | `{reason}` | 退回，狀態改為「需請醫師重圈」；已匯入的不能退回（409） | | ✓ |
| `POST /api/circling/batches/{batch_id}/import` | `{item_ids?}` | 把轉換成功、沒有錯誤的項目匯入成遮罩：來源 `physician_upload`、狀態 done、`verified_by`＝「醫師圈選（代號）」；旗標含 `structures`、`labeled`、`circler`、`batch_id`、警告 | | ✓ |
| `POST /api/circling/colors/detect` | `{path}` | 從一張圖找出使用的顏色（檔名含影像 ID 時只看醫師加的筆畫）；只回傳顏色與像素數 | | |
| `GET /api/circling/colors` | — | 目前的顏色對照、容許距離、構造名稱、原始影像匯出的確認文字 | | |

設定鍵（`PUT /api/settings`）：M3 新增 `clinical_plan`、`clinical_receiver_port`、`clinical_device_mode`（見 §10.1）；`primary_split_id`、`circling_colors`（`[{color: "#rrggbb", structure: kidney|sinus|liver|spleen}]`，同一顏色只能一個構造）、`circling_color_tolerance`（5–150，預設 40）。

### 9.2 交叉預測遮罩組【已實作】

程式：`app/ml/masksets.py`。遮罩存於 `03_資料/04_模型產出/預測遮罩組/{MS-ID}/{分桶}/{影像ID}.png`，`manifest.json` 記錄每張用哪一折、腎臟像素數、是否找不到腎臟。

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/mask-sets` | — | 遮罩組清單（分割訓練、切分、張數、找不到腎臟數、狀態） | | |
| `POST /api/mask-sets` | `{seg_run_id, note}` | 產生遮罩組（202，回傳 `id`、`job_id`）：資料集版本的每張影像，第 k 折病人用第 k 折模型，測試病人與不在切分中的影像用各折平均；後處理只留最大的腎臟區塊。任何一折沒有最佳模型回 409 `MASKSET_INCOMPLETE_FOLDS`；nnU-Net 訓練回 409 `RUN_NOT_SUPPORTED`。完成後自動建立 `source=mask_set` 的特徵集 | `mask_set` | ✓ |
| `GET /api/mask-sets/{ms_id}` | — | 覆蓋率：總張數、各來源（fold-k／ensemble）張數、找不到腎臟的影像、抽查樣本 | | |
| `GET /api/mask-sets/{ms_id}/overlay/{image_id}` | — | 去識別化影像＋預測遮罩疊圖 PNG | | |

### 9.3 eGFR 比較【已實作】

程式：`app/ml/egfr_compare.py`、`app/api/routes/egfr.py`。比較組存成 `experiments` 的一列（`template='egfr_compare'`），成員是一般的訓練。

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/egfr/options` | — | 類別數 2／3／5 的類別名稱、輸入方式 ①–⑥（代號、名稱、是否需要遮罩、是否在 CPU 執行）、快速選取「無遮罩版」「有遮罩版」、預先指定的主要比較 | | |
| `GET /api/egfr/comparisons` | — | 比較組清單（輸入方式、類別數、成員數、完成數、切分） | | |
| `POST /api/egfr/comparisons` | `{name, dataset_version_id, split_id, inputs: [image|image_clinical|clinical|image_mask|image_measures|measures], classes: [2|3|5], base_config, mask_set_id?, reuse=true, start=true}` | 建立比較組（201）：勾選的輸入 × 類別數各一個訓練。`reuse=true` 時設定相同（切分、版本、種子、骨幹、epoch、輸入大小等）的已完成訓練直接沿用。一個都沒勾回 422；勾了 ④⑤⑥ 卻沒有遮罩組回 409 `MASK_SET_REQUIRED`；遮罩組切分不同回 409 `MASK_SET_SPLIT`；⑤⑥ 需要遮罩組的特徵集（409 `FEATURES_REQUIRED`），④ 不需要 | `train`、`train_baseline` | ✓ |
| `GET /api/egfr/comparisons/{exp_id}` | — | 比較格：每格的狀態與病人層級指標（AUC(<60)、AUC(<30) 與信賴區間、QWK、合併成 3 類的 QWK、MAE、準確率、Brier、ECE、混淆矩陣、各類敏感度）；`test`：這一格最近一次固定測試集評估（評估 ID、AUC(<60) 與信賴區間），沒有時為 null | | |
| `POST /api/egfr/comparisons/{exp_id}/start` | — | 排入還沒訓練的成員（202）：CPU 基準先跑，GPU 模型依序進獨占執行池 | `train`、`train_baseline` | ✓ |
| `POST /api/egfr/comparisons/{exp_id}/export` | — | 匯出到 `08_匯出/{日期}_eGFR比較_{比較組}/`：`比較表.csv`、每個完成成員的 `每位病人機率_{輸入}_{k}類_{訓練}.csv`（P-編號、折、真實類別、各類機率、P(eGFR<60)、P(eGFR<30)、預測類別；不含 eGFR 數值）與 `說明.txt`。回傳 `folder` | | ✓ |
| `GET /api/egfr/pairwise` | `a`、`b`（訓練 ID）、`metric`（auc_lt60、auc_lt30、qwk3、qwk） | 病人層級配對 bootstrap（2,000 次）：兩者的值、差異、95% 信賴區間、p 值，以及逐折校正 t 檢定。切分或任務不同、指標不適用（例如 2 類的 AUC(<30)）時回 409 | | |
| `GET /api/egfr/test-readiness` | `experiment_ids`（逗號分隔） | 勾選的比較組能否一起評估固定測試集：切分、是否已鎖定、成員數、未完成的訓練、`missing_inputs`（每個成員的測試影像缺少的遮罩或量測特徵張數）、同切分還沒訓練完的其他比較組、`ready` | | |
| `POST /api/egfr/test` | `{experiment_ids, confirm}`（輸入切分編號） | 一起評估固定測試集（202）：先鎖定這個切分的 eGFR 測試集（只鎖 eGFR），再逐一評估每個成員（CNN 用各折最佳模型平均；基準用各折係數平均），每個成員存一筆測試評估。已鎖定 409 `TEST_LOCKED`；有成員沒完成 409 `RUNS_UNFINISHED`；測試影像缺少遮罩或量測特徵 409 `TEST_INPUTS_MISSING`；確認文字不符 422 `CONFIRM_MISMATCH`；比較組切分不同 409 `SPLIT_MISMATCH` | `evaluate_egfr_test` | ✓ |

### 9.4 其他修改【已實作】

| 方法與路徑 | 修改 |
|---|---|
| `GET /api/training/runs`、`GET /api/models`、`GET /api/experiments` | 必須帶任務參數（訓練清單可改帶 `experiment_id`）；三區不混放（D28） |
| `GET /api/jobs` | 新增 `zone` 篩選：egfr、segmentation、grade、other；每個工作的回應含 `zone`（訓練與測試集評估依訓練或模型的任務決定） |
| `POST /api/features` | `source` 新增 `mask_set`（帶 `mask_set_id`） |
| `GET /api/training/learning-curve` | 參數 `split_id`（預設主切分）：每個完成的分割訓練一點（累積的醫師遮罩張數、OOF Dice、和上一點的差），`plateau`＝連續兩點進步 < 0.01 |
| `POST /api/training/runs/trash` | 勾選的訓練（`{run_ids, reason}`，1–200 個）與它們註冊的模型、分割訓練產生的遮罩組與特徵集移入回收桶，同一組；比較組的成員全部移入時比較組也一起（201，回傳 `group_id`、`runs`、`models`、`mask_sets`、`feature_sets`、`experiments`）。排隊中或訓練中 409 `RUN_ACTIVE`；有臨床上線模型 409 `MODEL_CLINICAL`；其他訓練還用到這些遮罩組或特徵集時 409 `RUN_IN_USE`（請一起勾選）。eGFR 比較組裡被移入回收桶的成員顯示「找不到」；已鎖定的測試集不會解鎖（M2.5 #109） |
| `GET /api/training/runs/{run_id}/oof.csv` | 每位病人（P-編號，同一位病人的影像機率取平均）的 OOF 機率 CSV：折、真實類別、各類機率、P(eGFR<60)、P(eGFR<30)、預測類別；不含 eGFR 數值 |
| `POST /api/models/{model_id}/test`、`GET /api/models/{model_id}/test-readiness` | 測試鎖改成依任務；分割改為每個測試病人側至少 1 張醫師遮罩 |
| `PUT /api/annotation/labels/{image_id}` | `kind=quality` 回 422（影像品質已移除，D25） |

---

## 10. 醫師端【已實作】

程式：`app/api/routes/clinical.py`、`app/clinical/`（`plan`、`models_cache`、`receiver`、`exams`、`analysis`、`workspace`、`reports`、`demo_pack`、`transfer`、`trash`、`home`）。`/api/clinical` 已登記在路由表。設計見 [實作企劃](實作企劃.md) §5、決策 D38–D45。

### 10.1 分析方案與首頁

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/clinical/plan` | — | `options`：三區可選的模型（只有臨床上線、候選，臨床上線排前面）；`current`：目前方案每區的模型與階段、`candidate`（有候選模型）、`candidate_label`、`problems`（例如模型已不能用、④ 需要的分割模型不符、還沒選任何模型）；`loaded`：已預先載入的模型與裝置 | | |
| `POST /api/clinical/warmup` | — | 把分析方案的模型先載入（202）；走醫師端佇列，不排在訓練後面；顯示卡訓練中改用 CPU | `clinical_warmup` | ✓ |
| `GET /api/clinical/overview` | — | 醫師端首頁（B1）：`checks`（分析方案、接收位址、連接埠、最近備份，每項 `ok`、`detail`、`to`）、`counts`（待補資料、版面不符、失敗、AI 完成、分析中、待簽核、草稿、今天收到、是否接收中）、`recent_analyses`、`receiver` | | |

- 設定鍵（`PUT /api/settings`）：`clinical_plan`（`{segmentation, egfr, grade}`，每個是模型 ID 或 null；模型要存在、任務相符、階段是臨床上線或候選，否則 422）、`clinical_receiver_port`（1024–65535，不能是 8000）、`clinical_device_mode`（超音波設備模式；取得 IRB 前開啟回 422，見 §10.6）。
- 被分析方案（或已簽核報告的分析）用到的模型：`POST /api/models/{model_id}/stage` 改成研究或退役、`POST /api/training/runs/trash` 移入回收桶都回 409 `MODEL_IN_USE`。
- `GET /api/overview` 另回 `clinical`（同上 `counts`），通知鈴用來顯示醫師端事件（B2）。

### 10.2 雙機接收（D38）

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/clinical/receiver` | — | `session`（接收中時：`url`、6 位數 `code`、`code_expires_at`、憑證 `fingerprint`）、`interfaces`（私人網段 IPv4）、`suggested`（只有一個時自動選）、`port`、最近 30 次傳送 `batches`（每張的狀態統計）、`firewall_hint` | | |
| `POST /api/clinical/receiver/start` | `{address?}` | 在選定的網路介面啟動上傳小程式（HTTPS 自簽憑證、只綁這個 IP）並預先載入模型。已在接收回 409 `RECEIVER_ACTIVE`；位址不是這台電腦的私人網段回 422 `BAD_INTERFACE`；多個介面沒選回 422 `CHOOSE_INTERFACE`；連接埠被占用回 409 `PORT_IN_USE` | `clinical_warmup` | ✓ |
| `POST /api/clinical/receiver/stop` | — | 停止接收；配對失效、刪除私鑰 | | ✓ |
| `POST /api/clinical/receiver/code` | — | 換一個配對碼（10 分鐘有效；錯誤次數歸零） | | |
| `GET /api/clinical/receiver/batches/{batch_id}/summary` | — | 下載傳送摘要 JSON（B10）：每張的序號、狀態、SHA-256、大小、耗時；不含檔名與個資 | | |
| `POST /api/clinical/demo-pack` | `{patients: 1–30}` | 匯出示範影像包（D43）到 `08_匯出/示範影像包_{時間}/`：主要切分測試集病人、每側 1 張去識別化影像，加 `示範清單.json`（檔名、病例代碼 DEMO-nn、側別、像素間距、年齡、性別、糖尿病；不含 eGFR）。測試集沒有合適病人回 409 `NO_DEMO_IMAGES` | | ✓ |

**上傳小程式**（不在 `/api` 下，另一個連接埠 `https://{IP}:{clinical_receiver_port}`，只有下列路徑；不讀主網站的 Cookie）：

| 方法與路徑 | 說明 |
|---|---|
| `GET /` | A 電腦的傳送頁（配對、匯入示範清單、手動填病例代碼與臨床資料、拖放、重送失敗的影像） |
| `POST /pair` | 標頭 `X-Pair-Code`；回 `{token}`。錯誤回 401 `BAD_CODE`（剩幾次）、過期 401 `CODE_EXPIRED`；同一來源錯 5 次 429 `TOO_MANY_ATTEMPTS` |
| `POST /batches` | `Authorization: Bearer`；`{case_code?, age?, sex?, diabetes?, title?, demo?}`；建立一次傳送＝一筆檢查 |
| `PUT /batches/{id}/items/{seq}` | 影像本體串流（上限 32 MB、只收 PNG／JPEG）；標頭 `X-SHA256`（不符 422 `HASH_MISMATCH`）、示範影像加 `X-Demo`、`X-Side`、`X-Spacing`；同一次傳送內重複的回 `duplicate` |
| `POST /batches/{id}/finish` | 傳送完成，排入收圖與去識別化，完成後自動分析 |
| `GET /batches/{id}` | 這次傳送的摘要 |

### 10.3 工作清單與檢查工作區

| 方法與路徑 | 參數／內容 | 回傳與說明 | 背景工作 | 稽核 |
|---|---|---|---|---|
| `GET /api/clinical/exams` | `status`（逗號分隔）、`q`、`date_from`、`date_to` | 工作清單：病例代碼、狀態、影像數、候選標示、eGFR P(<60)、左右腎長、缺的臨床資料、報告狀態 | | |
| `GET /api/clinical/exams/{exam_id}` | — | 檢查工作區：病人（超音波模式才有姓名、病歷號）、臨床資料、影像（去識別化缺項）、最新分析（模型、步驟、結果）、分析紀錄、修改紀錄、報告、前次檢查比較（B3） | | |
| `GET /api/clinical/images/{image_id}/{kind}` | `kind`：model、thumb | 去識別化影像或縮圖；版面不符、有殘留的影像回 403 `IMAGE_NOT_SHOWN`；原始檔沒有任何 API | | |
| `GET /api/clinical/analyses/{analysis_id}/overlay/{image_id}` | — | 預測遮罩的半透明疊圖 PNG | | |
| `PATCH /api/clinical/exams/{exam_id}/images/{image_id}` | `{excluded, reason}` 或 `{side}` | 排除（要原因）／還原影像、指定側別；寫修改紀錄並回饋研究端 | | |
| `PATCH /api/clinical/exams/{exam_id}/sides/{side}` | `{length_mm?, grade?}`（null＝改回 AI） | 修改腎長（20–250 mm）、確認或修改分級；寫修改紀錄並回饋研究端 | | |
| `PATCH /api/clinical/exams/{exam_id}/clinical` | `{age, sex, diabetes}` | 補填這次檢查的年齡、性別（男／女轉 M／F）、糖尿病（有／無／不明）；只記在醫師端 | | |
| `POST /api/clinical/exams/{exam_id}/reanalyze` | — | 新增一筆分析（202，舊的分析不變） | `clinical_analysis` | ✓ |
| `POST /api/clinical/exams/{exam_id}/layout` | — | 版面不符：從最接近的範本按比例建立新範本、重新去識別化並分析 | `clinical_analysis` | ✓ |
| `GET /api/clinical/patients` | — | 病例代碼清單、檢查次數、最近一次檢查 | | |
| `GET /api/clinical/patients/{patient_id}` | — | 歷次檢查與趨勢（腎長、分級、eGFR P(<60)、報告） | | |
| `POST /api/clinical/exams/{exam_id}/transfer` | `{patient_id, image_ids?}` | 轉入研究（M3-7）：不重做去識別化；人工指定已存在的 P-編號（否則 422 `PATIENT_REQUIRED`）；研究端新增來源為「醫師端」的批次，影像為待確認；已在研究端的略過 | | ✓ |

已簽核的檢查不能修改（409 `EXAM_SIGNED`），要先在報告「修訂」。

### 10.4 報告（M3-5、D42）

| 方法與路徑 | 參數／內容 | 回傳與說明 | 稽核 |
|---|---|---|---|
| `GET /api/clinical/reports` | `status` | 報告中心清單 | |
| `POST /api/clinical/exams/{exam_id}/report` | — | 建立（或開啟已有的）報告草稿：AI 預填腎長、eGFR（有分級模型時加分級），其他欄位醫師手填。分析未完成回 409 `ANALYSIS_NOT_READY` | ✓ |
| `GET /api/clinical/reports/{report_id}` | — | 報告內容、版本歷史、簽核前檢查清單（B9）、使用的模型、PDF 狀態 | |
| `GET /api/clinical/reports/{report_id}/versions/{version}` | — | 某一版的內容（版本存在資料庫，不能修改） | |
| `PUT /api/clinical/reports/{report_id}` | `{payload, submit}` | 儲存成新的版本；`submit=true` 改為待簽核。已簽核或作廢回 409 `REPORT_LOCKED` | ✓（送簽核） |
| `POST /api/clinical/reports/{report_id}/sign` | `{physician, confirm_name, acknowledged}` | 簽核：判讀醫師要在醫師名單（422 `PHYSICIAN_REQUIRED`）、輸入姓名確認（422 `CONFIRM_MISMATCH`）、勾選檢查清單每一項（422 `CHECKLIST_REQUIRED`）；同時產生 PDF | ✓ |
| `POST /api/clinical/reports/{report_id}/revise` | — | 已簽核的報告修訂成新的草稿版本 | ✓ |
| `POST /api/clinical/reports/{report_id}/void` | `{reason}` | 作廢（原因必填）；PDF 覆蓋成作廢版 | ✓ |
| `POST /api/clinical/reports/{report_id}/pdf` | — | 產生 PDF，覆蓋 `05_醫師端/03_報告/{病例代碼}_{檢查}/報告.pdf`（資料夾只保留最新一份），記錄雜湊 | ✓ |
| `GET /api/clinical/reports/{report_id}/pdf` | `download` | 開啟或下載 PDF；檔案被外部修改或移動回 409 `PDF_CHANGED` | |

### 10.5 背景工作

| 工作 | 說明 |
|---|---|
| `clinical_warmup` | 預先載入分析方案的模型 |
| `clinical_receive` | 一次傳送：原始檔存受限區 `01_原始`、去識別化（強制殘留檢查）、建立影像，完成後自動排入分析 |
| `clinical_analysis` | 分割與量測、eGFR（整次檢查整合）、回音分級；每一步各自成功或失敗；缺臨床資料時影像＋臨床模型略過（檢查變「待補資料」） |

三者都走醫師端佇列（不排在訓練後面）。結束後只更新醫師端索引 `09_索引/醫師端檢查.csv`，不重建研究索引。

### 10.6 超音波設備模式（階段 F：只完成基礎）

資料表已有姓名、病歷號欄位（只在超音波模式寫入，只在醫師端的回應出現，不進索引、回饋與 PDF 以外的地方）；設定鍵 `clinical_device_mode` 已存在但開啟回 422。要等 IRB 同意、醫院資訊單位核准，並確認設備傳輸方式（DICOM 或資料夾）後才實作接收端點。

---

## 11. 已取消或改名的端點【已取消】

| 舊文件寫的 | 實際作法 |
|---|---|
| `POST /backups/daily`、`POST /backups/restore-preview` | 只有 `POST /api/backups/snapshot`；還原由人工操作（見系統架構 §8） |
| `GET /images/{id}/thumbnail` | `GET /api/images/{image_id}/file?kind=thumb` |
| `/layout-templates/*`、`POST …/test` | `/api/templates/*`、`POST …/preview`；範本由匯入時自動建立，不另外新增 |
| `GET/PATCH /patients/{id}` | 病人資料由病人表與人工確認流程修改 |
| `GET /splits/{id}/leakage-check` | `GET /api/splits/{split_id}/leakage` |
| `GET /dataset-versions/{id}` | 版本內容在 `05_資料集版本/{id}/manifest.json` |
| `/annotation/tasks/{id}/next`、`/annotations/{image_id}/{type}`、`/annotations/{id}/review` | 佇列、狀態、遮罩、分級、標籤、草稿確認等端點（§6） |
| `POST /feedback/{id}/accept`、`/reject` | `POST /api/feedback/{item_id}/{decision}` |
| `GET /pipelines`、`POST /pipelines/{id}/stop` | 流程是背景工作，用 `/api/jobs` 查詢與停止 |
| `POST /features/extract` | `POST /api/features` |
| `/training/preflight`、`/training/{id}/events|metrics|stop|resume|artifacts` | `/api/training/runs/*`；停止與恢復用 `/api/jobs/*`；歷程在訓練詳細 |
| `PATCH /models/{id}`、`/models/{id}/card`、`/models/{id}/download` | 模型卡包含在 `GET /api/models/{model_id}`；模型檔在 `04_模型/02_模型庫` |
| `/evaluations/preflight`、`POST /evaluations`、`/evaluations/{id}/*` | 交叉驗證評估在訓練、測試集評估在模型（§7） |
| `POST /analysis` | `POST /api/pipelines` 帶 `image_ids` |
| `GET /events`（SSE 變更通知） | 前端每 10 秒輪詢 `GET /api/overview` |
| 影像品質標註、品質模型 | M2.5 移除（決策 D25） |
