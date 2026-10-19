# -*- coding: utf-8 -*-
"""
把「我的法规-在这里填.csv」转换成 corpus.jsonl
=================================================
用法：在终端里跑这一行

/Users/zhangaoran/.workbuddy/binaries/python/envs/default/bin/python regulations/csv_to_corpus.py

它会读取同目录的「我的法规-在这里填.csv」，生成 corpus.jsonl。
原来的 corpus.jsonl 会自动备份成 corpus.jsonl.bak。
"""

import csv
import json
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "我的法规-在这里填.csv")
CORPUS_PATH = os.path.join(BASE, "corpus.jsonl")
BACKUP_PATH = os.path.join(BASE, "corpus.jsonl.bak")

FIELDS = ["id", "market", "category", "lang", "title", "text", "source", "verified", "note"]
REQUIRED = ["id", "market", "category", "title", "text"]


def read_csv_rows():
    """读取 CSV。BOM 会让第一列表头变成 '\\ufeffid'，所以要用 utf-8-sig。"""
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"找不到文件：{CSV_PATH}")
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for raw in reader:
            row = {}
            for k in FIELDS:
                v = (raw.get(k) or "").strip()
                row[k] = v
            # 跳过完全空白的行
            if not any(row.get(k) for k in REQUIRED):
                continue
            rows.append(row)
    return rows


def normalize(row, idx):
    """补全 / 校验字段，避免手填时的小错误把检索搞坏。"""
    rid = (row.get("id") or "").strip() or f"AUTO-{idx:03d}"
    market = (row.get("market") or "ALL").strip().upper()
    category = (row.get("category") or "ALL").strip().lower()
    lang = (row.get("lang") or "zh").strip().lower()
    verified_raw = (row.get("verified") or "").strip().lower()
    # 「是 / true / 1 / 已核对」都当成已核对
    verified = verified_raw in ("true", "是", "1", "yes", "y", "已核对")

    return {
        "id": rid,
        "market": market,
        "category": category,
        "lang": lang,
        "title": (row.get("title") or "").strip(),
        "text": (row.get("text") or "").strip(),
        "source": (row.get("source") or "").strip() or "（未填写来源）",
        "verified": verified,
        "note": (row.get("note") or "").strip(),
    }


def main():
    rows = read_csv_rows()
    if not rows:
        print("❌ CSV 里没有有效数据。请至少填一行（id / market / category / title / text 必填）。")
        return

    if os.path.exists(CORPUS_PATH):
        shutil.copy2(CORPUS_PATH, BACKUP_PATH)
        print(f"已备份原语料 → corpus.jsonl.bak")

    docs = [normalize(r, i + 1) for i, r in enumerate(rows)]
    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"✅ 已写入 {len(docs)} 条 → corpus.jsonl\n")
    verified_count = sum(1 for d in docs if d["verified"])
    print(f"   其中标记为「已核对官网原文」：{verified_count} 条")
    print(f"   仍为示例（verified=false）：{len(docs) - verified_count} 条\n")

    print("各市场分布：")
    stat = {}
    for d in docs:
        stat[d["market"]] = stat.get(d["market"], 0) + 1
    for k, v in sorted(stat.items(), key=lambda x: -x[1]):
        print(f"   {k}: {v} 条")

    print("\n下一步：跑一次检索自检，确认新加的法规能被查到。")


if __name__ == "__main__":
    main()
