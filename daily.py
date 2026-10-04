#!/usr/bin/env python3
"""毎朝の発行フロー（Claudeが編集者として回す想定）。
  python3 daily.py prepare                      # 収集して work/YYYYMMDD/ に候補とブリーフを書く
  python3 daily.py publish work/YYYYMMDD/stories.json   # 検証→リンク検査→HTML生成
  python3 daily.py deploy                       # site/ をGitHubにpush（Pagesで公開）
stories.json は {"stories":[{headline,points,links}], "worth_reading":[{title,source,link,blurb}]}
links は必ず candidates.json / opinion.json にあるURLだけ（推測で書いたURLは publish が拒否する）。"""
import datetime, json, os, sys
import newsletter as nl

cfg = nl.load_cfg()
today = datetime.date.today()
work = f"work/{today.strftime('%Y%m%d')}"

def prepare():
    os.makedirs(work, exist_ok=True)
    items = nl.collect(cfg, log=lambda m: print(m, file=sys.stderr))
    ops = nl.collect_opinion(cfg, log=lambda m: print(m, file=sys.stderr))
    json.dump(items, open(f"{work}/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(ops, open(f"{work}/opinion.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    prof = nl.load_profile("default"); prof["pick"] = 30
    chosen = nl.select(items, prof, noise=cfg["noise_keywords"], source_weights={s["name"]: s["weight"] for s in cfg["sources"] if "weight" in s})
    out = [f"# ブリーフ {today}（候補{len(items)}件 / オピニオン{len(ops)}件）", "", "## 複数媒体が報じた話題（自動クラスタ。誤結合あり、必ず中身を読んで判断）"]
    for k, c in enumerate(chosen, 1):
        out.append(f"\n### {k}. [{c['category']}] 媒体{len(c['sources'])} 得点{c['score']:.1f}")
        for m in c["members"][:5]:
            out.append(f"- ({m['source']}) {m['title']} | {m["desc"][:120]} | {m['link']}")
    for cat in ("AI", "テック", "サッカー"):
        out.append(f"\n## {cat}（ジャンル別の全候補）")
        for i in items:
            if nl.effective_category(i) == cat and not any(n in i["title"].lower() for n in cfg["noise_keywords"]):
                out.append(f"- ({i['source']}) {i['title']} | {i['desc'][:140]} | {i['link']}")
    out.append("\n## Worth Reading候補（社説・オピニオン）")
    for o in ops:
        out.append(f"- ({o['source']}) {o['title']} | {o['desc'][:140]} | {o['link']}")
    open(f"{work}/brief.md", "w", encoding="utf-8").write("\n".join(out))
    print(f"{work}/brief.md を書きました（{len(items)}件 / オピニオン{len(ops)}件）")
    per = {}
    for i in items: per[i["source"]] = per.get(i["source"], 0) + 1
    zero = [s["name"] for s in cfg["sources"] if per.get(s["name"], 0) == 0]
    print("ソース別件数:", ", ".join(f"{k}={v}" for k, v in sorted(per.items())))
    if zero: print("::warning::取得0件のソース: " + ", ".join(zero))

def publish(path):
    data = json.load(open(path, encoding="utf-8"))
    stories, worth = data["stories"], data.get("worth_reading", [])
    pool = {i["link"].split("?")[0] for i in json.load(open(f"{work}/candidates.json", encoding="utf-8"))}
    pool |= {o["link"].split("?")[0] for o in json.load(open(f"{work}/opinion.json", encoding="utf-8"))}
    unknown = [l for s in stories for l in s["links"] if l.split("?")[0] not in pool] + [w["link"] for w in worth if w["link"].split("?")[0] not in pool]
    if unknown: sys.exit("収集結果にないURLがあります（推測で書いていませんか）:\n" + "\n".join(unknown))
    stories, worth = nl.drop_dead_links(stories, worth, log=lambda m: print(m, file=sys.stderr))
    print(f"話題{len(stories)}本 / Worth Reading {len(worth)}本")
    print("生成:", nl.write_site(stories, worth, "morning", cfg, today))

def deploy():
    """site/ をコミットして main にpush。GitHub Actionsが Pages に公開する。"""
    import subprocess
    run = lambda *a: subprocess.run(a, capture_output=True, text=True)
    run("git", "add", "site")
    if run("git", "diff", "--cached", "--quiet").returncode == 0:
        print("変更なし。pushしません"); return
    msg = f"Daily Brief {today.isoformat()}\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
    r = run("git", "commit", "-m", msg)
    if r.returncode: sys.exit(r.stderr or r.stdout)
    r = run("git", "pull", "--rebase", "origin", "main")
    r = run("git", "push", "origin", "main")
    if r.returncode: sys.exit("pushに失敗:\n" + r.stderr)
    print("公開: https://yutaro0518.github.io/what2know/")

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "prepare": prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == "publish": publish(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "deploy": deploy()
    else: sys.exit(__doc__)
