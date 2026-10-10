#!/usr/bin/env python3
"""毎朝の発行フロー（Claudeが編集者として回す想定）。
  python3 daily.py prepare [morning|evening]   # 収集して work/YYYYMMDD-<edition>/ に候補とブリーフを書く
  python3 daily.py publish work/YYYYMMDD-<edition>/stories.json [edition]   # 検証→リンク検査→HTML生成
  python3 daily.py deploy [edition]            # site/ をGitHubにpush（Pagesで公開）
edition を省略すると、現在時刻（12時前=morning、以降=evening）で決まる。
stories.json は {"stories":[{headline,points,links}], "worth_reading":[{title,source,link,blurb}]}
links は必ず candidates.json / opinion.json にあるURLだけ（推測で書いたURLは publish が拒否する）。"""
import datetime, json, os, sys
import newsletter as nl

cfg = nl.load_cfg()
# 過去号の作り直し用: ISSUE_DATE=2026-10-03 ISSUE_AS_OF=2026-10-03T08:00:00+09:00 python3 daily.py prepare morning
today = datetime.date.fromisoformat(os.environ["ISSUE_DATE"]) if os.environ.get("ISSUE_DATE") else datetime.date.today()
AS_OF = datetime.datetime.fromisoformat(os.environ["ISSUE_AS_OF"]) if os.environ.get("ISSUE_AS_OF") else None

def current_edition():
    """朝刊(8:00)=12時前に作る / 夕刊(18:00)=12時以降。引数で上書き可。"""
    return "morning" if datetime.datetime.now().hour < 12 else "evening"

def workdir(edition): return f"work/{today.strftime('%Y%m%d')}-{edition}"

