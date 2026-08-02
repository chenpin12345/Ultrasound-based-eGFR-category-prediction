# ISU AI KUA 腎功能影像研究平台

這是一套在 Windows 本機執行的繁體中文 Web 應用程式，整合資料集管理、影像前處理、UNet 遮罩、特徵擷取、五類 eGFR 模型訓練、即時監控、模型管理與批次推論。

> 本系統僅供研究使用，不構成醫療診斷，也不可替代專業醫療人員的判斷。

所有圖片、metadata、模型與結果預設只保存在本機。系統不含第三方追蹤、不會自動上傳資料，也不需要雲端服務才能使用核心功能。

## 最快開始方式

第一次使用：

1. 安裝 64-bit Python 3.11 或 3.12。
2. 安裝 Node.js 20.19 以上版本。
3. 雙擊 `setup.bat`。
4. 安裝完成後雙擊 `start.bat`。
5. 瀏覽器會自動開啟本機網址，例如 `http://127.0.0.1:8000`。

日常使用只需雙擊 `start.bat`。結束時雙擊 `stop.bat`；它會核對 PID、程序建立時間及專案命令列，只停止本專案服務。

## 系統需求

- Windows 10/11 64-bit。
- Python 3.11 或 3.12 64-bit。
- Node.js 20.19+；Node.js 22 LTS 亦可。
- CPU 模式不需要 NVIDIA GPU。
- CUDA 模式需有相容 NVIDIA 驅動；安裝前先確認要使用的 PyTorch CUDA wheel。
- 建議至少 16 GB RAM。EfficientNetB3、較大 batch 或大型 ZIP 需要更多記憶體與磁碟空間。

## CPU 與 CUDA 安裝

`setup.bat` 預設安裝 PyTorch CPU wheel，適用所有電腦：

```bat
setup.bat
```

若要使用 CUDA 12.4，可先在命令提示字元設定：

```bat
set ISU_TORCH_VARIANT=cu124
setup.bat
```

CUDA 12.6：

```bat
set ISU_TORCH_VARIANT=cu126
setup.bat
```

CPU 模式相容性最高，但訓練速度較慢。CUDA 模式可大幅加速 CNN 訓練與推論；若發生 GPU OOM，系統會保留錯誤、釋放快取並提示降低 batch size。GPU 訓練預設同時只執行一個，其餘工作排隊。

## 網站頁面

- 儀表板：資料集、工作、訓練及模型概況。
- 資料集管理：圖片/ZIP/metadata/mask 匯入、摘要、分類分布、縮圖、缺漏篩選、拒絕紀錄與刪除。
- 影像處理：convert、crop、RB、assort 的自選步驟與順序。
- 遮罩產生：選擇 UNet 模型並批次產生 `IMG_Mask`，完成後成對預覽原圖與 mask。
- 特徵擷取：輸出相容的 UTF-8 BOM Feature CSV。
- 模型訓練：快速模式與進階模式。
- 訓練監控：SSE 即時 epoch、loss、accuracy、資源與日誌。
- AI 推論：單張/批次預測、全部分類機率、CSV 與 ZIP。
- 模型管理：匯入、重新命名、啟用、下載、刪除及檢視模型資訊。
- 歷史工作：重新整理後仍可查看持久化工作及結果。
- 系統設定：本機資源、上傳限制及工作設定。

桌面版使用左側導覽列；手機版改為可收合選單。表格在小螢幕可橫向捲動或轉為卡片。

## 匯入資料集

資料集管理頁支援：

- 多張 JPG/JPEG/PNG/JFIF 圖片。
- 包含圖片的 ZIP。
- 選配 metadata CSV。
- 選配 mask 圖片；可分開選取，或置於 ZIP 的 `IMG_Mask`、`mask`、`masks` 資料夾。

瀏覽器只上傳使用者選取的檔案，不接受任意伺服器絕對路徑。後端會為每個檔案建立隨機內部名稱、驗證真實圖片格式、計算 SHA-256、產生縮圖並記錄重複狀態。損壞影像不保留原始內容，但會在 SQLite 留下安全檔名、錯誤碼、大小與雜湊，讓使用者可在「匯入拒絕紀錄」查看。Mask 只會在檔名配對唯一時連結至樣本。

### 分類來源

優先順序如下：

1. ZIP 或上傳相對路徑中的既有分類資料夾。
2. metadata 的 `eGFR`、`egfr`、`matched_eGFR` 或 `matched_egfr`。
3. 舊版檔名開頭的 eGFR，例如 `97.8_1.jpg`。

