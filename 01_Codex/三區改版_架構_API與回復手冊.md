# 三區改版：架構、API、遷移與回復

更新：2026-10-13（接收位址、醫師端預設方案、傳輸協定 2、遷移 0011；詳見 [改版說明](20261013_接收位址_預設方案_案例資料改版.md)）。最新狀態見 `驗證報告/20261013-transfer-cases/STATUS.md`。本文件不是臨床適用性或海報成績證明。

## 唯一程式與資料位置

工作區根目錄為 `<專案根目錄>`，唯一主程式是 `02_主程式碼`。根目錄 `start.bat` 轉交該程式；三個區域共用一個 loopback 後端、研究資料庫、醫師資料庫及運算資源協調器。

`workspace-layout.json` 集中設定研究資料、模型、參考特徵、醫師資料、PDF 與 runtime 的位置。不要靠搬資料或改資料庫路徑欄位來解決啟動錯誤。外部「照片」與歸檔程式不是這次寫入目標。

| 邏輯區 | 位置與責任 |
|---|---|
| 01_Codex | 說明、測試 XML、數值比對、截圖、隔離驗收證據 |
| 02_主程式碼 | API、前端、遷移、啟動器與離線維護工具 |
| 03_模型與影像資料 | 研究 DB／影像／工作、權重、醫師 DB／原圖／不可變分析、runtime |
| 04_醫師報告 | 受管理 PDF 與雜湊；報告內容版本仍在醫師 DB |

## 導覽與相容網址

| 現行入口 | 內容 | 舊入口 |
|---|---|---|
| `/research` | 研究首頁、資料與研究處理流程 | `/`、舊登入／區域選擇入口 |
| `/research/training` | 訓練設定 | `/training` |
| `/research/inference` | AI 推論 | `/inference` |
| `/research/ai-judgment` | AI 判斷，MLP／OnlyIMG | `/ai-judgment` |
| `/model-center/training/:jobId` | 訓練監控 | `/training/:jobId`，`/training/monitor` 導至監控列表 |
| `/model-center/models/:modelId` | 模型列表／詳情 | `/models/:modelId`、`/research/models/:modelId` |
| `/model-center/evaluations/:evaluationId` | 手動模型評估、逐筆與匯出 | 新入口 |
| `/model-center/clinical-plans` | 醫師封存分析方案 | `/admin/clinical` |
| `/clinical/monitor` | 紀錄、作業與生命週期 | 新入口 |

转址保留 query 與 hash。切區不另外啟動模型服務。接收狀態顯示在共用頁首；相機頁離開則停止媒體來源及抽樣。記憶體快取不儲存病例到 localStorage，跨案例立即隔離。

研究／模型資料讀取採「先顯示已有資料、背景更新」。共用頁首顯示目前頁面已顯示快取的最早成功讀取時間，不是資料庫修改時間，也不保證所有資料同時更新。失效或更新失敗不把這個時間改成現在；保留內容並顯示錯誤與「重試資料更新」。離頁移除訂閱，三區頁首只建立一份研究事件訂閱。醫師監控另顯示其摘要資料時間與更新狀態；病例資料仍採獨立記憶體查詢，不混入研究快取。

## 本機安全邊界

主應用只允許 loopback 綁定，檢查實際連線、Host、Origin、Fetch Metadata；不把代理標頭當作來源證據。同源開發 proxy 不擴大 CORS。舊帳密 API 回 410，舊 cookie 不授權。

瀏覽器先取得短效一次性挑戰，再用 JSON、自訂初始化標頭建立八小時本機會話。Cookie 為 HttpOnly／SameSite Strict，HTTPS 時 Secure。CSRF token 只在記憶體，寫入需權限能力及 token。安全讀取會話失效可重新初始化後重試一次；寫入不自動重送。

local_system actor 只供稽核外鍵，不是管理員或已驗證醫師。歷史 users、sessions、作者不改寫。判讀醫師仍人工填寫。雙機接收使用獨立 TLS 程序、指紋及限權 bearer，沒有研究／病人／模型管理 API。

## API 契約索引

下列均在 `/api` 下，實際型別以後端 Pydantic 及前端 interface 為準。沒有路徑參數可以任意讀取本機檔案。

