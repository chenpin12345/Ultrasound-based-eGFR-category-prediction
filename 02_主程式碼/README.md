# 主程式碼

日常啟動、安裝與停止，請使用上層專案根目錄的 start/setup/stop.bat。
根目錄 README.md 是現行操作入口；01_Codex/INDEX.md 是現行工程文件入口。
原本的工程說明已保留於 01_Codex/歷史紀錄/20261007-before-refactor，不是本次驗收證據。

此區僅維護程式、相依套件、建置設定、測試與交付工具。
研究／醫師資料、權重與 PDF 分别由第三、第四區管理。

後端測試：`.venv\Scripts\python.exe -m pytest backend/tests`。
前端測試／檢查：在 frontend 執行 `pnpm test`、`pnpm typecheck`、`pnpm lint`、`pnpm build`。
套件版本保留 pnpm-lock.yaml 與 backend/requirements-workspace-lock.txt。
遷移、備份、回復與驗證工具位於 scripts。
