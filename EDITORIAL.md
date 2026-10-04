# 編集方針（朝刊8:00・夕刊18:00の号を作るときの手順とルール）

## 号の種類
- **朝刊（Morning）**: 8:00公開。現在時刻が12時前に作る。タイトルは「What to know on the Morning of October 4, 2026」
- **夕刊（Evening）**: 18:00公開。12時以降に作る。「What to know on the Evening of ...」。brief.md に今朝の朝刊の話題が載っているので、**同じ話題は新しい展開がある場合だけ**取り上げ、朝刊以降の出来事・続報を中心に選ぶ
- edition は `daily.py` が時刻で自動判定する（`morning` / `evening` を引数で指定も可）。以下 `<ed>` は edition。

## 手順
1. `cd ~/Desktop/newsletter-prototype && python3 daily.py prepare`
2. `work/YYYYMMDD-<ed>/brief.md` を最後まで読む（自動クラスタは誤結合があるので、中身を読んで判断する）
3. `work/YYYYMMDD-<ed>/stories.json` を書く（形式は `daily.py` の冒頭）
4. `python3 daily.py publish work/YYYYMMDD-<ed>/stories.json`
   - 収集結果にないURLは拒否される。**URLは brief.md / candidates.json / opinion.json からコピーする。推測で書かない**
   - 死んだリンクは自動で外れる。「リンク切れ」「出典が全て切れた」と出たら内容を確認し、差し替えが必要なら stories.json を直して再実行
5. 生成された `site/paper/YYYYMMDD-<ed>.html` を開いて確認する。問題なければ `python3 daily.py deploy`（main に push → GitHub Actions が Pages に公開）
6. 結果を短く報告する（公開URL、本数、外れたリンク、気づいた点）

## 構成（12本 + Worth Reading）
- **12本**。各本は見出し1つ＋要点2〜4個＋出典リンク
- **AI・テック産業・テクノロジー: 5本前後**（AI安全性・規制、AIインフラ、主要テック企業、日本のAI/テックを含める）
- **サッカー: 2本**（プレミアリーグ、ラ・リーガ、日本代表、スペイン代表の話題のみ。野球は扱わない）
- 残りは国際・政治・経済・科学から、複数媒体が報じた重要な話題を優先
- 日本の話題を最低1本入れる（NHKが止まっているので日経・時事・TBS・朝日などから）
- **Worth Reading（4〜5本、本編とは別枠・下に配置）**: NYT・Guardian・Economist・FT・Atlantic などの社説/オピニオンから、AI・テック・社会の面白い論考。各1〜2文の紹介文

## 書き方のルール
- 事実は見出しと概要に書かれた範囲だけ。書かれていないことを足さない
- 有料記事（日経・FT・Economist・Bloomberg）で概要がないものは「見出しのみ確認」と明記
- 媒体名を括弧で添える。英語記事も日本語で書く
- **天気・気象、スポーツの野球、広告・セール記事は載せない**
- **論説・コラム（日経の「Think!」「社説」など）は本編のソースにしない**（Worth Readingでは可）
- 重複する話題は1本にまとめる

## 注意
- ソース構成は `feeds.json`、調整は `profiles.json`、ソース一覧は `SOURCES.md`
- NHKのRSSは更新が止まっている（確認すること）
- 日経サイエンス/トップ、Bloomberg(JP)はページ解析。取れなくなったら報告する
