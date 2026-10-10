"""収集・選定・要約・描画のライブラリ。build.py（CLI）とtest_tuning.py（テスト）から使う。依存ライブラリなし。"""
import json, os, re, html, subprocess, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

# ---- 設定 ----
MAX_PICK = 12  # 1号に載せる本数の上限（profiles.jsonのpickがこれを超えても12本に丸める）
def load_cfg(path="feeds.json"):
    with open(path, encoding="utf-8") as f: return json.load(f)
def load_profile(name, path="profiles.json"):
    with open(path, encoding="utf-8") as f: p = json.load(f)
    if name not in p or name.startswith("_"):
        raise SystemExit(f"プロファイル '{name}' がありません。候補: {[k for k in p if not k.startswith('_')]}")
    p[name]["pick"] = min(p[name]["pick"], MAX_PICK)
    return p[name]

# ---- 収集 ----
def fetch(url):
    # macOSのPythonは証明書未設定のことがあるためcurlを使う
    return subprocess.run(["curl", "-sfL", "--max-time", "20", "-A", "Mozilla/5.0", url], capture_output=True, check=True).stdout

def nextdata_headlines(page, base):
    """Next.js製サイトのトップページから(見出し, URL)を取り出す。見出しとリンクのみ、本文は取得しない。"""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    out, seen = [], set()
    def walk(o):
        if isinstance(o, dict):
            h, u = o.get("headline") or o.get("title"), o.get("url")
            if isinstance(h, str) and isinstance(u, str) and "/news/articles/" in u:
                u = urljoin(base, u.split("?")[0])
                if u not in seen:
                    seen.add(u); out.append((h.strip(), u))
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    if m: walk(json.loads(m.group(1)))
    return out

def html_links(page, base, pattern):
    """RSSのない一覧ページから(見出し, URL)を取り出す。pattern に合うリンクのうち、文字のあるものだけ。"""
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(' + pattern + r')"[^>]*>(.*?)</a>', page, re.S):
        t = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        u = urljoin(base, m.group(1))
        if t and u not in seen:
            seen.add(u); out.append((t, u))
    return out

def parse_date(s):
    if not s: return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def collect(cfg, log=print):
    """全ソースから候補記事を集める。天気除外はここで行う（調整対象外の固定ルール）。"""
    items, ex = [], [k.lower() for k in cfg["exclude_keywords"]]
    focus = {cat: [k.lower() for k in ks] for cat, ks in cfg.get("focus_keywords", {}).items()}  # ジャンルごとの絞り込み（例 サッカーはPL・ラ・リーガ・日本/スペイン代表のみ）
    tag = lambda e: e.tag.rsplit("}", 1)[-1]
    def text(e, *names):
        for c in e:
            if tag(c) in names and (c.text or c.get("href")):
                return (c.text or c.get("href")).strip()
        return ""
    for src in cfg["sources"]:
        base = {"source": src["name"], "category": src["category"], "lang": src["lang"]}
        try:
            if src.get("type") in ("nextdata", "html_links"):
                page = fetch(src["url"]).decode("utf-8", "ignore")
                found = nextdata_headlines(page, src["url"]) if src["type"] == "nextdata" else html_links(page, src["url"], src["link_pattern"])
                for h, u in found[: cfg["per_source"] * 2]:
                    if not any(k in h.lower() for k in ex):
                        items.append({**base, "title": h, "desc": "", "link": u, "date": None})
                continue
            root = ET.fromstring(fetch(src["url"]))
        except Exception as e:
            log(f"skip {src['name']}: {e}"); continue
        n = 0
        for it in root.iter():
            if tag(it) not in ("item", "entry"): continue
            title = html.unescape(text(it, "title"))
            desc = html.unescape(re.sub(r"<[^>]+>", "", text(it, "description", "summary")))
            link = text(it, "link") or next((c.get("href") for c in it if tag(c) == "link" and c.get("href")), "")
            date = parse_date(text(it, "pubDate", "published", "updated", "date"))
            if any(k in (title + desc).lower() for k in ex): continue
            if src["category"] in focus and not any(k in (title + desc).lower() for k in focus[src["category"]]): continue
            items.append({**base, "title": title, "desc": desc, "link": link, "date": date.isoformat() if date else None})
            n += 1
            if n >= cfg["per_source"]: break
    seen, uniq = set(), []
    for i in items:
        if i["link"] and i["link"] not in seen:
            seen.add(i["link"]); uniq.append(i)
    return uniq

