import streamlit as st
import json, os, time, datetime, requests
from rag_retriever import RegulationRetriever, build_prompt

def _load_api_key():
    """优先从 Streamlit Secrets 读取（部署用），其次读环境变量，最后回退空值。
    密钥永不写死在代码里 —— 仓库一旦公开，硬编码密钥会在几分钟内被扫描机器人抓走。"""
    key = ""
    try:
        key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except Exception:
        pass
    if not key:
        key = os.environ.get("DEEPSEEK_API_KEY", "")
    return key or ""

API_KEY = _load_api_key()
API_BASE_URL = "https://api.deepseek.com/v1"
MODEL_NAME = "deepseek-chat"
CACHE_FILE = 'highlight_cache.json'

def extract_highlights(product_name, description, category):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                if f"{product_name}_{description}_{category}" in cache:
                    return cache[f"{product_name}_{description}_{category}"]
        except Exception:
            pass
    prompt = f"""你是一个资深跨境电商运营专家。请根据以下商品信息提取结构化卖点。
商品名称：{product_name}
商品描述：{description}
品类：{category}
请严格按 JSON 格式输出：{{"core_keywords":[],"selling_points":[],"target_audience":"","usage_scenarios":[],"specs":{{}}}}"""
    try:
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
        resp = requests.post(f"{API_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```json"): raw = raw[7:]
        if raw.endswith("```"): raw = raw[:-3]
        highlights = json.loads(raw)
    except Exception:
        highlights = {"core_keywords":[product_name],"selling_points":["结实耐用","高性价比"],"target_audience":"大众","usage_scenarios":["日常"],"specs":{}}
    try:
        cache = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: cache = json.load(f)
        cache[f"{product_name}_{description}_{category}"] = highlights
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return highlights

MARKET_RISK = {"US":1,"UK":1,"DE":3,"FR":3,"JP":3}
CATEGORY_RISK = {"home":1,"electronics":3,"beauty":2,"baby":3,"food":3}

def classify_risk(market, category):
    s = MARKET_RISK.get(market,2) + CATEGORY_RISK.get(category,2) + st.session_state['violation_records'].get(f"{market}_{category}",0)*2
    if s >= 5: level, action = "高", "暂停输出，人工全审"
    elif s >= 3: level, action = "中", "异步复核（抽检20%）"
    else: level, action = "低", "直接通过（0审核）"
    return {"level": level, "action": action, "score": s}

def record_violation(market, category):
    vr = st.session_state['violation_records']
    vr[f"{market}_{category}"] = vr.get(f"{market}_{category}",0) + 1

class CircuitBreaker:
    def __init__(self):
        self.status='closed'; self.failures=0; self.last_failure_time=None
        self.total_requests=0; self.total_failures=0; self.consecutive_failures=0
    def check_circuit(self):
        self.total_requests += 1
        if self.status=='closed': return True
        if self.status=='open':
            if time.time()-self.last_failure_time > 3600: self.status='half-open'; return True
            return False
        return True
    def record_success(self):
        if self.status=='half-open': self.status='closed'; self.failures=0; self.consecutive_failures=0
        elif self.status=='closed': self.consecutive_failures=0; self.failures=max(0,self.failures-1)
    def record_failure(self):
        self.total_failures+=1; self.failures+=1; self.consecutive_failures+=1; self.last_failure_time=time.time()
        self.status='open' if (self.status=='half-open' or self.failures>=5) else self.status
    def reset(self):
        self.status='closed'; self.failures=0; self.consecutive_failures=0; self.last_failure_time=None; self.total_requests=0; self.total_failures=0

st.set_page_config(page_title="跨境Listing助手", page_icon="🌍", layout="wide")

# Streamlit 每次交互都会重跑整个脚本，模块级变量会被重建。
# 风险违规记录与熔断器必须挂在 session_state 上，否则跨次交互的状态会丢失（面板恒为 0）。
if 'violation_records' not in st.session_state:
    st.session_state['violation_records'] = {}
if 'breaker' not in st.session_state:
    st.session_state['breaker'] = CircuitBreaker()
breaker = st.session_state['breaker']

option = st.sidebar.radio("功能", ["📝 Listing生成","🔍 法规查询（RAG）","📊 风控面板"])

