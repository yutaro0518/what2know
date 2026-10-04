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

def rank_opinion(items, boost, n=4, max_per_source=1):
    """APIキーなしの簡易順位づけ: 注目語（AI・テックなど）を含み、概要が長いものを優先し、媒体を分散。Claudeがある場合は判断を任せる。"""
    boost = [k.lower() for k in boost]
    def score(o):
        t = (o["title"] + " " + o["desc"]).lower()
        return sum(1 for k in boost if re.search(r"\b" + re.escape(k) + r"\b", t)) * 2 + min(len(o["desc"]), 300) / 150
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

# ---- 描画 ----
CSS = "body{font-family:-apple-system,'Hiragino Sans',sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;line-height:1.7;color:#222}h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:2rem}a{color:#0a58ca}"
def render(stories, title, site_title, worth=()):
    body = ""
    for n, s in enumerate(stories, 1):
        pts = "".join(f"<li>{html.escape(p)}</li>" for p in s["points"])
        lks = " ".join(f'<a href="{html.escape(l)}">出典</a>' for l in s["links"])
        body += f"<h2>{n}. {html.escape(s['headline'])}</h2><ul>{pts}</ul><p>{lks}</p>"
    if worth:
        body += "<h2 style='margin-top:3rem;border-top:2px solid #222;padding-top:1rem'>Worth Reading</h2><ul style='padding-left:1.2rem'>"
        for w in worth:
            body += (f"<li style='margin-bottom:1rem'><a href=\"{html.escape(w['link'])}\">{html.escape(w['title'])}</a>"
                     f" <span style='color:#777;font-size:.85rem'>— {html.escape(w['source'])}</span><br>{html.escape(w.get('blurb',''))}</li>")
        body += "</ul>"
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><meta name=robots content='noindex,nofollow'><title>{title}</title>"
            f"<style>{CSS}</style><h1>{title}</h1>{body}<hr><p style='font-size:.8rem;color:#777'>{site_title} / AIによる要約を含みます。詳細は出典をご確認ください。</p>")


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
    label = {"morning": "朝", "evening": "夕"}.get(edition, edition)
    title = f"{today.year}年{today.month}月{today.day}日 {label}の注目ニュース"
    os.makedirs("site/paper", exist_ok=True)
    stamp = today.strftime("%Y%m%d")
    page = f"site/paper/{stamp}-{edition}.html"
    doc = render(stories, title, cfg["title"], worth)
    open(page, "w", encoding="utf-8").write(doc)
    os.makedirs("email", exist_ok=True)  # メール用は公開サイトに置かない
    open(f"email/{stamp}-{edition}.html", "w", encoding="utf-8").write(doc)
    idx = sorted(os.listdir("site/paper"))[::-1]
    open("site/index.html", "w", encoding="utf-8").write(
        f"<!doctype html><meta charset=utf-8><meta name=robots content='noindex,nofollow'><title>{cfg['title']}</title><body style='font-family:sans-serif;max-width:640px;margin:2rem auto'><h1>{cfg['title']}</h1><ul>"
        + "".join(f"<li><a href='paper/{f}'>{f[:-5]}</a></li>" for f in idx) + "</ul>")
    return page
