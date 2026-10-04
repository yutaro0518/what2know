#!/usr/bin/env python3
"""feeds.json から SOURCES.md を生成（編集は feeds.json のみ）"""
import json
c = json.load(open("feeds.json", encoding="utf-8"))
order = ["総合", "政治", "経済", "国際", "テック", "AI", "科学"]
rows = sorted(c["sources"], key=lambda s: order.index(s["category"]) if s["category"] in order else 99)
out = ["# 参照ソースリスト", "", "`feeds.json` から自動生成（`python3 gen_sources.py`）。天気関連は `exclude_keywords` で除外。", "",
       "| カテゴリ | ソース | 言語 | 取得方法 | URL |", "|---|---|---|---|---|"]
out += [f"| {s['category']} | {s['name']} | {s['lang']} | {'ページ解析' if s.get('type') else 'RSS'} | {s['url']} |" for s in rows]
out += ["", "## 未対応", "- Bloomberg (JP): 公開RSSがないためトップページの見出しを解析（ページ構造が変わると取れなくなる）",
        "- 日本経済新聞: 公式RSSがないため、第三者ミラー（assets.wor.jp）経由。停止の可能性あり",
        "- 要約文はAIによる生成を含む。本文の転載はしない"]
open("SOURCES.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
