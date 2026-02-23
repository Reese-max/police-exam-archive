"""從 PDF 試題中抽取圖片，存到考古題網站目錄，並更新 JSON 的 figures 欄位"""

import fitz  # PyMuPDF
import json
import os
import re
import hashlib
from pathlib import Path

# === 設定 ===
PDF_BASE = Path(r"C:\Users\User\Desktop\pdf考古題檔案轉換\考古題下載\考古題庫")
JSON_BASE = Path(r"C:\Users\User\Desktop\考古題下載\考古題庫")
SITE_BASE = Path(r"C:\Users\User\Desktop\考古題下載\考古題網站")

# 圖表引用正規式
FIG_RE = re.compile(r'如圖[一二三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩(（\d]|附圖|下圖所示|如下圖')

# 需要處理的試卷（類科, 年份, 科目前綴）
TARGETS = [
    ("交通警察電訊組", "107年", "電路學"),
    ("交通警察電訊組", "109年", "電路學"),
    ("交通警察電訊組", "110年", "通訊系統"),
    ("交通警察電訊組", "110年", "電路學"),
    ("交通警察電訊組", "111年", "電路學"),
    ("刑事警察", "111年", "刑案現場處理與刑事鑑識"),
    ("水上警察", "106年", "水上警察情境實務"),
    ("水上警察", "107年", "水上警察情境實務"),
    ("消防警察", "107年", "消防警察情境實務"),
    ("鑑識科學", "111年", "物理鑑識"),
]

# 最小圖片尺寸（避免抓到裝飾性小圖）
MIN_WIDTH = 50
MIN_HEIGHT = 50
MIN_AREA = 5000  # 最小面積（像素²）


def find_subject_dir(base, cat, year, prefix):
    """找到包含前綴的科目目錄"""
    cat_path = base / cat / year
    if not cat_path.exists():
        return None
    for d in cat_path.iterdir():
        if d.is_dir() and prefix in d.name:
            return d
    return None


def extract_images_from_pdf(pdf_path):
    """從 PDF 抽取所有有意義的圖片，回傳 [(page_num, img_bytes, ext, bbox)] """
    doc = fitz.open(str(pdf_path))
    images = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        img_list = page.get_images(full=True)

        for img_idx, img_info in enumerate(img_list):
            xref = img_info[0]
            try:
                pix = fitz.Pixmap(doc, xref)

                # 轉換 CMYK → RGB
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)

                w, h = pix.width, pix.height

                # 過濾太小的圖
                if w < MIN_WIDTH or h < MIN_HEIGHT or w * h < MIN_AREA:
                    continue

                img_bytes = pix.tobytes("png")
                images.append((page_num + 1, img_bytes, "png", w, h))

            except Exception as e:
                print(f"  ⚠ 抽取圖片失敗 (xref={xref}): {e}")

    doc.close()
    return images


def render_page_as_image(pdf_path, page_num, dpi=200):
    """將整頁 PDF 渲染為圖片（備用方案，用於向量圖/電路圖）"""
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def get_category_site_dir(cat):
    """取得類科在網站中的目錄名"""
    return cat  # 名稱相同


