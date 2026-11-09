# 腎超工作台：前端

> 最後更新：2026-10-29。接手請先讀 [01_計畫與文件/README.md](../../01_計畫與文件/README.md)；逐頁規格見[網頁規格](../../01_計畫與文件/網頁規格.md)。

React 18.3 + TypeScript 5.7 + Vite 6 + Tailwind CSS 3 + recharts 2.15 + lucide-react；套件管理用 pnpm。

- **研究工作台**與**共用頁面**（任務紀錄、回收桶、設定）已接上後端 API。
- **臨床工作台**（`/clinical/*`）仍使用 `src/mock/clinical.ts` 的示範資料，M3 才接上；這些頁面上方會顯示示範提示列。
- **不需要登入**（決策 D12（改））：開啟網頁時自動建立本機工作階段，右上角選操作者。

## 啟動

平常使用不需要另外啟動前端：根目錄的 `start.bat` 會啟動後端，後端直接提供建置好的 `dist/`。

開發時：

```bash
pnpm install
pnpm dev
```

開啟 http://localhost:5173 。API 會轉到 `127.0.0.1:8000`，所以要先用 `start.bat`（或 `02_程式碼/scripts/run_server.py`）啟動後端。

型別檢查與建置：

```bash
pnpm typecheck
pnpm build
```

`pnpm build` 會先做型別檢查，再輸出到 `dist/`。改完前端要重新建置，`start.bat` 才會用到新版本。

## 頁面（35 個頁面路徑）

| 區域 | 頁面 |
|---|---|
| 臨床（示範資料） | 工作清單、檢查工作區、報告編輯器、影像接收、病人與檢查、病人詳細、報告中心 |
| 研究：資料 | 總覽、資料集、影像詳細、匯入報表、標註與回饋（含醫師圈選分頁）、標註編輯器 |
| 研究：eGFR 預測 | eGFR 訓練（勾選式比較組）、eGFR 比較清單、eGFR 比較頁、eGFR 模型 |
| 研究：分割 | 分割訓練（含學習曲線、實驗、nnU-Net）、遮罩組、分割模型 |
| 研究：回音分級 | 回音分級訓練（含實驗）、特徵擷取、回音分級模型 |
| 研究：三區共用 | 訓練詳細、實驗詳細、模型詳細（「返回」回到所屬的區） |
| 研究：流程與分析 | 流程執行、影像處理與遮罩、版面範本編輯、AI 分析 |
| 共用 | 任務紀錄（依區分頁）、回收桶、設定（含主切分、顏色對照、資料夾與索引） |

另有 `/` 導向 `/research`、舊網址 `/research/training`、`/research/experiments`、`/research/models` 導向對應的區，以及找不到頁面。三區分開的規則（決策 D28）：每頁只向後端要該任務的清單，任何清單都不混放；見網頁規格 §1。

**新增頁面時**：在 `src/App.tsx` 加路由、在 `src/layouts/navigation.ts` 加側邊欄項目，並在[網頁規格](../../01_計畫與文件/網頁規格.md) §1 的表格加一列（後端的文件檢查測試會比對 `App.tsx` 的路徑）。

## 結構

| 位置 | 內容 |
|---|---|
| `src/App.tsx` | 路由 |
| `src/layouts/` | `AppShell.tsx`（頂部列、通知、操作者選單、離線提示、示範提示列）、`navigation.ts`（側邊欄） |
| `src/auth/operator.tsx` | 目前的操作者（存在 localStorage `kidney-operator`），以 `X-Operator` 標頭送給後端 |
| `src/api/client.ts` | 呼叫後端：自動建立工作階段、帶 CSRF token 與操作者標頭、統一錯誤格式 |
| `src/api/hooks.ts` | `useApi`（讀取）、`useAction`（寫入，含 busy 與錯誤狀態）、`usePolling` |
| `src/api/types.ts`、`src/api/ml.ts`、`src/api/models.ts` | 型別；任務名稱、狀態標籤、分數名稱、數字格式 `fmt`、各區首頁 `zoneHome`；三區模型清單 `useAllModels`（流程、AI 分析的模型選單） |
| `src/pages/research/` | 研究工作台各頁；`datasets/` 是資料集的分頁元件。M2.5 新增：`PhysicianCircling.tsx`（醫師圈選）、`EgfrTraining.tsx`（勾選式比較組）、`EgfrCompare.tsx`（比較頁、兩兩比較、固定測試集；`EgfrCompareIndex` 清單）、`MaskSets.tsx`（遮罩組）、`LearningCurve.tsx`（分割學習曲線）；`Training.tsx`、`Registry.tsx`、`Experiments.tsx` 改成帶 `task` 參數 |
| `src/pages/clinical/` | 醫師端（示範資料） |
| `src/pages/shared/` | 任務紀錄、回收桶、設定；`ColorMapping.tsx` 是設定頁的顏色對照分頁 |
| `src/components/ui.tsx` | 基本元件：PageHeader、Panel、Button、Pill、EmptyState、Tabs、Table、Field、KeyValue、Figure、AiBadge、ProgressBar、Timeline、BackLink |
| `src/components/live.tsx` | `JobProgress`（輪詢背景工作）、`ErrorNote`、`Loading` |
| `src/components/overlays.tsx` | `ConfirmDialog`（可要求輸入確認文字）、`Drawer` |
| `src/components/charts.tsx` | `LineChartPanel`、`ConfusionMatrix` |
| `src/components/EvaluationReport.tsx` | 評估報告表格（影像、病人層級，信賴區間） |
| `src/components/AnnotationCanvas.tsx`、`MaskOverlay.tsx` | 標註畫布、遮罩疊圖（構造顏色在這裡定義） |
| `src/components/GradeScale.tsx`、`ImageGrid.tsx`、`UltrasoundSketch.tsx` | 回音分級色塊、縮圖格、檢視器示意圖 |
| `src/components/OpenFolder.tsx` | `OpenFolderButton`：請後端在檔案總管開啟資料夾（只限專案內、非受限區） |
| `src/components/PretrainedPanel.tsx` | 預訓練權重面板（分割、回音分級訓練頁共用） |
| `src/mock/clinical.ts`、`system.ts` | 醫師端示範資料（仍在使用） |

`src/mock/research.ts`、`training-demo.ts`（Phase 0 的示範資料，已沒有頁面引用）在 M2.5 刪除。

## 注意

- 介面只顯示去識別化後的影像（`GET /api/images/{image_id}/file`），永遠不顯示原始影像。
- 標註畫面不顯示 eGFR 與臨床資料（盲測）。
- 錯誤訊息直接顯示後端的中文訊息（`ErrorNote`）。
- 沒有前端自動測試；以 `pnpm typecheck`、`pnpm build` 與瀏覽器操作驗證。
