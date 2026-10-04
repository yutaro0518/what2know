#!/usr/bin/env python3
"""収集 → 選定(profiles.jsonのつまみ) → 要約 → HTML生成。
  python3 build.py [morning|evening] [--profile 名前] [--dry-run] [--stories stories.json] [--candidates cands.json]
--dry-run : 選定結果と得点だけを表示（チューニング用。ファイルは作らない）
--stories : 要約済みJSONを使う（APIキーなしで手書き要約を流し込む用）
--candidates : 収集をスキップして保存済みの候補JSONを使う"""
import argparse, datetime, json, os, sys
import newsletter as nl

ap = argparse.ArgumentParser()
ap.add_argument("edition", nargs="?", default="morning")
ap.add_argument("--profile", default="default")
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--stories")
ap.add_argument("--candidates")
ap.add_argument("--save-candidates")
ap.add_argument("--check-links", action="store_true", help="公開前にリンクを検査し、切れたものを外す")
a = ap.parse_args()

cfg, profile = nl.load_cfg(), nl.load_profile(a.profile)
items = json.load(open(a.candidates, encoding="utf-8")) if a.candidates else nl.collect(cfg, log=lambda m: print(m, file=sys.stderr))
if a.save_candidates: json.dump(items, open(a.save_candidates, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
if not items: sys.exit("記事を取得できませんでした")
chosen = nl.select(items, profile, noise=cfg.get("noise_keywords", []),
                   source_weights={s["name"]: s["weight"] for s in cfg["sources"] if "weight" in s})

if a.dry_run:
    print(f"プロファイル: {a.profile} / 候補{len(items)}件 / 選定{len(chosen)}本")
    for k, c in enumerate(chosen, 1):
        print(f"{k}. [{c['category']}] 得点{c['score']:.1f} 媒体{len(c['sources'])} {c['rep']['title'][:60]}")
        print(f"     {', '.join(c['sources'])}")
    sys.exit()

key = os.environ.get("ANTHROPIC_API_KEY")
worth = []
if a.stories:
    data = json.load(open(a.stories, encoding="utf-8"))
    stories, worth = (data["stories"], data.get("worth_reading", [])) if isinstance(data, dict) else (data, [])
else:
    stories = nl.summarize_with_claude(chosen, key) if key else [nl.to_story(c) for c in chosen]
    n_worth = profile.get("worth_reading", 0)
    if n_worth:
        ops = nl.rank_opinion(nl.collect_opinion(cfg), cfg.get("opinion_boost_keywords", []), n=n_worth)
        worth = [{"title": o["title"], "source": o["source"], "link": o["link"], "blurb": o["desc"][:140]} for o in ops]

today = datetime.date.today()
if a.check_links: stories, worth = nl.drop_dead_links(stories, worth, log=lambda m: print(m, file=sys.stderr))
print("生成:", nl.write_site(stories, worth, a.edition, cfg, today))