固定五類索引不可變更：

| 模型索引 | 介面顯示 | 相容舊資料夾名稱 |
|---:|---|---|
| 0 | eGFR < 15 | `eGFR -15` |
| 1 | eGFR 15–29 | `eGFR 15-29` |
| 2 | eGFR 30–59 | `eGFR 30-59` |
| 3 | eGFR 60–89 | `eGFR 60-89` |
| 4 | eGFR ≥ 90 | `eGFR 90-` |

metadata 至少應包含 `image_name`，其餘可用欄位包含 `age`、`gender`、`Length_px`、`Entropy`、`Contrast_Ratio`、`has_diabetes` 及 eGFR 欄位。

### 資料分割

- 預設 train/validation/test 比例為 70/20/10。
- 使用固定 random seed 與分層切割。
- 支援真正的 K-fold cross-validation；每個 fold 使用獨立模型、optimizer、scheduler、checkpoint 與 seed。
- 同一 SHA-256 圖片不會跨分割。
- 開始訓練前會顯示缺標籤、缺 metadata、重複、損壞與類別不平衡警告。

K-fold 模式會固定保留原 test split 作為共享 holdout，並在原 train + validation pool 中輪替 validation fold。完成後保存每個 fold 的指標、mean/std/min/max 聚合結果，選取 validation loss 最低的 fold 作為根目錄最佳模型。停止及服務中斷時會記錄目前 fold；恢復後跳過已完成 folds，從作用中 fold 的 checkpoint 接續。

## 影像處理相容性

一般工作會先把來源複製到獨立工作目錄，不會修改使用者原圖。

- `convert`：JFIF 轉為品質 95 的 JPG；只刪除工作副本中的 JFIF。
- `crop`：先 resize 成 1600×1200，再由 `(235, 90)` 裁成 1024×1024。
- `rb`：保留原有彩色/白色遮罩、inpaint 與固定黑化區域。
- `assort`：依分類建立資料分割輸出。

若 RB 前沒有 crop，或 assort 前沒有 crop/RB，介面會顯示既有順序警告。每個步驟可使用前一步輸出，也可指定同一工作中的不同輸入來源。

## UNet 遮罩

UNet 相容契約：

- 3-channel RGB。
- 512×512 resize。
- ImageNet mean/std normalization。
- 2 個 pixel classes。
- `base_c=32`、bilinear upsampling。
- argmax 後保留最大連通區並沿用既有形態學修整。

外部 `.pth` 可以是裸 `state_dict`，或在 `state_dict`、`model_state_dict`、`model` 下的權重字典。沒有安裝 UNet 模型時網站仍可啟動，頁面會顯示「尚未安裝模型」。

遮罩工作完成後，頁面會以原圖／mask 成對顯示，並可下載 ZIP。預覽 API 只提供該 job 工作目錄內、已通過實際解碼驗證的 JPEG/PNG；非影像、絕對路徑與路徑穿越會被拒絕。

## Feature CSV

固定欄位及順序如下：

```text
image_name,age,gender,Length_px,Entropy,Contrast_Ratio,has_diabetes
```

輸出使用 UTF-8 BOM。特徵包含最大元件 major-axis length、GLCM entropy，以及 ROI/背景環帶 contrast ratio。缺少 mask 或 metadata 的檔案會保留在結果摘要中，不會被靜默忽略。

MLP 模型實際輸入順序固定為：

```text
age,Length_px,Contrast_Ratio,has_diabetes
```

`gender` 與 `Entropy` 為 CSV/研究特徵，但不會偷偷加入既有四維 MLP 權重。

## 一鍵訓練

快速模式只需：

1. 選擇資料集。
2. 選擇 ResNet18、MobileNetV2、EfficientNetB3 或 MLP-ResNet18。
3. 選擇 epochs。
4. 點擊「開始訓練」。

進階模式可設定 optimizer、learning rate、weight decay、scheduler、early stopping、patience、random seed、augmentation、class weights、CPU/CUDA、K-fold、checkpoint 間隔及 CORAL 序位分類。

建立請求會立即回傳 `training_job_id`。訓練在背景執行，狀態與指標持續寫入 SQLite；離開頁面或重新整理不會停止訓練。

### 停止與恢復