if option=="📝 Listing生成":
    st.title("🌍 跨境Listing智能生成系统")
    with st.sidebar:
        st.subheader("⚙️ API 设置")
        temp_key = st.text_input("API Key (DeepSeek/OpenAI)", type="password", value="")
        API_KEY = temp_key if temp_key else API_KEY
        st.subheader("🛡️ 风控配置")
        st.session_state['mkt'] = st.selectbox("目标市场",["US","UK","DE","FR","JP"],index=0)
        st.session_state['cat'] = st.selectbox("品类",["home","electronics","beauty","baby","food"],index=0)
        r = classify_risk(st.session_state['mkt'], st.session_state['cat'])
        col = {'高':'red','中':'orange','低':'green'}.get(r['level'],'gray')
        st.markdown(f"**风险等级:** <span style='color:{col};font-weight:bold'>{r['level']}</span>", unsafe_allow_html=True)
        st.info(f"{r['level']}风险 → {r['action']}")
    c1, c2 = st.columns([2,1])
    with c1:
        st.subheader("任务输入")
        task_target = st.selectbox("生成目标", ["TikTok Shop 标题+五点描述","Amazon 标题+五点描述","独立站商品详情"])
        kw = st.text_area("商品关键词/描述", "高颜值复古 中国风 结实耐用 陶瓷茶杯")
        brand = st.text_input("品牌名", "白牌")
        if st.button("✨ 开始智能生成", type="primary"):
            mkt = st.session_state.get('mkt','US'); cat = st.session_state.get('cat','home')
            if not breaker.check_circuit():
                st.error("⚠️ 服务熔断中，请稍后或重置熔断器"); st.stop()
            risk = classify_risk(mkt, cat)
            if risk['level']=='高':
                st.warning("⚠️ 高风险任务已拦截，请转交人工审核"); breaker.record_success(); st.stop()
            with st.spinner("Step 1: 提取商品卖点..."):
                try:
                    h = extract_highlights(brand, kw, cat)
                    st.success("✅ 卖点提取完成"); st.json(h)
                except Exception as e:
                    st.error(str(e)); breaker.record_failure(); st.stop()
            with st.spinner("Step 2: 撰写 Listing..."):
                try:
                    p = f"""你是跨境电商 Listing 专家。根据以下卖点为市场【{mkt}】写本地化 Listing。
目标：{task_target}
品牌:{brand} 关键词:{','.join(h.get('core_keywords',[]))} 卖点:{','.join(h.get('selling_points',[]))}
人群:{h.get('target_audience')} 场景:{','.join(h.get('usage_scenarios',[]))}
要求：标题150字符内含核心词；五点描述每点突出一个卖点；排版清晰符合平台规范。"""
                    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
                    payload = {"model": MODEL_NAME, "messages": [{"role":"user","content":p}], "temperature": 0.7}
                    resp = requests.post(f"{API_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=20)
                    resp.raise_for_status()
                    txt = resp.json()["choices"][0]["message"]["content"].strip()
                    st.success("🎉 生成成功"); st.markdown(txt); breaker.record_success()
                except Exception as e:
                    st.error(f"生成失败，请检查 API Key 和网络: {e}"); breaker.record_failure()
elif option=="📊 风控面板":
    st.title("📊 风控面板")
    a,b = st.columns(2)
    with a:
        sc={'closed':'green','open':'red','half-open':'orange'}; sn={'closed':'正常','open':'已熔断','half-open':'半开测试'}
        st.markdown(f"**状态:** <span style='color:{sc[breaker.status]};font-weight:bold'>{sn[breaker.status]}</span>", unsafe_allow_html=True)
        st.metric("总请求",breaker.total_requests); st.metric("总失败",breaker.total_failures)
        if st.button("重置熔断器"): breaker.reset(); st.success("✅ 已重置"); st.rerun()
    with b:
        st.subheader("违规记录登记")
        vm=st.selectbox("违规市场",["US","UK","DE","JP"],key="vm"); vc=st.selectbox("违规品类",["home","electronics","beauty","baby"],key="vc")
        if st.button("记录违规"): record_violation(vm,vc); st.success("已记录")
else:
    st.title("🔍 跨境法规查询（RAG）")
    st.caption("基于本地法规语料的检索式问答 · 当前语料条数见侧栏")
    with st.sidebar:
        st.subheader("🌍 法规检索设置")
        mkt = st.selectbox("目标市场",["JP","DE","FR","US","UK"], index=0, key="rag_mkt")
        cat = st.selectbox("品类",["ALL","electronics","beauty","baby","food","home"], index=0, key="rag_cat")
    @st.cache_resource
    def _get_retriever():
        return RegulationRetriever()
    retriever = _get_retriever()
    q = st.text_area("合规问题（例：日本销售的充电器需要什么认证？）", height=80, key="rag_q")
    if st.button("🔎 检索 + 回答", type="primary"):
        if not q.strip():
            st.warning("请先输入问题")
        elif not retriever.docs:
            st.error("语料为空。请先在 regulations/ 目录放入法规条目（见 regulations/法规收集手册.md）")
        else:
            hits = retriever.retrieve(q.strip(), market=mkt, category=cat, top_k=3)
            st.subheader("📚 命中条款（按相关度排序）")
            if not hits:
                st.info("未命中。可在语料中补充该市场/品类的条款。")
            else:
                for i, h in enumerate(hits, 1):
                    badge = "✅已核实" if h.get('verified') else "⚠️待核实"
                    with st.expander(f"[{i}] {badge} · {h['id']} · 相关度 {h['score']} · {h['title']}"):
                        st.write(h['text'])
                        st.caption(f"出处：{h['source']}")
                        if not h.get('verified'):
                            st.warning("本条尚未与官方原文核对，仅供检索定位，请勿直接作为合规依据。")
            if hits and API_KEY:
                with st.spinner("基于命中条款生成回答..."):
                    try:
                        prompt = build_prompt(q.strip(), hits, product_name="", market=mkt, category=cat)
                        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
                        payload = {"model": MODEL_NAME, "messages": [{"role":"user","content":prompt}], "temperature": 0.2}
                        resp = requests.post(f"{API_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=20)
                        resp.raise_for_status()
                        st.subheader("💡 回答")
                        st.markdown(resp.json()["choices"][0]["message"]["content"].strip())
                    except Exception as e:
                        st.error(f"生成失败：{e}")
            elif hits and not API_KEY:
                st.info("检测到命中条款，但未配置 API Key，请先在「Listing生成」侧栏填入。")