# ---- Worth Reading（社説・オピニオン。本編とは別枠） ----
def collect_opinion(cfg, now=None, days=14, log=print):
    now = now or datetime.now(timezone.utc)
    tag = lambda e: e.tag.rsplit("}", 1)[-1]
    out = []
    for src in cfg.get("opinion_sources", []):
        try: root = ET.fromstring(fetch(src["url"]))
        except Exception as e:
            log(f"skip {src['name']}: {e}"); continue
        for it in root.iter():
            if tag(it) not in ("item", "entry"): continue
            g = lambda *n: next(((c.text or c.get("href") or "").strip() for c in it if tag(c) in n and (c.text or c.get("href"))), "")
            d = parse_date(g("pubDate", "published", "updated", "date"))
            if d and d < now - timedelta(days=days): continue
            out.append({"source": src["name"], "title": html.unescape(g("title")), "desc": html.unescape(re.sub(r"<[^>]+>", "", g("description", "summary"))),
                        "link": g("link"), "date": d.isoformat() if d else None})
    return [o for o in out if o["link"] and o["title"]]

def rank_opinion(items, boost, n=4, max_per_source=1, source_weights=None):
    """APIキーなしの簡易順位づけ: 注目語（AI・テックなど）を含み、概要が長いものを優先し、媒体を分散。Claudeがある場合は判断を任せる。"""
    boost = [k.lower() for k in boost]
    def score(o):
        t = (o["title"] + " " + o["desc"]).lower()
        return (sum(1 for k in boost if re.search(r"\b" + re.escape(k) + r"\b", t)) * 2 + min(len(o["desc"]), 300) / 150
                + (source_weights or {}).get(o["source"], 0))
    out, per = [], {}
    for o in sorted(items, key=score, reverse=True):
        if per.get(o["source"], 0) < max_per_source:
            out.append(o); per[o["source"]] = per.get(o["source"], 0) + 1
        if len(out) >= n: break
    return out

# ---- 話題の判定・クラスタリング ----
TOPIC_RULES = {  # タイトル/概要に合致したらジャンルを上書き
    "AI": re.compile(r"\bA\.?I\.?\b|openai|anthropic|chatgpt|\bllm|gpt-\d|生成ai|人工知能|オープンai|エージェント|\bmuse\b", re.I),
}
ALIASES = {"オープンai": "openai", "ベッセント": "bessent", "フライドバイ": "flydubai", "キーウ": "kyiv",
           "ルーラ": "lula", "ボルソナロ": "bolsonaro", "イラン": "iran", "ブラジル": "brazil", "ロシア": "russia",
           "ウクライナ": "ukraine", "トランプ": "trump", "メタ": "meta", "アンソロピック": "anthropic", "ロビンソン": "robinson", "デビッド": "david", "副操縦士": "co-pilot", "斧": "ax", "ブルームバーグ": "bloomberg", "ふるさと納税": "furusato"}
STOP = set("""this that with from have will after about they their said says into over more than what when which while were been also would could first last news 2026 government capital markets market president states state week world officials official people leader leaders ahead amid under over
trump's biden says say plans plan report reports warns warn shows show calls call talks deal former major new more most
energy bills pressure suppliers company companies bank banks business economy economic national global public house white
""".split())

