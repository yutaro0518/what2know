# 参照ソースリスト

`feeds.json` から自動生成（`python3 gen_sources.py`）。天気関連は `exclude_keywords` で除外。

| カテゴリ | ソース | 言語 | 取得方法 | URL |
|---|---|---|---|---|
| 総合 | NHK 主要ニュース | ja | RSS | https://www3.nhk.or.jp/rss/news/cat0.xml |
| 総合 | 日本経済新聞 トップ | ja | ページ解析 | https://www.nikkei.com/ |
| 総合 | 時事通信 主要 | ja | RSS | https://www.jiji.com/rss/ranking.rdf |
| 総合 | TBS NEWS DIG | ja | RSS | https://newsdig.tbs.co.jp/list/feed/rss |
| 政治 | NHK 政治 | ja | RSS | https://www3.nhk.or.jp/rss/news/cat4.xml |
| 政治 | Bloomberg (US) Politics | en | RSS | https://feeds.bloomberg.com/politics/news.rss |
| 政治 | Politico | en | RSS | https://rss.politico.com/politics-news.xml |
| 政治 | NYT Politics | en | RSS | https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml |
| 政治 | Axios | en | RSS | https://api.axios.com/feed/ |
| 政治 | Foreign Affairs | en | RSS | https://www.foreignaffairs.com/rss.xml |
| 経済 | NHK 経済 | ja | RSS | https://www3.nhk.or.jp/rss/news/cat5.xml |
| 経済 | Nikkei Asia | en | RSS | https://asia.nikkei.com/rss/feed/nar |
| 経済 | BBC Business | en | RSS | https://feeds.bbci.co.uk/news/business/rss.xml |
| 経済 | 日本経済新聞 速報 | ja | RSS | https://assets.wor.jp/rss/rdf/nikkei/news.rdf |
| 経済 | The New York Times Business | en | RSS | https://rss.nytimes.com/services/xml/rss/nyt/Business.xml |
| 経済 | Business Insider (US) | en | RSS | https://feeds.businessinsider.com/custom/all |
| 経済 | Bloomberg (US) Markets | en | RSS | https://feeds.bloomberg.com/markets/news.rss |
| 経済 | Financial Times | en | RSS | https://www.ft.com/rss/home |
| 経済 | Bloomberg (JP) | ja | ページ解析 | https://www.bloomberg.co.jp/ |
| 国際 | NHK 国際 | ja | RSS | https://www3.nhk.or.jp/rss/news/cat6.xml |
| 国際 | BBC World | en | RSS | https://feeds.bbci.co.uk/news/world/rss.xml |
| 国際 | The Guardian World | en | RSS | https://www.theguardian.com/world/rss |
| 国際 | Al Jazeera | en | RSS | https://www.aljazeera.com/xml/rss/all.xml |
| 国際 | The New York Times World | en | RSS | https://rss.nytimes.com/services/xml/rss/nyt/World.xml |
| 国際 | The Economist | en | RSS | https://www.economist.com/latest/rss.xml |
| テック | BBC Technology | en | RSS | https://feeds.bbci.co.uk/news/technology/rss.xml |
| テック | The New York Times Technology | en | RSS | https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml |
| テック | The Verge | en | RSS | https://www.theverge.com/rss/index.xml |
| テック | Wired (US) | en | RSS | https://www.wired.com/feed/rss |
| テック | Bloomberg (US) Technology | en | RSS | https://feeds.bloomberg.com/technology/news.rss |
| テック | MIT Technology Review (US) | en | RSS | https://www.technologyreview.com/feed/ |
| テック | MIT Technology Review (JP) | ja | RSS | https://www.technologyreview.jp/feed/ |
| AI | ITmedia AI+ | ja | RSS | https://rss.itmedia.co.jp/rss/2.0/aiplus.xml |
| AI | TechCrunch AI | en | RSS | https://techcrunch.com/category/artificial-intelligence/feed/ |
| AI | OpenAI News | en | RSS | https://openai.com/news/rss.xml |
| 科学 | NHK 科学・医療 | ja | RSS | https://www3.nhk.or.jp/rss/news/cat3.xml |
| 科学 | Nature | en | RSS | https://www.nature.com/nature.rss |
| 科学 | Science (AAAS) News | en | RSS | https://www.science.org/rss/news_current.xml |
| 科学 | Scientific American | en | RSS | https://www.scientificamerican.com/platform/syndication/rss/ |
| 科学 | Quanta Magazine | en | RSS | https://api.quantamagazine.org/feed/ |
| 科学 | Ars Technica Science | en | RSS | https://feeds.arstechnica.com/arstechnica/science |
| 科学 | BBC Science & Environment | en | RSS | https://feeds.bbci.co.uk/news/science_and_environment/rss.xml |
| 科学 | NYT Science | en | RSS | https://rss.nytimes.com/services/xml/rss/nyt/Science.xml |
| 科学 | STAT News | en | RSS | https://www.statnews.com/feed/ |
| 科学 | NASA | en | RSS | https://www.nasa.gov/feed/ |
| 科学 | Phys.org | en | RSS | https://phys.org/rss-feed/breaking/ |
| 科学 | Nature ダイジェスト（日本語） | ja | RSS | https://www.natureasia.com/ja-jp/rss/nature |
| 科学 | sorae 宇宙ニュース | ja | RSS | https://sorae.info/feed |
| 科学 | ナゾロジー | ja | RSS | https://nazology.net/feed |
| 科学 | The Conversation | en | RSS | https://theconversation.com/global/articles.atom |
| 科学 | Wired (US) Science | en | RSS | https://www.wired.com/feed/category/science/latest/rss |
| 科学 | 日本経済新聞 サイエンス | ja | ページ解析 | https://www.nikkei.com/topics/24032503 |

## 未対応
- Bloomberg (JP): 公開RSSがないためトップページの見出しを解析（ページ構造が変わると取れなくなる）
- 日本経済新聞: 公式RSSがないため、第三者ミラー（assets.wor.jp）経由。停止の可能性あり
- 要約文はAIによる生成を含む。本文の転載はしない
