#!/usr/bin/env python3
"""チューニングのテスト。fixtures/candidates.json（ある日の収集結果のスナップショット）で、ネットなしに再現できる。
  python3 test_tuning.py          # 全テスト
  python3 test_tuning.py -v       # 詳細
スナップショットを更新: python3 build.py --dry-run --save-candidates fixtures/candidates.json"""
import json, unittest
from datetime import datetime, timezone
import newsletter as nl

CFG = nl.load_cfg()
with open("fixtures/candidates.json", encoding="utf-8") as _f: ITEMS = json.load(_f)
NOW = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)
NOISE = CFG["noise_keywords"]
SW = {s["name"]: s["weight"] for s in CFG["sources"] if "weight" in s}
WEATHER = [k.lower() for k in CFG["exclude_keywords"]]

def run(profile_name, **override):
    p = {**nl.load_profile(profile_name), **override}
    return nl.select(ITEMS, p, now=NOW, noise=NOISE, source_weights=SW)

def cats(chosen):
    out = {}
    for c in chosen: out[c["category"]] = out.get(c["category"], 0) + 1
    return out

class Basics(unittest.TestCase):
    def test_pick_count_for_every_profile(self):
        with open("profiles.json", encoding="utf-8") as f: profiles = json.load(f)
        for name, p in profiles.items():
            if name.startswith("_"): continue
            self.assertEqual(len(run(name)), p["pick"], name)

    def test_no_duplicate_stories(self):
        for name in ["default", "ai_focus", "business", "world", "no_ai", "wide"]:
            links = [m["link"] for c in run(name) for m in c["members"]]
            self.assertEqual(len(links), len(set(links)), name)

    def test_weather_never_appears(self):
        # 収集後にも天気語が混ざっていないこと（収集時に除外済みの回帰テスト）
        for c in run("wide"):
            text = " ".join(m["title"] + m["desc"] for m in c["members"]).lower()
            self.assertFalse([k for k in WEATHER if k in text], c["rep"]["title"])

    def test_stale_feed_is_dropped(self):
        # NHKのRSSは8/8で止まっている。max_age_hours=72で全て落ちる
        for name in ["default", "wide"]:
            for c in run(name):
                self.assertFalse([m for m in c["members"] if m["source"].startswith("NHK")], name)

    def test_noise_filtered(self):
        for c in run("wide", pick=15):
            for m in c["members"]:
                self.assertFalse(any(k in m["title"].lower() for k in NOISE), m["title"])

class Knobs(unittest.TestCase):
    def test_zero_weight_excludes_category(self):
        self.assertEqual(cats(run("no_ai")).get("AI", 0), 0)
        self.assertEqual(cats(run("business")).get("科学", 0), 0)

    def test_max_per_category_respected(self):
        for name in ["default", "business", "world", "wide"]:
            p = nl.load_profile(name)
            for cat, n in cats(run(name)).items():
                self.assertLessEqual(n, p["max_per_category"].get(cat, 99), f"{name}:{cat}")

    def test_min_per_category_met(self):
        for name in ["default", "ai_focus", "business", "world"]:
            p = nl.load_profile(name)
            got = cats(run(name))
            for cat, need in p["min_per_category"].items():
                self.assertGreaterEqual(got.get(cat, 0), need, f"{name}:{cat}")

    def test_ai_weight_is_monotonic(self):
        counts = [cats(run("default", category_weights={**nl.load_profile("default")["category_weights"], "AI": w},
                           max_per_category={}, min_per_category={})).get("AI", 0) for w in (0.0, 0.5, 1.0, 2.0, 4.0)]
        self.assertEqual(counts, sorted(counts), counts)
        self.assertEqual(counts[0], 0)
        self.assertGreater(counts[-1], counts[1])

    def test_pick_capped_at_12(self):
        self.assertEqual(nl.load_profile("default")["pick"], 12)
        self.assertLessEqual(len(run("default", pick=30)), 30)  # runは上書きするのでselect自体は制限しない
        import json as _j, tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            _j.dump({"x": {**nl.load_profile("default"), "pick": 50}}, f)
        self.assertEqual(nl.load_profile("x", f.name)["pick"], 12)
        os.unlink(f.name)

    def test_pick_scales(self):
        self.assertEqual([len(run("default", pick=n)) for n in (3, 5, 8, 12)], [3, 5, 8, 12])

    def test_breadth_limits_per_source(self):
        # max_per_source=1 なら同一媒体が代表になる話題は1本まで
        reps = [c["sources"][0] for c in run("wide", max_per_source=1)]
        self.assertEqual(len(reps), len(set(reps)))

    def test_coverage_weight_prefers_widely_reported(self):
        hi = sum(len(c["sources"]) for c in run("default", coverage_weight=2.0, min_per_category={}, max_per_category={}))
        lo = sum(len(c["sources"]) for c in run("default", coverage_weight=0.0, min_per_category={}, max_per_category={}))
        self.assertGreater(hi, lo)

    def test_profiles_actually_differ(self):
        names = ["default", "ai_focus", "business", "world", "no_ai"]
        tops = [tuple(sorted(c["rep"]["link"] for c in run(n))) for n in names]
        self.assertEqual(len(set(tops)), len(names), "プロファイル間で結果が同じ")