def signature(i):
    """話題の指紋。見出し中の固有語＋別名辞書で正規化した語（概要の語は一般語が多くノイズになるため使わない）。"""
    toks = {w for w in re.findall(r"[a-z0-9][a-z0-9\-]{3,}", i["title"].lower()) if w not in STOP}
    toks |= set(re.findall(r"[ァ-ヴー]{3,}", i["title"])) | set(re.findall(r"[一-龥]{2,}", i["title"]))
    low = (i["title"] + i["desc"]).lower()
    return {ALIASES.get(w, w) for w in toks} | {v for k, v in ALIASES.items() if k in low or v in low}

def proper_nouns(i):
    """見出しの固有名詞（文頭以外の大文字語、カタカナ語）と別名辞書の正規化語。1語だけの一致で同一話題と判定してよいのはこれだけ。"""
    words = re.findall(r"[A-Za-z][A-Za-z\-]+", i["title"])
    out = {w.lower() for w in words[1:] if w[0].isupper() and len(w) >= 6}
    out |= set(re.findall(r"[ァ-ヴー]{4,}", i["title"]))
    low = (i["title"] + i["desc"]).lower()
    return out | {v for k, v in ALIASES.items() if k in low or v in low}

def effective_category(i):
    return "AI" if TOPIC_RULES["AI"].search(i["title"] + " " + i["desc"]) else i["category"]

def cluster(items, min_shared=2, max_df=0.06):
    """同じ話題を報じた記事をまとめる。共通する固有語が2つ以上で、最初の記事(シード)と比べる方式。
    連鎖でまとまり過ぎないよう、全記事の6%超に出る語（trump, openaiなど）は一致の根拠から外す。"""
    sigs = [signature(i) for i in items]
    propers = [proper_nouns(i) for i in items]
    df = {}
    for sg in sigs:
        for w in sg: df[w] = df.get(w, 0) + 1
    limit = max(3, int(len(items) * max_df))
    sigs = [{w for w in sg if df[w] <= limit} for sg in sigs]
    seeds, groups, seed_prop = [], [], []  # seeds[k]: groups[k]のシグネチャ
    for k, i in enumerate(items):
        for g, sd in enumerate(seeds):
            shared = sigs[k] & sd
            # 共通語が2つ以上、または珍しい長い固有語（flydubai, bolsonaroなど）が1つあれば同一話題
            if len(shared) >= min_shared or any(df[w] <= 8 and w in propers[k] and w in seed_prop[g] for w in shared):
                groups[g].append(i); break
        else:
            seeds.append(sigs[k]); groups.append([i]); seed_prop.append(propers[k])
    return groups

