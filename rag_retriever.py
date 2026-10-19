# -*- coding: utf-8 -*-
"""
朴素 RAG 检索引擎 —— 日选 AI 法规合规模块
================================================

这一份是「能跑的教材」。阅读顺序建议：
  1. 先看 retrieve() —— 整个 RAG 的核心只有 4 步
  2. 再看 tokenize() —— 中日文分词为什么要分开处理
  3. 最后看 build_prompt() —— 检索结果怎么喂给大模型

RAG = Retrieval（检索）+ Augmented（增强）+ Generation（生成）
朴素 RAG = 不做向量、不做 embedding，用关键词检索。

为什么法规场景用关键词而不是向量？
  - 法规条款短、术语密集（"PSE""菱形""GPSR"），关键词命中率反而高
  - 命中可解释、可引用出处 —— 合规场景必须要能回答"这句话依据哪一条"
  - 零额外依赖、零 embedding 成本、检索延迟 < 10ms
这是产品判断，不是技术偷懒。面试时要能讲出来。
"""

import json
import os
import re
from typing import List, Dict

import jieba
from rank_bm25 import BM25Okapi

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "regulations", "corpus.jsonl")


# ----------------------------------------------------------------------
# 第 1 步：分词（分词质量直接决定检索质量）
# ----------------------------------------------------------------------
def tokenize(text: str, lang: str = "zh") -> List[str]:
    """
    中日文必须分开处理，这是朴素 RAG 里最容易踩的坑。

    - 中文：有词边界，用 jieba 分词效果好
    - 日文：没有空格，jieba 是按中文语料训练的，切日文会切碎
            → 用「字符 2-gram」兜底，对中日韩都稳
    - 英文/数字：小写化后按非字母数字切
    """
    text = (text or "").strip()
    if not text:
        return []

    if lang == "ja":
        # 字符 2-gram：把 "電気用品安全法" 切成 [電気, 気用, 用品, 品安, 安全, 全法]
        # 好处是不依赖分词器，召回率高；坏处是索引稍大
        cleaned = re.sub(r"\s+", "", text)
        grams = [cleaned[i:i + 2] for i in range(len(cleaned) - 1)]
        # 保留英文数字原词，避免 "PSE" 被切成 "PS""SE"
        grams += [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text)]
        return grams or [cleaned]

    if lang == "en":
        return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text)]

    # 默认按中文处理
    # ⚠️ 用 lcut_for_search 而不是 lcut：搜索引擎模式会切出更细的粒度
    #    例："儿童玩具" → lcut 只给 ["儿童玩具"]，文档里只有"儿童"就永远召回不到
    #        lcut_for_search 给 ["儿童","玩具","儿童玩具"]，召回率明显更高
    #    这是分词粒度不一致导致的漏召回，朴素 RAG 里最常见的坑之一
    tokens = [t for t in jieba.lcut_for_search(text) if t.strip()]
    tokens += [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text)]
    return tokens


