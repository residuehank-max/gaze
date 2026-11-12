# 開機之後照這個做

一次性的設定在第 1～4 步，之後加照片只要第 6 步。
指令照 macOS 寫（你的 M1 機）。

---

## 1. 在 GitHub 開一個空 repo

1. 開 https://github.com/new
2. Repository name：**`gaze`**（小寫）
3. 選 **Public** — 免費帳號的 GitHub Pages 需要公開 repo
4. 下面三個勾選框**都不要勾**（Add a README / .gitignore / license）

   要完全空的。勾了會跟這包裡的檔案衝突。
5. Create repository

---

## 2. 推上去

把這包解壓到你想放的地方，然後：

```bash
cd ~/路徑/到/gaze

git init -b main
git add .
git commit -m "init: 攝影作品集，資料與版面分離"
git remote add origin https://github.com/residuehank-max/gaze.git
git push -u origin main
```

如果 push 要帳密，密碼那欄要填 **Personal Access Token**（不是 GitHub 登入密碼）。
沒有的話去 https://github.com/settings/tokens 開一個，勾 `repo` 權限就夠。

---

## 3. 打開 Pages

repo 頁面 → **Settings** → 左側 **Pages** → Source 選 **GitHub Actions**

選完就會自己跑第一次部署。repo 頁面上方 **Actions** 分頁可以看進度，約一兩分鐘。

網址：**https://residuehank-max.github.io/gaze/**

（路徑有大小寫之分，`/gaze/` 全小寫才對。）

---

## 4. 裝 Pillow

處理照片的腳本需要它。macOS 的系統 Python 不讓直接裝，所以開一個虛擬環境：

```bash
cd ~/路徑/到/gaze
python3 -m venv .venv
source .venv/bin/activate
pip install Pillow
```

`.venv/` 已經在 `.gitignore` 裡，不會被推上去。

以後每次要跑腳本前，先 `source .venv/bin/activate`。

---

## 5. 確認腳本跑得起來

```bash
python3 tools/build.py --check
```

`--check` 不會改任何檔案，只報告現在的狀態。應該會告訴你原圖資料夾是空的、
`photos.json` 裡有 20 筆示意資料。

---

## 6. 加照片（之後固定就這幾步）

**第一步，匯出。** 從 Lightroom 或你平常的工具匯出 JPEG，**不用自己縮**，
腳本會處理。原圖直接丟進 `photos-original/`。

**檔名規則**：`年-地點或主題.jpg`，全小寫、用連字號、不要中文和空白。

```
2026-keelung-rain.jpg
2025-taisho-pond.jpg
2024-dihua-street.jpg
```

開頭那個年份不只是給人看的——沒有 EXIF 的底片掃描檔，腳本會從檔名讀年份。

**第二步，跑腳本。**

```bash
source .venv/bin/activate
python3 tools/build.py
```

它會：**把色彩正確轉到 sRGB 並嵌入 profile**、輸出 1280／2560 兩種寬度放進 `images/`、
縮小後補一道銳化、**清掉所有 EXIF（GPS 座標不會上網）**、讀出年份和器材、
算出長寬比和載入用的主色、寫進 `photos.json`。

兩種寬度是給 `srcset` 用的，瀏覽器自己挑——手機拿 1280、retina 桌機才拿 2560。
原圖比 1280 還小的話不會放大，只輸出原尺寸一份。

跑完它會列出還要你手動補的欄位。

**第三步，補標題和分類。** 打開 `photos.json`，找到新加的那幾筆：

```json
{
  "id": "2026-keelung-rain",
  "file": "images/2026-keelung-rain-2560.jpg",
  "sizes": { ... },               ← 腳本產生
  "title": "keelung rain",        ← 改成「基隆 雨港」
  "year": 2026,                   ← 腳本填好了
  "categories": [],               ← 填 ["street"] 或 ["street","travel"]
  "ratio": "3/2",                 ← 腳本算好了
  "gear": "Nikon Zf · 40mm f/2",  ← 腳本從 EXIF 讀的
  "tone": ["#5d6a74", "#b4bcc0"]  ← 腳本算好了
}
```

你只要動 `title` 和 `categories`。其他都是算出來的。

新照片會**附加在陣列最後**，所以網站上也在最後。`photos` 的順序就是你的編排，
腳本不會去動它——想讓新的排前面就自己把那一段剪貼上去。

可用的分類在 `photos.json` 最上面的 `categories`。要加新分類就往那裡加一筆，
篩選列會自己長出來。

**第四步，推上去。**

```bash
git add .
git commit -m "add: 基隆 雨港"
git push
```

一兩分鐘後網站就更新了。

---

## 本機預覽

`photos.json` 是用 `fetch()` 讀的，直接雙擊 `index.html` 會被瀏覽器擋掉。要起伺服器：

```bash
python3 -m http.server 8000
```

然後開 http://localhost:8000

---

## 清掉示意資料

現在 `photos.json` 裡那 20 筆是色塊示意圖（`file` 是空字串）。
等你放進真照片、看夠了之後，把那些 `file` 為空的整筆從 `photos.json` 刪掉就好。

腳本每次跑完都會提醒你還剩幾筆。

---

## 要注意的事

**原圖不在 repo 裡。** `.gitignore` 排除了 `photos-original/` 和各種 RAW 格式。
repo 裡只有壓過的網頁版。所以：網站掛掉無所謂，重做就好；**原圖掉了就真的沒了。**
原圖要自己照 3-2-1 存（本機、外接硬碟、雲端各一份）。GitHub 不算備份。

**公開 repo = 照片可以被下載。** `images/` 裡是 2560px 的版本，夠大但不是原始解析度。
腳本已經清掉 EXIF，所以不會洩漏拍攝地點座標。

**改版面不用碰資料。** 想換排版就只改 `index.html`，`photos.json` 完全不用動。
反過來加照片也不用碰版面。這是整個架構的重點。