| 範圍 | 主要操作與必要契約 |
|---|---|
| `/local-session/challenge`、`/local-session` | 挑戰 GET、初始化 POST、查詢 GET、撤銷 DELETE；kind、capabilities、expires_at、CSRF |
| `/models`、`/models/{id}` | 搜尋／篩選／offset／limit、total；有序 class_names、class_count、train_stats、source、references、evaluation_summary |
| `/evaluations/preflight` → `/evaluations` | 預檢回傳指紋，建立須 expected_preflight_sha256；綁定 model、資料／輸入版本、split、device、來源確認 |
| `/evaluations/{id}` | 詳情、predictions 分頁、stop、retry、compare/{other_id}、export JSON／CSV |
| `/evaluations/reference-masks/preflight` → `/reference-masks` | 獨立 Mask 的來源聲明、尺寸、座標與 SHA；不可將模型自產 Mask 當自己的答案 |
| `/clinical/monitor/{section}` | 每頁預設 50、精確 total、search、status、kind、日期、lifecycle、exact_id；只傳摘要 |
| `/clinical/lifecycle/{entity}/{id}` | GET 預檢；POST action、expected_revision、reason；提交重查引用／父層／進行中作業，衝突 409 |
| `/clinical/monitor/operations/{id}/retry` | 同影像、同方案及目前基本資料建立新作業；保留 retry_of，不覆寫 |
| `/clinical/monitor/cleanup/{id}/retry` | 明確理由與確認後重試精確暫存目錄，保留嘗試紀錄 |
| `/clinical/frames/{id}/analyses/history` | 分析 run 歷史；版本化产物 `/clinical/analyses/{run}/{artifact}` 驗證 SHA |
| `/clinical/preview`、`/preview/release` | 明確 operation_id，租用綁定會話／操作；取消前未開始的不運算，已開始的退出後才釋放運算鎖 |
| `/clinical/reports/{id}/versions` | expected_version 防衝突；保存不可變內容與明確分析 run；確認需判讀醫師與缺項承認 |
| `/clinical/reports/{id}/versions/{n}/pdf` | GET 僅讀取、POST 明確生成／重建；不隱性生成 |
| `/clinical/pdf-artifacts/{id}` | GET 受管理產物；DELETE expected_sha256、reason；已刪 URL 回 410，不重生 |
| `/clinical/default-plans` | GET 兩個來源（`network_demo`／`capture`）的目前預設、可分析狀態、問題與設定歷史；POST 需 `models.manage`：source、mode（plan／preview_only）、plan_id、evidence。只新增不修改 |
| `/clinical/receiver-settings`、`/receiver-settings/validate` | GET 本機網卡（名稱、IP、連線狀態、類型）、建議位址、上次設定與重新驗證結果；POST 驗證 host／port |
| `/clinical/demo-sessions` | POST 必須含 `analysis`：`{mode:'default'}`／`{mode:'preview_only'}`／`{mode:'plan',plan_id}`，另含 host、port、address_mode；恢復用 session_id 且不可帶 analysis。建立時鎖定方案 |
| `/clinical/exams/{id}/case` | PUT `expected_revision`：title、side、age、diabetes（yes／no／unknown）、exam_name、exam_time、notes；示範案例另含 patient_ref／patient_name。寫入新案例資料版本，待補資料的接收項目自動續跑一次 |
| `/clinical/exams/{id}` | GET 另含 diabetes_status、transfer（會話鎖定方案、狀態、缺項）、versions（案例資料版本） |
| 接收程序（區網）`/batches` | 協定 2：`{protocol:2, case_schema:1, id, items:[{id, sha256, case, case_sha256}]}`；協定不符回 426 |

舊病人／檢查／報告列表 API 保留相容；新介面使用監控分頁與指定 ID 查詢，不依賴舊固定上限。模型及相關引用建立使用同一主服務內的寫入協調，離線維護工具必須停服。

## 模型來源與數值

三種資料分開：訓練 history、指定 checkpoint 評估、单張模型機率。新訓練完成後只補來源記錄，不改 loss、optimizer、scheduler、資料切分、最低 validation loss 選模或隨機序列。

checkpoint sidecar 核對輸入樣本／split／標籤、weight、manifest、history、metrics 雜湊；最佳 epoch 與最後 epoch、被選 fold 與 k-fold 平均分開。舊模型沒有證據時維持「來源未核實」，不靠檔名填成績，也不為補紀錄重訓。

評估紀錄與逐筆預測不可覆寫。只有相同任務、class schema、實際樣本與標籤、輸入處理及指標定義才能比較；部分完成沒有完整成績。無法排除訓練重疊就明示未知。單張輸出不稱為準確率。

