# -*- coding: utf-8 -*-
"""
把千问生成的《各国法规速查_违规与卖家义务.docx》转换成 CSV 语料
==================================================================
做三件事：
  1. 按章节切分，每个 Normal 段落 = 一条法规
  2. 剔除「労働安全衛生法」整章（雇主劳动法义务，与跨境卖家卖货合规无关，是语料噪音）
  3. 修正已核实的错误（如ステマ规制日期），并在 note 里标注待核对项

用法：
/Users/zhangaoran/.workbuddy/binaries/python/envs/default/bin/python regulations/docx_to_csv.py
"""

import csv
import os
import re

from docx import Document

BASE = os.path.dirname(os.path.abspath(__file__))
DOCX_PATH = "/Users/zhangaoran/Downloads/各国法规速查_违规与卖家义务.docx"
CSV_PATH = os.path.join(BASE, "我的法规-在这里填.csv")

# 章节 → (市场, 默认品类, id 前缀)
SECTION_MAP = {
    "一": ("JP", "electronics", "JP-PSE"),
    "二": None,                          # 労働安全衛生法 —— 整章剔除（劳动法噪音）
    "三": ("JP", "ALL", "JP-CAA"),
    "四": ("DE", "ALL", "EU-GPSR"),
    "五": ("DE", "electronics", "EU-CE"),
}

# 按关键词细化品类（覆盖上面给的默认值）
CATEGORY_KEYWORDS = [
    ("食品", "food"),
    ("機能性", "food"),
    ("健康増進", "food"),
    ("繊維", "home"),
    ("家庭用品", "home"),
    ("電気用品", "electronics"),
    ("化学物質", "electronics"),
]

# 已核实并修正的错误：原文错 → 正确
VERIFIED_FIXES = [
    ("自2025年10月1日起", "自2023年10月1日起"),   # ステマ规制实际为令和5年(2023)10月1日施行
]

# 需要重点核对的条目关键词（命中则在 note 里标记）
NEED_CHECK_KEYWORDS = ["品目", "保存", "欧元", "营业额", "0.1%", "45天", "3个工作日", "日内", "个月"]


def parse_docx():
    """按 Heading 2 分章节，抽出 (章节号, 来源链接, [正文段落])。"""
    doc = Document(DOCX_PATH)
    sections = []
    cur = None
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = p.style.name
        if style == "Heading 2":
            m = re.match(r"^([一二三四五六七八九十]+)、", text)
            key = m.group(1) if m else None
            cur = {"key": key, "heading": text, "source": "", "items": []}
            sections.append(cur)
        elif cur is None:
            continue
        elif text.startswith("来源链接"):
            cur["source"] = text.replace("来源链接：", "").replace("来源链接:", "").strip()
        elif style in ("Normal", "First Paragraph"):
            cur["items"].append(text)
        elif style == "Heading 1":
            continue
    return sections


def guess_category(text, default):
    for kw, cat in CATEGORY_KEYWORDS:
        if kw in text:
            return cat
    return default


def build_rows():
    sections = parse_docx()
    rows = []
    dropped = 0
    fixed = 0

    for sec in sections:
        cfg = SECTION_MAP.get(sec["key"])
        if cfg is None:
            dropped += len(sec["items"])
            continue
        market, default_cat, prefix = cfg

        for i, text in enumerate(sec["items"], 1):
            # 修正已核实的错误
            note_parts = []
            for wrong, right in VERIFIED_FIXES:
                if wrong in text:
                    text = text.replace(wrong, right)
                    fixed += 1
                    note_parts.append(f"已修正：{wrong} → {right}（官网核实）")

            if any(kw in text for kw in NEED_CHECK_KEYWORDS):
                note_parts.append("含具体数字/期限，建议二次核对")

            rows.append({
                "id": f"{prefix}-{i:03d}",
                "market": market,
                "category": guess_category(text, default_cat),
                "lang": "zh",
                "title": f"{sec['heading'].split('、', 1)[-1][:28]} 要点{i:02d}",
                "text": text,
                "source": sec["source"],
                "verified": "否",
                "note": "；".join(note_parts),
            })

    return rows, dropped, fixed


def main():
    if not os.path.exists(DOCX_PATH):
        print(f"找不到文档：{DOCX_PATH}")
        return

    rows, dropped, fixed = build_rows()

    # 读回现有 CSV 的表头，保持一致
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "market", "category", "lang", "title", "text", "source", "verified", "note"])
        w.writeheader()
        w.writerows(rows)

    print(f"✅ 已生成 CSV：{len(rows)} 条 → 我的法规-在这里填.csv")
    print(f"   剔除劳动法噪音：{dropped} 条（労働安全衛生法整章，与卖家卖货合规无关）")
    print(f"   修正已核实错误：{fixed} 处\n")

    stat = {}
    for r in rows:
        stat[r["market"]] = stat.get(r["market"], 0) + 1
    print("各市场分布：")
    for k, v in sorted(stat.items(), key=lambda x: -x[1]):
        print(f"   {k}: {v} 条")

    need_check = sum(1 for r in rows if "核对" in r["note"])
    print(f"\n⚠️  其中 {need_check} 条含具体数字/期限，建议逐条官网核对后把 verified 改成「是」")


if __name__ == "__main__":
    main()