def process_target(cat, year, subj_prefix):
    """處理單一試卷：抽取圖片、更新 JSON"""
    print(f"\n{'='*60}")
    print(f"處理: {cat} / {year} / {subj_prefix}")
    print(f"{'='*60}")

    # 找 PDF
    pdf_dir = find_subject_dir(PDF_BASE, cat, year, subj_prefix)
    if not pdf_dir:
        print(f"  ✗ PDF 目錄未找到")
        return 0

    pdf_path = pdf_dir / "試題.pdf"
    if not pdf_path.exists():
        print(f"  ✗ PDF 檔案不存在: {pdf_path}")
        return 0

    # 找 JSON
    json_dir = find_subject_dir(JSON_BASE, cat, year, subj_prefix)
    if not json_dir:
        print(f"  ✗ JSON 目錄未找到")
        return 0

    json_path = json_dir / "試題.json"
    if not json_path.exists():
        print(f"  ✗ JSON 檔案不存在")
        return 0

    # 建立圖片輸出目錄
    site_cat_dir = SITE_BASE / get_category_site_dir(cat)
    img_dir = site_cat_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    # 讀取 JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 找出引用圖表的題目
    fig_questions = []
    for i, q in enumerate(data.get("questions", [])):
        stem = q.get("stem", "")
        if FIG_RE.search(stem):
            fig_questions.append((i, q))

    if not fig_questions:
        print(f"  無引用圖表的題目，跳過")
        return 0

    print(f"  找到 {len(fig_questions)} 題引用圖表")

    # 方案: 渲染含圖頁面為完整圖片
    # 電路學等理科 PDF 通常是向量圖，直接 render 整頁最可靠
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    # 先嘗試抽取嵌入式圖片
    embedded_images = extract_images_from_pdf(pdf_path)
    print(f"  PDF 共 {total_pages} 頁，找到 {len(embedded_images)} 張嵌入圖片")

    year_num = year.replace("年", "")
    subj_safe = re.sub(r'[^\w]', '_', subj_prefix)[:20]
    count = 0

    if len(embedded_images) >= len(fig_questions):
        # 嵌入圖片足夠，按順序對應到題目
        print(f"  使用嵌入式圖片（{len(embedded_images)} 張）")
        for idx, (q_idx, q) in enumerate(fig_questions):
            if idx >= len(embedded_images):
                break

            page_num, img_bytes, ext, w, h = embedded_images[idx]
            img_hash = hashlib.md5(img_bytes).hexdigest()[:8]
            filename = f"{year_num}_{subj_safe}_q{q.get('number', idx+1)}_{img_hash}.png"
            img_path = img_dir / filename
            img_path.write_bytes(img_bytes)

            # 更新 JSON
            rel_path = f"images/{filename}"
            q_num = q.get("number", str(idx + 1))
            data["questions"][q_idx]["figures"] = [{
                "src": rel_path,
                "alt": f"{year} {subj_prefix} 第{q_num}題圖表"
            }]
            count += 1
            print(f"  ✓ 第{q_num}題 → {filename} ({w}x{h})")
    else:
        # 嵌入圖片不足，改用整頁渲染
        print(f"  嵌入圖片不足，改用頁面渲染方案")

        # 對於申論題 PDF，通常每題佔 1-2 頁
        # 電路圖通常在題目所在頁面
        for idx, (q_idx, q) in enumerate(fig_questions):
            q_num = q.get("number", str(idx + 1))
            q_type = q.get("type", "essay")

            if q_type == "essay":
                # 申論題：每題通常佔半頁到一頁
                # 第一頁通常是考試說明，題目從第二頁開始
                # 嘗試根據題號推算頁面
                try:
                    # 中文數字轉阿拉伯
                    cn_nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
                    if q_num in cn_nums:
                        num = cn_nums[q_num]
                    else:
                        num = int(q_num)
                    # 第1頁是封面/說明，題目從第2頁開始
                    target_page = min(num, total_pages - 1)
                except (ValueError, KeyError):
                    target_page = min(idx + 1, total_pages - 1)
            else:
                # 選擇題：需要搜尋題號在哪一頁
                target_page = None
                for p in range(total_pages):
                    page = doc[p]
                    text = page.get_text()
                    if q_num in text and ("圖" in text or "附圖" in text):
                        target_page = p
                        break
                if target_page is None:
                    target_page = min(idx + 1, total_pages - 1)

            # 渲染該頁
            img_bytes = render_page_as_image(pdf_path, target_page, dpi=200)
            img_hash = hashlib.md5(img_bytes).hexdigest()[:8]
            filename = f"{year_num}_{subj_safe}_q{q_num}_p{target_page+1}_{img_hash}.png"
            img_path = img_dir / filename
            img_path.write_bytes(img_bytes)

            rel_path = f"images/{filename}"
            data["questions"][q_idx]["figures"] = [{
                "src": rel_path,
                "alt": f"{year} {subj_prefix} 第{q_num}題圖表 (試卷第{target_page+1}頁)"
            }]
            count += 1
            size_kb = len(img_bytes) // 1024
            print(f"  ✓ 第{q_num}題 → {filename} (頁{target_page+1}, {size_kb}KB)")

    doc.close()

    # 儲存更新的 JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ JSON 已更新: {json_path.name}")

    return count


def main():
    print("=" * 60)
    print("  考古題圖片抽取工具")
    print("=" * 60)

    total = 0
    for cat, year, subj_prefix in TARGETS:
        count = process_target(cat, year, subj_prefix)
        total += count

    print(f"\n{'='*60}")
    print(f"  完成！共抽取 {total} 張圖片")
    print(f"{'='*60}")

    if total > 0:
        print(f"\n下一步: 執行 python generate_html.py 重新生成網站")


if __name__ == "__main__":
    main()
