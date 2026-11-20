#!/usr/bin/env python3
"""
gaze — 照片建置腳本

把 photos-original/ 裡的照片處理成網頁用的版本，並更新 photos.json。

做這幾件事：
  1. 色彩      用原圖的 ICC profile 正確轉到 sRGB，並嵌入 sRGB profile
  2. 壓縮      輸出 1280 / 2560 兩種寬度，品質 82、漸進式 JPEG，放進 images/
  3. 銳化      縮小後補一道輕量 unsharp mask，抵銷縮放造成的軟化
  4. 去 EXIF   輸出檔不帶任何 EXIF，GPS 座標不會跟著上網
  5. 讀資料    從原圖 EXIF 取年份、機身、鏡頭，算出長寬比和主色
  6. 合併      寫回 photos.json，手打的標題、分類和排列順序一律保留

用法：
    python3 tools/build.py              # 只處理新的或改過的照片
    python3 tools/build.py --force      # 全部重新處理
    python3 tools/build.py --check      # 不改檔案，只報告現在的狀態

需要 Pillow：
    pip install Pillow
"""

import argparse
import io
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

try:
    from PIL import Image, ImageOps, ImageCms, ImageFilter, ExifTags
except ImportError:
    sys.exit("缺少 Pillow。先跑：pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "photos-original"
OUT_DIR = ROOT / "images"
DATA = ROOT / "photos.json"

# 輸出寬度。瀏覽器會用 srcset 自己挑合適的那個——
# 手機不用下載 2560px，桌機 retina 才會拿。
WIDTHS = [1280, 2560]
QUALITY = 82            # JPEG 品質
SRC_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

# 縮小後的補償銳化。數字保守，寧可不夠也不要過頭——
# 過度銳化在人像的皮膚和天空的漸層上特別難看。
SHARPEN = dict(radius=0.8, percent=55, threshold=3)

# sRGB 是網頁的標準色彩空間，所有輸出都轉到這裡
_SRGB = ImageCms.createProfile("sRGB")
SRGB_BYTES = ImageCms.ImageCmsProfile(_SRGB).tobytes()

# 機身／鏡頭名稱整理。EXIF 寫的往往很醜，這裡換成你想顯示的寫法。
# 要加就直接往下寫，左邊是 EXIF 原文（會轉小寫比對），右邊是顯示用的。
ALIASES = {
    "nikon z f": "Nikon Zf",
    "nikon zf": "Nikon Zf",
    "nikon z 6_2": "Nikon Z6 II",
    "nikkor z 40mm f/2": "40mm f/2",
    "nikkor z 85mm f/1.8 s": "85mm f/1.8",
    "nikkor z 24-70mm f/4 s": "24-70mm f/4",
    "nikkor z mc 50mm f/2.8": "50mm macro",
}


# ---------------------------------------------------------------- helpers

def tidy(name: str) -> str:
    """把 EXIF 的機身／鏡頭名稱換成好看的寫法。"""
    if not name:
        return ""
    s = " ".join(name.split())
    return ALIASES.get(s.lower(), s)


def slugify(stem: str) -> str:
    """檔名轉成乾淨的 id：小寫、連字號、不留奇怪符號。"""
    s = stem.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "photo"


def title_from(stem: str) -> str:
    """從檔名猜一個暫時的標題，去掉開頭年份。等你自己改成想要的。"""
    s = re.sub(r"^\d{4}[-_]?", "", stem)
    s = re.sub(r"[-_]+", " ", s).strip()
    return s or stem


def year_from(stem: str):
    """檔名開頭的年份。底片掃描檔沒有 EXIF，就靠這個。"""
    m = re.match(r"(19|20)(\d{2})\b", stem)
    if not m:
        return None
    y = int(m.group(0))
    return y if 1900 <= y <= 2100 else None


def ratio_of(w: int, h: int) -> str:
    """算出好看的長寬比字串，例如 3/2、4/5、16/9。"""
    f = Fraction(w, h).limit_denominator(16)
    return f"{f.numerator}/{f.denominator}"


def tone_of(img: Image.Image):
    """抓兩個代表色，當照片載入中的底色。"""
    small = img.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    pal = small.quantize(colors=2, method=Image.Quantize.FASTOCTREE)
    counts = sorted(pal.getcolors() or [], reverse=True)
    raw = pal.getpalette() or []
    out = []
    for _, idx in counts[:2]:
        r, g, b = raw[idx * 3 : idx * 3 + 3]
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    while len(out) < 2:
        out.append(out[0] if out else "#8a9099")
    # 深的放前面、淺的放後面，漸層方向才一致
    def lum(hexstr):
        v = hexstr.lstrip("#")
        r, g, b = (int(v[i : i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    out.sort(key=lum)
    return out


def to_srgb(im: Image.Image):
    """
    轉到 sRGB。

    這一步是必要的，不是講究。如果你在 Lightroom 匯出 AdobeRGB 或 ProPhoto，
    檔案裡的數值只有配上那個 ICC profile 才有意義。profile 一掉，瀏覽器會把
    同一組數值當成 sRGB 解讀——結果是整張照片飽和度掉、顏色偏掉，而且你在
    自己電腦上看原圖完全不會發現。

    AdobeRGB 和 sRGB 都是矩陣型 profile，沒有 perceptual 對應表，所以指定
    perceptual 也會退回 relative colorimetric。這裡就直接寫明。

    回傳 (影像, 用了什麼轉換) 方便報告。
    """
    icc = im.info.get("icc_profile")

    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            name = ImageCms.getProfileDescription(src).strip() or "未命名 profile"
            im = ImageCms.profileToProfile(
                im, src, _SRGB,
                outputMode="RGB",
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            )
            return im, name
        except Exception:
            # profile 壞掉或不支援，退回直接轉 RGB
            return im.convert("RGB"), "profile 讀不了，當 sRGB 處理"

    # 沒有 profile 的檔案，慣例上就是 sRGB
    return im.convert("RGB"), None


def exif_of(img: Image.Image):
    """從 EXIF 取年份和器材。底片掃描檔通常沒有，回傳空值。"""
    year, gear = None, ""
    try:
        ex = img.getexif()
    except Exception:
        return year, gear
    if not ex:
        return year, gear

    make = tidy(str(ex.get(271, "")))      # Make
    model = tidy(str(ex.get(272, "")))     # Model
    lens = ""
    try:
        sub = ex.get_ifd(ExifTags.IFD.Exif)
        shot = sub.get(36867) or sub.get(36868)   # DateTimeOriginal / Digitized
        if shot:
            m = re.match(r"(\d{4})", str(shot))
            if m:
                year = int(m.group(1))
        lens = tidy(str(sub.get(42036, "")))      # LensModel
    except Exception:
        pass

    body = model or make
    gear = " · ".join(x for x in (body, lens) if x)
    return year, gear


# ---------------------------------------------------------------- data i/o

def load_data():
    if not DATA.exists():
        sys.exit(f"找不到 {DATA.name}")
    with DATA.open(encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with DATA.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------- build

def build(force=False, check=False):
    if not SRC_DIR.exists():
        SRC_DIR.mkdir(parents=True)
    OUT_DIR.mkdir(exist_ok=True)

    data = load_data()
    by_id = {p.get("id"): p for p in data.get("photos", [])}

    sources = sorted(
        p for p in SRC_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SRC_EXT and not p.name.startswith(".")
    )

    made, skipped, added = [], [], []

    profiles_seen = {}

    for src in sources:
        pid = slugify(src.stem)

        with Image.open(src) as probe:
            probe = ImageOps.exif_transpose(probe)
            w0, h0 = probe.size
        long0 = max(w0, h0)

        # 只產生不超過原圖的尺寸，絕不放大。
        # 原圖小於最大尺寸時，另外輸出一份原尺寸——
        # 例如原圖 2352px，只給 1280 的話 retina 螢幕會浪費掉一半解析度。
        targets = [t for t in WIDTHS if t <= long0]
        if long0 < max(WIDTHS) and long0 not in targets:
            targets.append(long0)
        biggest = OUT_DIR / f"{pid}-{max(targets)}.jpg"

        fresh = biggest.exists() and biggest.stat().st_mtime >= src.stat().st_mtime
        if fresh and not force and pid in by_id:
            skipped.append(pid)
            continue

        sizes = {}
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)

            year, gear = exif_of(im)
            year = year or year_from(src.stem)   # 沒 EXIF 就用檔名開頭的年份

            im, prof = to_srgb(im)               # 色彩先轉好，再縮
            if prof:
                profiles_seen[pid] = prof

            tone = tone_of(im)
            ratio = ratio_of(w0, h0)

            for t in sorted(targets):
                scale = t / long0
                tw, th = max(1, round(w0 * scale)), max(1, round(h0 * scale))

                if scale < 1:
                    frame = im.resize((tw, th), Image.Resampling.LANCZOS)
                    # 縮完補銳化。縮小一定會軟，這是在補回來，不是在加效果。
                    frame = frame.filter(ImageFilter.UnsharpMask(**SHARPEN))
                else:
                    frame = im

                out = OUT_DIR / f"{pid}-{t}.jpg"
                if not check:
                    # 不傳 exif=，所以輸出檔沒有任何 EXIF（GPS 不會上網）；
                    # 但要傳 icc_profile=，否則瀏覽器會猜錯色彩空間。
                    frame.save(
                        out, "JPEG",
                        quality=QUALITY, optimize=True, progressive=True,
                        icc_profile=SRGB_BYTES,
                    )
                sizes[str(tw)] = f"images/{out.name}"

        rel = sizes[str(max(int(k) for k in sizes))]   # 最大那張當預設

        entry = by_id.get(pid)
        if entry is None:
            entry = {
                "id": pid,
                "file": rel,
                "sizes": sizes,
                "title": title_from(src.stem),
                "year": year or 0,
                "categories": [],
                "ratio": ratio,
                "gear": gear,
                "tone": tone,
            }
            # 附加在最後，不插到前面——photos.json 的陣列順序就是你編排的順序，
            # 加照片不該動到它。新的位置你自己挪。
            data.setdefault("photos", []).append(entry)
            by_id[pid] = entry
            added.append(pid)
        else:
            # 手打的欄位不動，只更新從圖算出來的
            entry["file"] = rel
            entry["sizes"] = sizes
            entry["ratio"] = ratio
            entry["tone"] = tone
            if not entry.get("year") and year:
                entry["year"] = year
            if not entry.get("gear") and gear:
                entry["gear"] = gear
        made.append(pid)

    # 資料裡有、但圖不見了的。--check 模式下，這一輪本來要產生的不算遺失。
    processed = set(made)
    missing = [
        p["id"] for p in data.get("photos", [])
        if p.get("file")
        and not (ROOT / p["file"]).exists()
        and p.get("id") not in processed
    ]

    if not check:
        save_data(data)

    # ------------------------------------------------------------ report
    tag = "［檢查模式，沒有改任何檔案］" if check else ""
    print(f"\ngaze build {tag}")
    print(f"  原圖資料夾   {SRC_DIR.name}/   {len(sources)} 個檔案")
    print(f"  處理         {len(made)}        跳過（沒變動）{len(skipped)}")
    print(f"  新增到資料    {len(added)}")
    print(f"  輸出寬度      {' / '.join(str(x) for x in WIDTHS)}px（不超過原圖）")

    if profiles_seen:
        print(f"\n  色彩轉換（原圖不是 sRGB，已轉好並嵌入 sRGB）：")
        for pid, prof in profiles_seen.items():
            print(f"    {pid}  ←  {prof}")

    if added:
        print("\n  新加進 photos.json：")
        for pid in added:
            e = by_id[pid]
            y = e["year"] or "年份待填"
            print(f"    {pid}  ({e['ratio']}, {y})")

    todo = [
        p for p in data.get("photos", [])
        if p.get("file") and (not p.get("categories") or not p.get("year"))
    ]
    if todo:
        print(f"\n  還要你手動補的（{len(todo)} 筆）：")
        for p in todo:
            need = []
            if not p.get("categories"):
                need.append("分類")
            if not p.get("year"):
                need.append("年份")
            print(f"    {p['id']}  缺 {'、'.join(need)}   標題目前是「{p.get('title','')}」")

    if missing:
        print(f"\n  ⚠ 資料裡有這幾筆，但 images/ 找不到檔案：")
        for pid in missing:
            print(f"    {pid}")

    placeholders = [p["id"] for p in data.get("photos", []) if not p.get("file")]
    if placeholders:
        print(f"\n  （{len(placeholders)} 筆還是示意色塊，沒有對應照片——"
              f"要清掉的話把它們從 photos.json 刪掉就好）")

    print()


def main():
    ap = argparse.ArgumentParser(description="gaze 照片建置")
    ap.add_argument("--force", action="store_true", help="全部重新處理，不管有沒有變動")
    ap.add_argument("--check", action="store_true", help="只報告狀態，不改任何檔案")
    args = ap.parse_args()
    build(force=args.force, check=args.check)


if __name__ == "__main__":
    main()
