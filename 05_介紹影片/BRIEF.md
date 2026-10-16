---
workflow: general-video
flow: automation
storyboard: no
message: "A 電腦傳送超音波影像，B 電腦自動 AI 分析，最後由醫師產生報告"
destination: youtube
aspect: 1920x1080
language: zh-TW
length: 80s
voice: edge-tts:zh-TW-HsiaoChenNeural
---

## Intent

介紹本專案「腎超新」的雙機流程：A 電腦用超音波圖片發送工具傳圖 → B 電腦醫師工作區自動 AI 分析 → 報告中心產生 PDF 最終報告。使用者要求：影片約 1:00～1:30；展示畫面必須是現在程式碼實際運行的畫面，不可捏造介面；繁體中文字幕與 AI 配音。

## Assets

- assets/shots/*.png — 以 Playwright 操作實際運行的程式（隔離的醫師資料複本，port 8010；A 傳送工具 port 8020）擷取的 1920×1080 截圖，manifest.json 含元素座標。
- assets/pdf/page-*.png — 程式實際產生的報告 PDF（模板 v2）轉圖。
- assets/vo/s1–s8.mp3 — 微軟神經語音「曉臻 zh-TW-HsiaoChenNeural」台灣華語女聲（語速 +5%），逐字時間戳 s*.words.json 由 WordBoundary 換算；durations.json 為 ffprobe 長度。使用者要求台灣口音，取代原先 HeyGen「James Gao」（大陸口音）。

## Customizations

- 繁體中文逐句字幕（依 HeyGen 逐字時間戳對齊）。
- 截圖上以框線與游標標示實際點擊的元素（座標取自真實 DOM）。

## Notes

- 示範影像為原始照片的去識別化複本：頂端標頭（姓名、病歷號、醫院、日期）已塗黑，檔名改為中性名稱，原圖未修改。
- 不宣稱準確率；機率一律稱「模型預測機率」。示範報告保留「真實影像示範／非正式診斷書」標記。
- A 工具的 Windows 原生資料夾對話框無法被瀏覽器錄製，錄製時由啟動腳本自動回應為示範資料夾；網頁介面本身未修改。
