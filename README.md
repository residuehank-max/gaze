# gaze

> 開機之後第一次設定，看 **[SETUP.md](SETUP.md)**。

個人攝影作品集，靜態網站，跑在 GitHub Pages 上。

## 設計原則：資料與呈現分開

| 檔案 | 角色 |
|---|---|
| `photos.json` | **資料層。** 唯一的真實來源——有哪些照片、標題、年份、分類、長寬比、器材。 |
| `index.html` | **呈現層。** 讀 `photos.json` 然後畫出來。對「有哪些照片」零假設。 |
| `images/` | 網頁用的照片。每張兩種寬度，sRGB，無 EXIF。腳本產生，不要手改。 |
| `photos-original/` | 你丟原圖的地方。**不進 repo。** |
| `tools/build.py` | 建置腳本。壓縮、去 EXIF、讀器材、算主色、更新 `photos.json`。 |
| `.github/workflows/deploy.yml` | 推到 main 就自動部署到 Pages。 |

換版面只改 `index.html`，資料不動。加照片只改 `photos.json` 和 `images/`，版面不動。

## 加一張照片

```bash
source .venv/bin/activate
python3 tools/build.py        # 壓縮、去 EXIF、讀器材、算主色、寫 photos.json
```

1. 原圖丟進 `photos-original/`，檔名 `年-主題.jpg`（全小寫、連字號、不要中文）
2. 跑上面那行
3. 打開 `photos.json`，把新那幾筆的 `title` 和 `categories` 補好（其他欄位腳本算好了）
4. `git add . && git commit -m "add: 照片名" && git push`

一兩分鐘後網站就更新了。詳細說明在 [SETUP.md](SETUP.md)。

## photos.json 欄位

```json
{
  "id": "2025-taisho-pond",
  "file": "images/2025-taisho-pond-2560.jpg",
  "sizes": {
    "1024": "images/2025-taisho-pond-1280.jpg",
    "2048": "images/2025-taisho-pond-2560.jpg"
  },
  "title": "上高地 大正池",
  "year": 2025,
  "categories": ["travel", "landscape"],
  "ratio": "3/2",
  "gear": "Nikon Zf · 24-70mm f/4",
  "tone": ["#6f8a86", "#cfd9d2"]
}
```

| 欄位 | 說明 |
|---|---|
| `id` | 永久識別碼，跟檔名分開。檔案改名不影響它。 |
| `file` | 預設圖（最大那張）。留空字串會顯示 `tone` 的色塊，可以先排版面、照片後補。 |
| `sizes` | 各尺寸的對應表，**key 是該檔案的實際像素寬度**。網頁用它組 `srcset`，瀏覽器自己挑——手機不會去下載 2560px 的版本。腳本產生。 |
| `categories` | **陣列**，一張照片可以掛多個分類。 |
| `ratio` | 長寬比，例如 `3/2`、`4/5`、`16/9`。寫在資料裡，瀏覽器在圖載入前就知道要留多高，版面不會跳動。 |
| `gear` | 機身、鏡頭、底片。單張檢視時顯示在標題旁。 |
| `tone` | 兩個主色，照片載入中的底色。網路慢的時候看到的是這張照片的色調而不是空白。 |

`photos` 陣列的**順序就是網站上的順序**，那是你的編排。腳本加新照片時一律附加在最後，
不會動到你排好的，要移位置自己剪貼。

分類清單本身也在 `photos.json` 的 `categories` 裡。新增分類改資料就好，篩選列會自己長出來；沒有照片的分類自動隱藏。

## 版面

右上角可切換：

- **單張** — 預設。一次一張，照片佔住畫面，左右鍵／縮圖／滑動換張，點照片進全螢幕。
  網址會跟著目前這張走（`...#2025-taisho-pond`），複製貼給別人會開在同一張。
- **索引** — 瀑布流，保留原始長寬比，用來跳著找。
- **清單** — 一行一張，資訊密度最高。

三種讀同一份資料。

## 色彩

輸出檔一律轉到 sRGB 並嵌入 profile。

這不是講究而是必要：如果你在 Lightroom 匯出 AdobeRGB 或 ProPhoto，檔案裡的數值
只有配上那個 ICC profile 才有意義。profile 一掉，瀏覽器會把同一組數值當成 sRGB 解讀，
照片飽和度掉、顏色偏掉——而你在自己電腦上看原圖完全不會發現。

縮小之後會補一道輕量 unsharp mask（`tools/build.py` 裡的 `SHARPEN`）。
縮放一定會軟，這是補回來，不是加效果。覺得過頭就把 `percent` 調低。

## 原圖與備份

原圖**不在這個 repo 裡**（`.gitignore` 已排除）。repo 裡只有壓過的網頁版。

也就是說：網站掛掉無所謂，重做就好；**原圖掉了就真的沒了**。所以原圖照 3-2-1 存：

1. 本機硬碟（工作用）
2. 外接硬碟（定期同步，建議用同步軟體不要手動拖）
3. 雲端（負責「異地」——家裡失火或被偷的時候就靠這份）

GitHub 不算備份。

## 本機預覽

`photos.json` 是用 `fetch()` 讀的，直接雙擊 `index.html` 會被瀏覽器的同源政策擋住。要起一個本機伺服器：

```bash
cd gaze
python3 -m http.server 8000
```

然後開 http://localhost:8000