# ---- 選定（つまみで調整） ----
def select(items, profile, now=None, noise=(), source_weights=None):
    """noise: 広告・セール・まとめ記事などを落とす語 / source_weights: 媒体ごとの重み（例 自社ブログは0.3）"""
    now = now or datetime.now(timezone.utc)
    source_weights = source_weights or {}
    noise = [k.lower() for k in noise]
    items = [i for i in items if not any(k in i["title"].lower() for k in noise)]
    w = profile["category_weights"]
    cut = now - timedelta(hours=profile["max_age_hours"])
    fresh = [i for i in items if not i.get("date") or datetime.fromisoformat(i["date"]) >= cut]
    boost = [k.lower() for k in profile.get("boost_keywords", [])]
    cands = []
    for g in cluster(fresh):
        members = [dict(m, category=effective_category(m)) for m in g]
        members = [m for m in members if w.get(m["category"], 1.0) > 0]
        if not members: continue
        n_src = len({m["source"] for m in members})
        freq = {}
        for m in members: freq[m["category"]] = freq.get(m["category"], 0) + 1
        top = max(members, key=lambda m: (w.get(m["category"], 1.0), freq[m["category"]], len(m["desc"])))
        sw = max(source_weights.get(m["source"], 1.0) for m in members)
        score = w.get(top["category"], 1.0) * sw * (1 + profile["coverage_weight"] * (n_src - 1))
        if any(k in " ".join(m["title"] for m in members).lower() for k in boost): score *= 1.5
        rep = next((m for m in members if m["lang"] == "ja" and m["category"] == top["category"]), top)
        cands.append({"category": top["category"], "score": score, "sources": sorted({m["source"] for m in members}),
                      "rep": rep, "members": members})
    cands.sort(key=lambda c: -c["score"])
    chosen, per_cat, per_src = [], {}, {}
    def ok(c):
        if per_cat.get(c["category"], 0) >= profile["max_per_category"].get(c["category"], 99): return False
        return all(per_src.get(s, 0) < profile["max_per_source"] for s in c["sources"][:1])
    def take(c):
        chosen.append(c); per_cat[c["category"]] = per_cat.get(c["category"], 0) + 1
        per_src[c["sources"][0]] = per_src.get(c["sources"][0], 0) + 1
    for cat, need in profile["min_per_category"].items():  # 最低本数を先に満たす
        for c in [c for c in cands if c["category"] == cat]:
            if per_cat.get(cat, 0) >= need or len(chosen) >= profile["pick"]: break
            if c not in chosen and ok(c): take(c)
    for c in cands:
        if len(chosen) >= profile["pick"]: break
        if c not in chosen and ok(c): take(c)
    return sorted(chosen, key=lambda c: -c["score"])

# ---- 要約 ----
def to_story(c):
    """APIキーなしの簡易整形。見出し＝代表記事、要点＝各媒体の概要（最大3つ）。"""
    pts = []
    for m in c["members"]:
        if m["desc"] and m["desc"] not in pts: pts.append(m["desc"])
    return {"headline": c["rep"]["title"], "points": pts[:3], "links": [m["link"] for m in c["members"]][:5]}