# ----------------------------------------------------------------------
# 第 2 步：加载语料 + 建索引（BM25）
# ----------------------------------------------------------------------
class RegulationRetriever:
    """
    BM25 是一种「改进版 TF-IDF」：
      - 词频高 → 更相关（TF）
      - 但同一个词出现 10 次不等于重要 10 倍 → 有饱和抑制
      - 稀有词比常见词更有区分度（IDF）
      - 长文档天然包含更多词 → 有长度归一

    对比你想学的「向量检索」：
      BM25      靠字面重合，可解释、零成本、术语命中强
      向量检索  靠语义相似，能命中"意思一样但说法不同"的查询，但需要 embedding 调用成本
    法规场景先做 BM25；等 BM25 明显不够用了再上向量——这才是正确的迭代顺序。
    """

    def __init__(self, corpus_path: str = CORPUS_PATH):
        self.docs: List[Dict] = []
        self.tokenized: List[List[str]] = []
        self.bm25: BM25Okapi = None
        if os.path.exists(corpus_path):
            self.load(corpus_path)

    def load(self, corpus_path: str):
        self.docs = []
        with open(corpus_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                self.docs.append(json.loads(line))
        self._build_index()

    def _build_index(self):
        self.tokenized = [
            tokenize(f"{d.get('title','')} {d.get('text','')}", d.get("lang", "zh"))
            for d in self.docs
        ]
        # 语料为空时 BM25Okapi 会报错，这里兜住
        self.bm25 = BM25Okapi(self.tokenized) if self.tokenized else None

    # ------------------------------------------------------------------
    # 第 3 步：检索（可以按市场/品类过滤，这是产品逻辑不是检索逻辑）
    # ------------------------------------------------------------------
    def retrieve(self, query: str, market: str = None, category: str = None,
                 top_k: int = 3) -> List[Dict]:
        """
        完整的 RAG 第 1 步就在这里：query → top_k 条最相关法规
        """
        if not self.bm25 or not self.docs:
            return []

        # 先按市场/品类过滤候选集 —— 合规场景下「不相关市场的法规」是噪音，必须提前剪掉
        candidate_idx = [
            i for i, d in enumerate(self.docs)
            if (market is None or d.get("market") in (market, "ALL"))
            and (category is None or d.get("category") in (category, "ALL"))
        ]
        if not candidate_idx:
            candidate_idx = list(range(len(self.docs)))

        q_tokens = tokenize(query, "ja" if market == "JP" else "zh")
        scores = self.bm25.get_scores(q_tokens)

        ranked = sorted(candidate_idx, key=lambda i: scores[i], reverse=True)
        ranked = [i for i in ranked if scores[i] > 0][:top_k]

        return [
            {
                "id": self.docs[i].get("id"),
                "title": self.docs[i].get("title"),
                "text": self.docs[i].get("text"),
                "source": self.docs[i].get("source"),
                "market": self.docs[i].get("market"),
                "score": round(float(scores[i]), 3),
                # 核实状态随结果一起返回：合规场景下「这条能不能直接信」和「这条相不相关」同等重要
                "verified": bool(self.docs[i].get("verified", False)),
            }
            for i in ranked
        ]


# ----------------------------------------------------------------------
# 第 4 步：把检索结果拼进 Prompt（这就是 "Augmented"）
# ----------------------------------------------------------------------
def build_prompt(query: str, hits: List[Dict], product_name: str = "",
                 market: str = "", category: str = "") -> str:
    """
    RAG 的 "A"（增强）就发生在这一步：把检索到的法规原文塞进上下文。

    关键设计：要求模型「引用条款编号」。
    这样输出可追溯，也让你能自动检测幻觉——模型引用的编号如果不在 hits 里，就是编的。
    这个「引用校验」可以直接做成硬断言，和你在医者 AI 做的对照实验是同一套方法论。
    """
    if not hits:
        return (
            f"未检索到适用法规条款，请勿自行编造合规要求。\n"
            f"请基于通用合规原则回答，并明确提示用户咨询专业合规机构。\n\n"
            f"问题：{query}"
        )

    context = "\n\n".join(
        f"[{i+1}] 条款编号 {h['id']}｜{h['title']}"
        f"{'（已与官方原文核对）' if h.get('verified') else '（尚未与官方原文核对）'}\n"
        f"{h['text']}\n出处：{h['source']}"
        for i, h in enumerate(hits)
    )
    allowed_ids = "、".join(h["id"] for h in hits)

    return f"""你是跨境电商合规专家。请严格依据下列法规条款回答问题。

=== 适用法规条款（只允许引用这些）===
{context}

=== 任务 ===
目标市场：{market or '未指定'}
品类：{category or '未指定'}
商品：{product_name or '未指定'}
用户问题：{query}

=== 硬性要求 ===
1. 只能使用上面列出的条款，条款编号仅限于：{allowed_ids}
2. 每给出一条合规要求，必须在其后标注引用的条款编号，格式如「（依据 {hits[0]['id']}）」
3. 若上述条款不足以回答，直接说明"现有条款库未覆盖，建议咨询专业合规机构"，禁止编造
4. 不要输出你在条款中未看到的具体数值、认证编号或法条序号
5. 引用标注为「尚未与官方原文核对」的条款时，在句末加「（该条待官方核对，建议复核后执行）」
"""


if __name__ == "__main__":
    # 离线自检：不调用任何 API
    r = RegulationRetriever()
    print(f"语料条数：{len(r.docs)}")
    for q in ["日本销售的充电器需要什么认证？", "欧盟销售需要欧盟负责人吗？", "儿童玩具出口注意什么？"]:
        print(f"\n查询：{q}")
        for hit in r.retrieve(q, top_k=2):
            print(f"  [{hit['score']}] {hit['id']} {hit['title']}")
