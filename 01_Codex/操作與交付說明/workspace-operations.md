# 啟動、資料位置、備份與工具

## 日常使用

- 啟動：雙擊根目錄 `start.bat`（PowerShell：`& '<專案根目錄>\start.bat'`），網站為 `http://127.0.0.1:8000`。
- 停止：根目錄 `stop.bat`，只停止本專案驗證過 PID、建立時間及命令列的程序。
- 主站只綁定本機 loopback；雙機接收是獨立 HTTPS 程序（見 [本次改版說明](../20261013_接收位址_預設方案_案例資料改版.md)）。
- 啟動時自動套用資料庫遷移。若 `runtime/maintenance-operation.json`、`runtime/restore-journal.json`、`runtime/schema-upgrade-journal.json` 或 `.maintenance/migration-in-progress.json` 存在會禁止啟動；不得自行刪除標記繞過，先依手冊確認原因。

## A 電腦傳送工具

交付物：`02_主程式碼/delivery/UltrasoundImageSender-portable.zip`（或同目錄的 `UltrasoundImageSender/` 整個資料夾），雜湊與版本見 `delivery/SHA256.json`。重新封裝：

```powershell
& '.\02_主程式碼\scripts\build_image_sender.ps1'
```

腳本會建置、壓縮、從系統暫存位置的獨立解壓副本執行自我測試，並更新 `SHA256.json`。

## 備份與回復

本機已不保留任何歷史備份或還原副本（2026-10-13 依指示清除）。異地或額外備份由使用者自行保存。需要新備份時，先停止本專案服務與接收，再於根目錄執行：

```powershell
& '.\02_主程式碼\.venv\Scripts\python.exe' '.\02_主程式碼\scripts\workspace_backup.py' backup '<新的備份資料夾>' --scope full
& '.\02_主程式碼\.venv\Scripts\python.exe' '.\02_主程式碼\scripts\workspace_backup.py' verify '<新的備份資料夾>'
& '.\02_主程式碼\.venv\Scripts\python.exe' '.\02_主程式碼\scripts\snapshot_current_code.py' '.\.maintenance\backups\<新的程式快照名>'
```

- `full` 含研究資料、模型、參考特徵、醫師 DB／影像／方案與 04 區 PDF；也可用 `research` 或 `clinical`（含 PDF）。目的地必須是新資料夾，不能位於來源內。備份可能含敏感資料，不要放到公開位置。
- 回復與中斷恢復：`workspace_backup.py restore <備份>`、`workspace_backup.py recover`。回復會把原資料保留為 `.before-restore-<id>`，不會就地混合新舊檔案；程式需與資料世代成套回復。詳見 [架構、API 與回復手冊](../三區改版_架構_API與回復手冊.md)。
- 驗證成套備份可還原：`scripts/verify_three_zone_restore.py --backup <資料備份> --code-backup <程式快照> --output <暫存資料夾> --summary <摘要路徑> --discard`。完整還原副本只放暫存資料夾，通過後刪除，不放進 01_Codex。

## 不依賴備份的檢查工具（在 02_主程式碼 執行）

| 工具 | 用途 |
|---|---|
| `scripts/verify_live_integrity.py <out.json> [--compare <before.json>]` | 只讀檢查兩個資料庫完整性、外鍵，以及所有被引用原圖、權重、方案、分析產物、PDF 的存在與雜湊；維護前後比較 |
| `scripts/verify_protected_compute.py` | 受保護數值程式的雜湊清單比對（只證明檔案未變） |
| `scripts/verify_relocation_inference.py --code . --data ..\03_模型與影像資料\research\data --models ..\03_模型與影像資料\research\models --output <暫存> --compare scripts\fixtures\numeric_baseline_1009.json` | CPU 數值回歸：59 個分類權重 × 5 張影像、UNet Mask、特徵與修改前基準比較 |
| `scripts/verify_real_image_transfer.py <圖片資料夾>` | 隔離暫存工作區中的同機 A→B 傳輸（兩張真實影像、兩組案例資料）；不是雙機驗收 |
| `scripts/verify_deployment.py --assert-idle [--output <資料夾>]` | 已啟動的正式站健康、資產、未授權 API、資料數量與醫師資料庫版本 |
| `scripts/cleanup_obsolete.py` | 2026-10-13 一次性清理工具與收據（保留作為紀錄） |

## 維護定位（02_主程式碼 內）

| 功能 | 位置 |
|---|---|
| 三區路由與頁面 | frontend/src/App.tsx、frontend/src/pages、frontend/src/clinical |
| 本機會話與權限 | backend/app/clinical/auth.py、backend/app/main.py |
| A 傳送／B 接收 | tools/image_sender、backend/app/clinical/transfer.py、receiver.py、network.py、cases.py |
| 醫師端預設方案 | backend/app/clinical/defaults.py、frontend/src/clinical/Admin.tsx |
| 推論／前處理 | backend/app/clinical/analysis.py、backend/app/ml、workers、services |
| 病人／案例／方案／報告 | backend/app/clinical/service.py、routes.py、reports.py、report_v2.py |
| 資料庫 | backend/app/db、backend/app/clinical/store.py、clinical/migrations |
| 啟動／封裝／備份 | scripts、build_windows.ps1、app.spec |
| 測試 | backend/tests、frontend/src 中的 *.test.ts(x) |

## 限制

CUDA、第二台實體 Windows、超音波設備需另外實測。Docker 設定僅靜態同步，本機未跑過容器。目錄整理與刪除備份沒有被量測為推論加速。