def summarize_with_claude(chosen, key):
    """選定済みの話題を日本語で要約する（事実は候補テキストの範囲のみ）。"""
    blocks = "\n\n".join(f"[{k}] " + "\n".join(f"- ({m['source']}) {m['title']} | {m['desc']}" for m in c["members"][:6])
                         for k, c in enumerate(chosen))
    prompt = ("以下は話題ごとの記事見出しと概要です。各話題を日本語の見出し1つと要点2〜3個にまとめてください。"
              "書かれていない事実は足さない。JSONのみ出力: "
              '[{"headline":"...","points":["..."]}]（話題の順番を保つ）\n\n' + blocks)
    body = json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body,
        {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    text = json.load(urllib.request.urlopen(req, timeout=120))["content"][0]["text"]
    data = json.loads(text[text.index("["): text.rindex("]") + 1])
    return [{**d, "links": to_story(c)["links"]} for d, c in zip(data, chosen)]

# ---- 描画（ダークモードのみ） ----
FONTS = ("<link rel=preconnect href='https://fonts.googleapis.com'><link rel=preconnect href='https://fonts.gstatic.com' crossorigin>"
         "<link href='https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700&family=Noto+Sans+JP:wght@400;500;700&display=swap' rel=stylesheet>")
BASE_CSS = """
:root{--bg:#121212;--fg:#f2f2f2;--muted:#a3a3a3;--accent:#8b9be0;--line:#4a5fa8;--rule:#2c2c2c;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:Manrope,'Noto Sans JP',-apple-system,'Hiragino Sans',sans-serif;line-height:1.8;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
"""
INDEX_CSS = BASE_CSS + """
main{max-width:1060px;margin:0 auto;padding:130px 24px 120px}
h1{font-size:2.1rem;line-height:1.3;margin:0 0 1.6rem;font-weight:700;letter-spacing:.01em}
.lead{color:#b5b5b5;font-size:1.1rem;line-height:2;margin:0 0 5.5rem}
.feed{display:grid;grid-template-columns:140px 1fr;gap:0 24px}
.label{color:var(--accent);font-size:1.05rem;padding-top:.15rem}
ol{list-style:none;margin:0;padding:0 0 0 0;border-left:1px solid var(--line)}
li{display:grid;grid-template-columns:150px 1fr;gap:0 24px;padding:0 0 3.2rem 0}
time{text-align:right;color:var(--accent);font-size:.92rem;padding-top:.25rem;font-variant-numeric:tabular-nums;letter-spacing:.02em}
li h2{font-size:1.28rem;line-height:1.5;margin:0 0 .9rem;font-weight:700}
li a:hover h2{color:var(--accent)}
li p{margin:0;color:var(--muted);font-size:.97rem;line-height:1.95}
@media(max-width:760px){main{padding:72px 20px 80px}.lead{margin-bottom:3rem}.feed{grid-template-columns:1fr}.label{margin-bottom:1.2rem}ol{border-left:0}li{grid-template-columns:1fr;padding-bottom:2.4rem}time{text-align:left;margin-bottom:.4rem}}
"""
ISSUE_CSS = BASE_CSS + """
main{max-width:760px;margin:0 auto;padding:72px 24px 120px}
.back{color:var(--accent);font-size:.9rem}
h1{font-size:1.7rem;line-height:1.35;margin:1.6rem 0 2.4rem;font-weight:700}
h2{font-size:1.15rem;line-height:1.55;margin:2.6rem 0 .8rem;font-weight:700}
ul{margin:0;padding-left:1.2rem;color:#d6d6d6}li{margin:.35rem 0}
.src{margin:.7rem 0 0;font-size:.85rem;color:var(--muted)}.src a{color:var(--accent);margin-right:.9rem}
.worth{margin-top:4rem;border-top:1px solid var(--rule);padding-top:1.4rem}.worth h2{margin-top:0}
.worth li{margin:0 0 1.3rem;list-style:none}.worth ul{padding:0}.worth a{color:var(--accent)}.worth .by{color:var(--muted);font-size:.85rem}.worth p{margin:.2rem 0 0;color:#cfcfcf;font-size:.95rem}
footer{margin-top:4rem;border-top:1px solid var(--rule);padding-top:1rem;color:#7a7a7a;font-size:.8rem}
"""
HEAD = "<!doctype html><html lang=ja><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><meta name=robots content='noindex,nofollow'><meta name=color-scheme content=dark>"

def render(stories, title, site_title, worth=()):
    body = ""
    for n, s in enumerate(stories, 1):
        pts = "".join(f"<li>{html.escape(p)}</li>" for p in s["points"])
        lks = "".join(f'<a href="{html.escape(l)}">Source {k}</a>' for k, l in enumerate(s["links"], 1))
        body += f"<h2>{n}. {html.escape(s['headline'])}</h2><ul>{pts}</ul><p class=src>{lks}</p>"
    if worth:
        body += "<section class=worth><h2>Worth Reading</h2><ul>"
        for w in worth:
            body += (f"<li><a href=\"{html.escape(w['link'])}\">{html.escape(w['title'])}</a> <span class=by>— {html.escape(w['source'])}</span>"
                     f"<p>{html.escape(w.get('blurb',''))}</p></li>")
        body += "</ul></section>"
    return (f"{HEAD}<title>{html.escape(title)}</title>{FONTS}<style>{ISSUE_CSS}</style><main><a class=back href=\"../\">&larr; {html.escape(site_title)}</a>"
            f"<h1>{html.escape(title)}</h1>{body}<footer>Summaries are AI-generated. See the sources for details.</footer></main>")

def issue_title(today, edition):
    label = {"morning": "Morning", "evening": "Evening"}.get(edition, edition.capitalize())
    return f"What to know on the {label} of {today.strftime('%B')} {today.day}, {today.year}"

def render_index(cfg, site_dir="site"):
    """site/paper/ の各号から、日付・タイトル・冒頭の話題を拾って一覧ページを作る。"""
    rows = []
    order = lambda f: (f[:8], {"morning": 0, "evening": 1}.get(f[9:].split(".")[0], 0))
    for f in sorted(os.listdir(f"{site_dir}/paper"), key=order, reverse=True):
        if not f.endswith(".html"): continue
        doc = open(f"{site_dir}/paper/{f}", encoding="utf-8").read()
        m = re.match(r"(\d{4})(\d{2})(\d{2})-", f)
        if not m: continue
        t = re.search(r"<h1>(.*?)</h1>", doc, re.S)
        heads = [html.unescape(h) for h in re.findall(r"<h2>\d+\. (.*?)</h2>", doc, re.S)][:3]
        ex = " / ".join(heads)
        ex = ex if len(ex) <= 150 else ex[:150].rstrip() + "…"
        rows.append((f"{m[1]}.{m[2]}.{m[3]}", t.group(1) if t else f, f"paper/{f}", ex))
    items = "".join(f"<li><time>{d}</time><div><a href=\"{href}\"><h2>{t}</h2></a><p>{html.escape(ex)}</p></div></li>" for d, t, href, ex in rows)
    return (f"{HEAD}<title>{html.escape(cfg['title'])}</title>{FONTS}<style>{INDEX_CSS}</style><main>"
            f"<h1>{html.escape(cfg['title'])}</h1><p class=lead>Here's what to know about the world today.</p>"
            f"<section class=feed><div class=label>Latest</div><ol>{items}</ol></section></main>")


# ---- リンク検査・サイト書き出し ----
ALIVE_UNKNOWN = {401, 403, 429, 999}  # 有料サイトはボット判定で弾くため「生きているが確認不能」として扱う

def link_status(url):
    """HTTPステータスを返す（取得不能は0）。HEADを拒否するサイトにはGETでやり直す。"""
    def run(*extra):
        r = subprocess.run(["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", "-A", "Mozilla/5.0", *extra, url],
                           capture_output=True, text=True)
        return int(r.stdout.strip() or 0)
    code = run("-I")
    return run() if code in (0, 400, 403, 405, 501) else code

def check_links(urls, workers=12):
    """{url: (ok, status)}。404/410/5xx/接続失敗はNG。"""
    from concurrent.futures import ThreadPoolExecutor
    urls = list(dict.fromkeys(urls))
    with ThreadPoolExecutor(workers) as ex:
        codes = list(ex.map(link_status, urls))
    return {u: ((200 <= c < 400) or c in ALIVE_UNKNOWN, c) for u, c in zip(urls, codes)}

def drop_dead_links(stories, worth, log=print):
    """死んだリンクを外す。出典が1つも残らない話題は落とす。"""
    allurls = [l for s in stories for l in s["links"]] + [w["link"] for w in worth]
    res = check_links(allurls)
    for u, (ok, c) in res.items():
        if not ok: log(f"リンク切れ({c}): {u}")
    for s in stories: s["links"] = [l for l in s["links"] if res[l][0]]
    kept = [s for s in stories if s["links"]]
    for s in stories:
        if not s["links"]: log(f"出典が全て切れたため話題を削除: {s['headline']}")
    return kept, [w for w in worth if res[w["link"]][0]]

def write_site(stories, worth, edition, cfg, today):
    title = issue_title(today, edition)
    os.makedirs("site/paper", exist_ok=True)
    stamp = today.strftime("%Y%m%d")
    page = f"site/paper/{stamp}-{edition}.html"
    doc = render(stories, title, cfg["title"], worth)
    open(page, "w", encoding="utf-8").write(doc)
    os.makedirs("email", exist_ok=True)  # メール用は公開サイトに置かない
    open(f"email/{stamp}-{edition}.html", "w", encoding="utf-8").write(doc)
    open("site/index.html", "w", encoding="utf-8").write(render_index(cfg))
    return page
