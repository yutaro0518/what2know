#!/usr/bin/env python3
"""Claude API（編集者役）で work/YYYYMMDD/stories.json を作る。GitHub Actionsで毎朝回す用。
  ANTHROPIC_API_KEY=... python3 agent_edit.py
brief.md と EDITORIAL.md を渡し、stories.json を生成。収集結果にないURLが含まれていたら理由を伝えて最大2回やり直す。
環境変数 MODEL でモデルを変更できる（既定 claude-sonnet-5-5）。"""
import datetime, json, os, re, sys, urllib.request, urllib.error

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
today = datetime.date.today()
work = f"work/{today.strftime('%Y%m%d')}"

SPEC = """出力はJSONのみ（前後に説明やコードフェンスを付けない）。形式:
{"stories":[{"headline":"...","points":["..."],"links":["URL",...]}],
 "worth_reading":[{"title":"原題","source":"媒体名","link":"URL","blurb":"日本語で1〜2文の紹介"}]}
- stories は12本、worth_reading は4〜5本
- links と worth_reading.link は、ブリーフに載っているURLを一字一句そのままコピーする（推測・改変は禁止）
- 1本の links は、その話題を報じた記事のURLを2〜6個"""

def call(messages, system):
    body = json.dumps({"model": MODEL, "max_tokens": 16000, "system": system, "messages": messages}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body,
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=600))["content"][0]["text"]
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code}: {e.read().decode()[:500]}")

def parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))

def pool_urls():
    p = set()
    for f in ("candidates.json", "opinion.json"):
        with open(f"{work}/{f}", encoding="utf-8") as fh:
            p |= {i["link"].split("?")[0] for i in json.load(fh)}
    return p

def problems(data, pool):
    errs = []
    st, wr = data.get("stories", []), data.get("worth_reading", [])
    if len(st) != 12: errs.append(f"stories は12本必要（現在{len(st)}本）")
    if not 4 <= len(wr) <= 5: errs.append(f"worth_reading は4〜5本必要（現在{len(wr)}本）")
    bad = [l for s in st for l in s.get("links", []) if l.split("?")[0] not in pool] + [w.get("link", "") for w in wr if w.get("link", "").split("?")[0] not in pool]
    if bad: errs.append("ブリーフにないURLがあります。ブリーフからコピーして差し替えるか、その出典を外してください:\n" + "\n".join(bad))
    empty = [s["headline"] for s in st if not s.get("links")]
    if empty: errs.append("出典リンクがない話題: " + " / ".join(empty))
    return errs

def main(call_fn=call):
    system = open("EDITORIAL.md", encoding="utf-8").read()
    brief = open(f"{work}/brief.md", encoding="utf-8").read()
    pool = pool_urls()
    msgs = [{"role": "user", "content": f"今日の号を作ってください。以下がブリーフ（収集結果）です。\n\n{SPEC}\n\n---\n{brief}"}]
    for attempt in range(3):
        text = call_fn(msgs, "あなたはニュースレター「Daily Brief」の編集者です。次の編集方針に厳密に従ってください。\n\n" + system)
        try:
            data = parse(text); errs = problems(data, pool)
        except Exception as e:
            data, errs = None, [f"JSONとして解釈できません: {e}"]
        if not errs:
            json.dump(data, open(f"{work}/stories.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"stories.json を書きました（試行{attempt + 1}回目）"); return
        print(f"試行{attempt + 1}: 問題あり -> {errs}", file=sys.stderr)
        msgs += [{"role": "assistant", "content": text}, {"role": "user", "content": "次の問題を直して、JSONのみで出し直してください。\n" + "\n".join(errs)}]
    sys.exit("3回試しても検証を通りませんでした")

if __name__ == "__main__":
    if "ANTHROPIC_API_KEY" not in os.environ: sys.exit("ANTHROPIC_API_KEY が未設定です")
    main()