原圖／權重不變。二分類單 logit sigmoid 且 `>0.5`，三／五分類按原有序類別；各用自己的權重與 train_stats。全量一致性是相同 CPU 輸入前後比較，並非新測試集準確率。原始海報依然「尚未驗證重現」。

## 遷移與正式維護

研究鏈是獨立 `research_0001` 基線核對、`research_0002` 評估；醫師沿原 Alembic 0001–0011，新增本機 actor／session、作業、生命週期、分析版本、PDF、清理／確認、預覽紀錄，以及 0011 的醫師端預設方案、案例資料版本、接收設定與協定 2 欄位（只新增，主程式啟動時自動套用）。既有 DB 不盲目 stamp，不做破壞歷史的 downgrade。

先停止寫入工作與接收，再停止本專案。不要按程序名稱批次結束所有 Python。維護工具也會檢查主服務／子程序仍在時拒絕操作。

在 `02_主程式碼` 的 PowerShell 中，使用全新備份名：

```powershell
.\.venv\Scripts\python.exe scripts\workspace_backup.py backup "..\.maintenance\backups\<新的資料備份名>" --scope full
.\.venv\Scripts\python.exe scripts\workspace_backup.py verify "..\.maintenance\backups\<新的資料備份名>"
.\.venv\Scripts\python.exe scripts\snapshot_current_code.py "..\.maintenance\backups\<新的程式備份名>"
```

資料備份包括五個邏輯根及兩個 SQLite 已提交 WAL 內容；程式備份含 source-manifest、建置產物與根設定／啟動器，不含可重建的 node_modules、venv、快取。備份內可能含敏感資料，應保持本機存取限制，不上傳公開位置。

先以全新隔離目錄完成回復、重複升級及雜湊核對，再使用明確 `--apply` 的 `scripts/upgrade_three_zones.py`。它要求全量資料備份與現在資料逐檔／逐表一致，並驗證程式備份。成功只代表 DB 升級完成，不代替啟動、頁面及重啟驗收。

### 升級／回復失敗

`maintenance-operation.json` 阻擋其他啟動；`schema-upgrade-journal.json` 在升級未完成時持續阻擋正常啟動。不要刪掉標記假裝完成。先查看 owner 是否仍在、phase、備份與 evidence，保留失敗現場，核對兩個 DB 的版本與完整性。

回復前另存升級後的新資料與目前程式，避免回復舊版造成新增紀錄遺失。停服後使用已驗證的成套資料備份：

```powershell
.\.venv\Scripts\python.exe scripts\workspace_backup.py restore "..\.maintenance\backups\<已驗證的成套資料備份名>"
```

工具以 journal 分段發布各資料根，原根改名保留 `.before-restore-<識別碼>`，不就地混合新舊檔案。中斷執行 `workspace_backup.py recover`，必須仍使用同一設定與路徑；原 owner 仍在時拒絕清锁。失敗產物保留供查驗。

程式／設定須與所選資料世代成套回復：先將目前 `02_主程式碼` 保存到明確的新備份位置，再核對 source-manifest 後從配對的程式快照還原，不在兩份版本間零散覆蓋。不要從歸檔程式啟動後指向新 DB。`schema-upgrade-journal.json` 不會因恢復 DB 自動消失；確認成套程式、版本、完整性、引用及產物後，將該紀錄移到驗收證據保存，才可重新啟動。不能在未核對前移除它。

第一次啟動應核對實際 `runtime/run/server.json` 的 project_root、URL 及程序身分，三區深層路由、資料／模型數量、受保護 API、本機初始化、舊 cookie 停用。重啟後新會話重建，接收不自動開網路，PDF tombstone 及報告版本應仍在。

本機目前不保留任何歷史備份（2026-10-13 依指示清除）；以上指令需要時用來建立**新的**備份。成套還原驗證請用 `scripts/verify_three_zone_restore.py --output <暫存資料夾> --summary <摘要> --discard`，完整副本不放 01_Codex。

## 驗收界線

10/11 的測試結果、v2 合成 PDF、975 張一致性與成套回復結論只保留摘要於 `驗證報告/20261008-three-zones`；10/13 改版證據在 `驗證報告/20261013-transfer-cases`。

同機 HTTPS、合成相機與 CPU 驗收，只證明軟體流程。第二台 Windows、實際超音波／擷取卡、CUDA 裝置及醫療適用性須另外驗證。現階段不宣稱醫療系統已完成，也不將一般軟體測試通過等同臨床安全或診斷效能。