- 「停止」只設定持久化 stop request。
- worker 在安全的 batch/epoch 邊界停止。
- 停止前原子寫入 `last_checkpoint.pth`。
- 狀態為 `stopped`，不會誤標成 `completed`。
- 「恢復」將同一持久化訓練工作由最近 checkpoint 重新排隊接續。
- 服務重啟時，舊的 `running/stopping` 工作會標成 `interrupted`。

K-fold 訓練亦支援安全停止與恢復。根工作保存作用中 fold、已完成 folds 與目前 checkpoint；不會重跑已完成 fold。

## 訓練產物

每個訓練工作的目錄：

```text
models/{training_job_id}/best_model.pth
models/{training_job_id}/last_checkpoint.pth
models/{training_job_id}/model_metadata.json
models/{training_job_id}/training_config.json
models/{training_job_id}/metrics.json
models/{training_job_id}/history.csv
```

K-fold 另增加：

```text
models/{training_job_id}/kfold_state.json
models/{training_job_id}/folds/fold-1/...
models/{training_job_id}/folds/fold-N/...
```

根目錄 `metrics.json` 會包含各 fold、聚合 mean/std/min/max/count、共用 test holdout 指標及被選為最佳模型的 fold；`history.csv` 增加 fold 與 fold epoch 欄位。

`model_metadata.json` 保存架構、固定類別索引、metadata 順序、train stats、RGB/尺寸/normalization、資料集 ID、建立時間、最佳指標及 CORAL 模式。新模型完成後會自動出現在模型管理頁，可直接啟用並推論。

## AI 推論與快速分析

分類模型固定使用 RGB、224×224 與 ImageNet normalization。支援 ResNet18、MobileNetV2、EfficientNetB3、MLP-ResNet18 及 CORAL 相容權重。

批次結果包含：

- 檔名、預測索引與繁體中文分類。
- 信心分數與五類機率。
- 批次分類統計。
- UTF-8 BOM CSV。
- 含圖片衍生結果與報告的 ZIP。

快速分析工作依序執行預設前處理、預設 UNet、特徵與預設分類模型。若任一預設模型未安裝，工作會回報明確缺少項目，不會使整個網站無法啟動。

## 資料與結果位置

```text
data/isu_ai.sqlite3       SQLite 狀態、事件、指標與設定
data/datasets/            匯入後的資料集、縮圖與已配對 masks
data/jobs/                一般工作的原始副本、暫存、預覽與結果
data/outputs/             可下載輸出
data/training/            訓練工作中間資料
models/                   外部與訓練完成模型
frontend/dist/            React production build
```

所有資料表只保存工作根目錄內的相對路徑。API 回應使用 ID 與下載 URL，不會回傳完整本機路徑或 traceback。

## API

互動式文件：`http://127.0.0.1:<port>/api/docs`

主要路由：

- 系統：`GET /api/health`、`GET /api/system/info`、`GET|PUT /api/settings`
- 資料集：`GET|POST /api/datasets`、detail/samples/issues/summary/delete，以及安全的 sample file/thumbnail/mask
- 一般工作：`GET|POST /api/jobs`、process/masks/features/inference/events/results/download/delete，以及 job 內影像預覽
- 訓練：`GET|POST /api/training/jobs`、events/stop/resume/metrics/artifacts/delete
- 模型：`GET|POST /api/models`、`PATCH /api/models/{id}` 重新命名、detail/activate/download/delete

建立背景工作的 API 使用 HTTP 202。錯誤統一回傳：

```json
{
  "error": {
    "code": "STABLE_ERROR_CODE",
    "message": "可理解的繁體中文訊息",
    "details": {}
  },
  "request_id": "..."
}
```

SSE 支援 `Last-Event-ID`，只傳送新增事件與 heartbeat，不會每次重送完整日誌。

## 安全與隱私

- 服務預設只綁定 `127.0.0.1`。
- `start.bat` 拒絕非 loopback bind。
- 安全化 Windows 保留名稱、控制字元與路徑分隔符。
- 所有檔案解析都限制在設定的 data/models roots。
- ZIP 預檢 entry 數、單檔大小、總解壓大小及 compression ratio。
- 拒絕 ZIP Slip、絕對路徑、drive path 與 symlink。
- 圖片以 Pillow 實際 decode/verify，不只看副檔名。
- 外部 `.pth` 使用 PyTorch `weights_only=True` 驗證，不使用不受信任 pickle fallback。
- 日誌不記錄病患 metadata、完整本機路徑或瀏覽器可見 traceback。
- `.gitignore` 與 `.dockerignore` 排除資料、模型、CSV/XLSX、ZIP、SQLite、工作及輸出。