class Clustering(unittest.TestCase):
    """正解を手で付けた話題で、同じ話題がまとまり、無関係な記事が混ざらないかを見る。"""
    def group_with(self, needle):
        for g in nl.cluster([i for i in ITEMS if not i["source"].startswith("NHK")]):
            if any(needle in m["title"] for m in g): return g
        self.fail(needle)

    def test_flydubai_grouped_across_outlets(self):
        g = self.group_with("Flydubai co-pilot attacked")
        self.assertGreaterEqual(len({m["source"] for m in g}), 3)
        self.assertTrue(all("lydubai" in m["title"].lower() or "co-pilot" in m["title"].lower() or "ax" in m["title"].lower()
                            for m in g), [m["title"] for m in g])

    def test_cross_language_openai_resignation(self):
        g = self.group_with("OpenAI safety employee resigns")
        langs = {m["lang"] for m in g}
        self.assertEqual(langs, {"en", "ja"}, [m["source"] for m in g])  # 英語と日本語の記事が同じ話題に入る

    def test_lula_bolsonaro(self):
        self.assertGreaterEqual(len(self.group_with("Lula, Bolsonaro")), 2)

    def test_no_false_merge_rate(self):
        """3件以上の塊の純度。見出しが話題語を1つも共有しない記事が混ざる割合を測る。"""
        impure = total = 0
        for g in nl.cluster([i for i in ITEMS if not i["source"].startswith("NHK")]):
            if len(g) < 3: continue
            total += 1
            sigs = [nl.signature(m) for m in g]
            common = set.intersection(*sigs) if sigs else set()
            if not common and not any(len(a & b) >= 2 for a in sigs for b in sigs if a is not b): impure += 1
        self.assertLessEqual(impure, max(1, total // 3), f"{impure}/{total}")

class AgentEdit(unittest.TestCase):
    """Claude API役の出力を検証する層。偽の応答で、推測URLを弾いてやり直させることを確認する。"""
    def test_fabricated_url_rejected_then_fixed(self):
        import os, shutil, tempfile, agent_edit as ae
        urls = sorted({i["link"].split("?")[0] for i in ITEMS})[:40]
        story = lambda n: {"headline": f"h{n}", "points": ["p"], "links": [urls[n]]}
        good = {"stories": [story(n) for n in range(12)], "worth_reading": [{"title": "t", "source": "s", "link": urls[20 + n], "blurb": "b"} for n in range(4)]}
        bad = json.loads(json.dumps(good)); bad["stories"][0]["links"] = ["https://example.com/fabricated"]
        calls = []
        def fake(msgs, system):
            calls.append(1); return "前置き\n" + json.dumps(bad if len(calls) == 1 else good, ensure_ascii=False)
        d = tempfile.mkdtemp(); ae.work = d
        ae.pool_urls = lambda: set(urls)
        for f in ("brief.md", "candidates.json", "opinion.json"): open(f"{d}/{f}", "w").write("[]" if f.endswith("json") else "x")
        ae.main(fake)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(json.load(open(f"{d}/stories.json"))["stories"]), 12)
        shutil.rmtree(d)

    def test_wrong_count_rejected(self):
        import agent_edit as ae
        urls = {"https://a/1"}
        data = {"stories": [{"headline": "h", "points": [], "links": ["https://a/1"]}] * 3, "worth_reading": []}
        errs = ae.problems(data, urls)
        self.assertTrue(any("12本" in e for e in errs) and any("4〜5本" in e for e in errs))

if __name__ == "__main__":
    unittest.main()