def prepare(edition):
    work = workdir(edition)
    os.makedirs(work, exist_ok=True)
    log = lambda m: print(m, file=sys.stderr)
    if AS_OF:  # 過去号: RSSを深めに取り、公開時刻より前の記事だけを残す（日付のない記事は時点が不明なので除外）
        deep = {**cfg, "per_source": 40}
        items = [i for i in nl.collect(deep, log=log) if i["date"] and AS_OF - datetime.timedelta(hours=72) <= datetime.datetime.fromisoformat(i["date"]) <= AS_OF]
        ops = [o for o in nl.collect_opinion(cfg, now=AS_OF, days=21, log=log) if not o["date"] or datetime.datetime.fromisoformat(o["date"]) <= AS_OF]
    else:
        items = nl.collect(cfg, log=log)
        ops = nl.collect_opinion(cfg, log=log)
    json.dump(items, open(f"{work}/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(ops, open(f"{work}/opinion.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    prof = nl.load_profile("default"); prof["pick"] = 30
    chosen = nl.select(items, prof, now=AS_OF, noise=cfg["noise_keywords"], source_weights={s["name"]: s["weight"] for s in cfg["sources"] if "weight" in s})
    out = [f"# ブリーフ {today} {edition}（候補{len(items)}件 / オピニオン{len(ops)}件）", ""]
    if edition == "evening":
        out += ["**夕刊（18:00号）です。** 朝刊からの続報・新しい出来事を中心に選ぶこと。朝刊と同じ話題は、新しい展開がある場合だけ取り上げ、その展開を書く。", "", "## 今朝の朝刊の話題（重複を避ける）"]
        mp = f"site/paper/{today.strftime('%Y%m%d')}-morning.html"
        if os.path.exists(mp):
            import re, html as _h
            doc = open(mp, encoding="utf-8").read()
            out += [f"- {_h.unescape(h)}" for h in re.findall(r"<h2>\d+\. (.*?)</h2>", doc)]
        else:
            out.append("- （朝刊が見つかりません）")
        out.append("")
    out += ["## 複数媒体が報じた話題（自動クラスタ。誤結合あり、必ず中身を読んで判断）"]
    for k, c in enumerate(chosen, 1):
        out.append(f"\n### {k}. [{c['category']}] 媒体{len(c['sources'])} 得点{c['score']:.1f}")
        for m in c["members"][:5]:
            out.append(f"- ({m['source']}) {m['title']} | {m['desc'][:120]} | {m['link']}")
    for cat in ("AI", "テック", "サッカー"):
        out.append(f"\n## {cat}（ジャンル別の全候補）")
        for i in items:
            if nl.effective_category(i) == cat and not any(n in i["title"].lower() for n in cfg["noise_keywords"]):
                out.append(f"- ({i['source']}) {i['title']} | {i['desc'][:140]} | {i['link']}")
    out.append("\n## Worth Reading候補（社説・オピニオン）")
    out.append("**推薦順（AI×人文・仕事・キャリア・社会の論考を優先、媒体は分散）。まずここから選び、残りの一覧も見ること。**")
    top = nl.rank_opinion(ops, cfg.get("opinion_boost_keywords", []), n=25, max_per_source=5, source_weights=cfg.get("opinion_source_weights"))
    for o in top:
        out.append(f"- ★ ({o['source']}) {o['title']} | {o['desc'][:140]} | {o['link']}")
    out.append("\n### その他の候補")
    seen = {o["link"] for o in top}
    for o in ops:
        if o["link"] not in seen:
            out.append(f"- ({o['source']}) {o['title']} | {o['desc'][:140]} | {o['link']}")
    open(f"{work}/brief.md", "w", encoding="utf-8").write("\n".join(out))
    print(f"{work}/brief.md を書きました（{len(items)}件 / オピニオン{len(ops)}件）")
    per = {}
    for i in items: per[i["source"]] = per.get(i["source"], 0) + 1
    zero = [s["name"] for s in cfg["sources"] if per.get(s["name"], 0) == 0]
    print("ソース別件数:", ", ".join(f"{k}={v}" for k, v in sorted(per.items())))
    if zero: print("::warning::取得0件のソース: " + ", ".join(zero))

def publish(path, edition):
    work = workdir(edition)
    data = json.load(open(path, encoding="utf-8"))
    stories, worth = data["stories"], data.get("worth_reading", [])
    pool = {i["link"].split("?")[0] for i in json.load(open(f"{work}/candidates.json", encoding="utf-8"))}
    pool |= {o["link"].split("?")[0] for o in json.load(open(f"{work}/opinion.json", encoding="utf-8"))}
    unknown = [l for s in stories for l in s["links"] if l.split("?")[0] not in pool] + [w["link"] for w in worth if w["link"].split("?")[0] not in pool]
    if unknown: sys.exit("収集結果にないURLがあります（推測で書いていませんか）:\n" + "\n".join(unknown))
    stories, worth = nl.drop_dead_links(stories, worth, log=lambda m: print(m, file=sys.stderr))
    print(f"話題{len(stories)}本 / Worth Reading {len(worth)}本")
    print("生成:", nl.write_site(stories, worth, edition, cfg, today))

def deploy(edition):
    """site/ をコミットして main にpush。GitHub Actionsが Pages に公開する。"""
    import subprocess
    run = lambda *a: subprocess.run(a, capture_output=True, text=True)
    run("git", "add", "site")
    if run("git", "diff", "--cached", "--quiet").returncode == 0:
        print("変更なし。pushしません"); return
    msg = f"What to know: {edition} {today.isoformat()}\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
    r = run("git", "commit", "-m", msg)
    if r.returncode: sys.exit(r.stderr or r.stdout)
    r = run("git", "pull", "--rebase", "origin", "main")
    r = run("git", "push", "origin", "main")
    if r.returncode: sys.exit("pushに失敗:\n" + r.stderr)
    print("公開: https://yutaro0518.github.io/what2know/")

if __name__ == "__main__":
    ed = lambda i: sys.argv[i] if len(sys.argv) > i else current_edition()
    if len(sys.argv) >= 2 and sys.argv[1] == "prepare": prepare(ed(2))
    elif len(sys.argv) >= 3 and sys.argv[1] == "publish": publish(sys.argv[2], ed(3))
    elif len(sys.argv) >= 2 and sys.argv[1] == "deploy": deploy(ed(2))
    else: sys.exit(__doc__)
