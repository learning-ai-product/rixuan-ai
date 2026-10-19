# 日选 AI · 出海 Listing 智能生成与合规风控

> 面向 TikTok Shop / 独立站卖家的中日双语 Listing 生成工具。内置合规风险分层与熔断降级机制，避免生成违反目标市场法规的内容。

## 项目背景

2026 年 6–8 月我作为 TikTok Shop 美区一级经销商运营，发现小卖家写一条多语言 Listing 平均要 2 小时，且对目标市场法规（如日本 PSE、欧盟 GPSR）缺少判断，容易踩雷。本项目从该痛点出发，用 Streamlit + DeepSeek API 做了一个可交互的 MVP。

## 当前功能

- 输入商品信息后，自动生成亚马逊日本站 / 其他市场风格的 Listing
- 根据「目标市场 + 品类」输出高 / 中 / 低三档风险等级
- 命中高风险时熔断，提示人工复核；中风险抽检；低风险直通
- 失败时输出兜底卖点模板，而不是报错页
- 高频问题走本地缓存，降低 API 调用成本

## 运行方式

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 密钥配置（重要）

代码里**没有写死任何 API Key**。本地开发时可在侧边栏输入；部署到 Streamlit Community Cloud 时，在 App 后台 `Settings → Secrets` 配置：

```toml
DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
```

## 演示

81 秒竖屏实录（调用链路：输入商品信息 → 生成中日双语 Listing → 命中合规提示）：

[点击下载演示视频 MP4（9.4 MB）](https://zhangaoran.github.io/portfolio/media/rixuan-ai-demo.mp4)

> 注：作品集页含完整项目说明、医者 AI 评测报告与本项目演示。

## 已知局限

- RAG 合规文档召回模块正在接入（计划 11 月中旬完成）
- 当前风控规则以品类 / 市场关键词为主，尚未接入各国官方法规全文
- 模型输出需人工最终审核，不可替代专业法务/合规判断

## 技术栈

Streamlit · Python · DeepSeek API · 朴素 RAG（BM25 + 关键词召回，开发中）

---

本项目为个人学习与求职作品集，所有代码由本人独立完成。