## 固定相依版本

後端與 ML 套件固定在 `backend/requirements*.txt`；前端固定在 `frontend/package.json` 與 lockfile。關鍵組合為：

- PyTorch 2.6.0 + torchvision 0.21.0。
- FastAPI 0.116.1 + Pydantic 2.11.7 + SQLAlchemy 2.0.41。
- React 18.3.1 + TypeScript 5.7.2 + Vite 6.0.5 + Tailwind CSS 3.4.17。

PyTorch/torchvision 採用[官方配對版本](https://docs.pytorch.org/get-started/previous-versions/)，避免 state-dict 與 torchvision backbone 不相容；FastAPI 固定到已通過本專案測試的版本，避免 0.x 升級造成 schema/Starlette 行為漂移。Vite 的 Node.js 下限依[官方 Vite 指引](https://vite.dev/guide/)，前端使用 pnpm frozen lockfile，設定語意可參考[pnpm 官方文件](https://pnpm.io/settings)。

## 開發與驗證

後端：

```bat
.venv\Scripts\python.exe -m pytest backend\tests -q
```

前端：

```bat
cd frontend
corepack pnpm run lint
corepack pnpm run typecheck
corepack pnpm run test
corepack pnpm run build
```

啟動 API（開發用途）：

```bat
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

一般使用者不需要輸入上述命令；它們只供開發與驗收。

## Docker（選配）

Docker Compose 只將連接埠綁定到本機：

```bat
docker compose up --build
```

本機 `data/` 與 `models/` 會掛載進容器。Windows 一鍵模式仍是主要支援路徑。

## 舊版相容性與已知限制

- 根目錄 `app.py` 保留，沒有刪除。
- 舊權重沒有 manifest 時，匯入者必須明確選擇 task、architecture 與 class count；系統不會冒險猜測。
- 舊 `resnet/trainer.py` 預設二分類，但新版依需求固定訓練五類；二分類裸權重不會被誤載成五類。
- 原始碼包沒有任何 `.pth`，第一次使用模型功能前需匯入可信權重或完成一次訓練。
- 新版提供 UNet 遮罩生成與推論相容性，但分類資料集沒有成對 segmentation ground truth，因此目前不提供 UNet 訓練流程。
- 既有固定 crop/RB 幾何與原始影像設備版面高度相關；對其他設備影像應先用少量樣本驗證。
- SQLite/ThreadPool 適合單機本機使用，不是多機分散式訓練平台。
- CUDA 是否可用取決於 NVIDIA 驅動與所選 wheel；網站會顯示實際偵測結果。

## 本次交付驗收紀錄

- 後端完整測試：`61 passed`。
- TypeScript type-check：通過。
- ESLint：通過，0 warnings。
- 真實隔離端到端：通過；包含 20 張五類合成影像、安全停止與 checkpoint 恢復、CPU MobileNetV2 訓練、模型註冊/啟用、實際推論、2-fold cross-validation、UNet 權重嚴格匯入，以及完整快速分析 CSV/ZIP。
- production build 與前端 8 個 Vitest 測試曾在本次重構中通過；其後一次中斷的離線 pnpm 修復使目前工作副本缺少 esbuild JavaScript wrapper，因此最後一輪無法重跑。新環境執行 `setup.bat` 會依 frozen lockfile 重建前端依賴與 production build。
- 桌面工具安全政策不允許本次驗收啟動背景 GUI/服務程序，所以沒有重跑「實際雙擊」的 start/stop 生命週期；已用 5 個單元測試覆蓋占用連接埠、過期紀錄、瀏覽器 opt-out、遺失程序及 PID 重用身分保護。
- 同一安全政策拒絕 `file://` 與背景服務啟動，未能完成 375×667、768×1024、1440×900 的瀏覽器截圖 QA；響應式來源仍已通過 TypeScript/ESLint，先前 production build 存在於 `frontend/dist`。

## 疑難排解

- `尚未安裝模型`：到模型管理頁匯入可信 `.pth`，或先完成訓練。
- `CUDA unavailable`：改用 CPU，或確認驅動與 `ISU_TORCH_VARIANT`。
- `CUDA out of memory`：降低 batch size，關閉其他 GPU 程式後恢復 checkpoint。
- 前端 build 不存在：重新執行 `setup.bat`。
- 連接埠已使用：`start.bat` 會自動嘗試後續可用連接埠。
- 重複啟動：第二次執行只會開啟既有網址，不會建立第二個服務。
