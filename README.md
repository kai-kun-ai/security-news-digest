[![CI](https://github.com/kai-kun-ai/security-news-digest/actions/workflows/ci.yml/badge.svg)](https://github.com/kai-kun-ai/security-news-digest/actions/workflows/ci.yml)

# Security News Digest

セキュリティニュースを自動収集・重複排除・LLM要約し、カテゴリ別マークダウンダイジェストを生成するツール。  
Docker で `make run` するだけで動きます。

---

## 特徴

- **RSS取得** — 複数フィードから過去N日分の記事を一括取得
- **重複排除** — 同一URL・共通CVE・タイトル類似度で自動グルーピング
- **LLM要約** — Codex互換API（プライマリ）＋ OpenAI（フォールバック）で日本語要約を生成
- **ランキング** — 複数ソース報道・信頼ソース・CVSS 9.0+・KEV/悪用確認で優先度付け
- **興味フィルタ** — キーワードリストで関心のある記事だけ抽出
- **カスタムフィード** — テキストファイルでフィードURLを自由にカスタマイズ

---

## クイックスタート

### 前提条件

- Docker & Docker Compose（または `make` + Docker）
- （LLMモード使用時）APIキー

### 1. クローン

```bash
git clone https://github.com/kai-kun-ai/security-news-digest.git
cd security-news-digest
```

### 2. 環境変数を設定

```bash
export CODEX_API_KEY="your-codex-api-key"      # プライマリLLM
export OPENAI_API_KEY="your-openai-api-key"    # フォールバックLLM
```

> **LLM不要モード**もあります（`make run-no-llm`）。APIキー無しで動作します。

### 3. 実行

```bash
make run
```

出力は `output/digest_YYYY-MM-DD.md` に保存されます。

---

## 使い方

| コマンド | 説明 |
|---|---|
| `make run` | LLM要約付きでダイジェスト生成 |
| `make run-no-llm` | ヒューリスティックモード（APIキー不要） |
| `make run-interests` | 興味キーワードでフィルタして生成 |
| `make analyze REFERENCE_URL=https://example.com/blog` | 第三者ソースと比較してギャップ分析 |
| `make run FEEDS_FILE=my-feeds.txt` | カスタムフィードリストを使用 |
| `make build` | Dockerイメージのビルドのみ |
| `make clean` | Dockerイメージを削除 |

### Docker無しで実行

```bash
pip install -r requirements.txt
python main.py                                # digest (LLM)
python main.py --no-llm                       # digest (heuristic)
python main.py --interests                    # digest with interest filter
python main.py --feeds-file feeds.txt         # custom feeds
python main.py --config my.yaml               # custom config
python main.py --output-dir ./out             # override output directory
python main.py analyze-gap --reference-url https://example.com/blog  # gap analysis
```

---

## ギャップ分析 (Gap Analysis)
第三者のブログと比較して、収集漏れの原因分析と改善提案を行う機能。

### 例（Docker）

```bash
make analyze REFERENCE_URL=https://example.com/blog
```

### 例（ローカル実行）

```bash
python main.py analyze-gap --reference-url https://example.com/blog
# digestファイルを指定したい場合:
python main.py analyze-gap --reference-url https://example.com/blog --digest-file output/digest_YYYY-MM-DD.md
# 非対話モード（レポート表示のみ）:
python main.py analyze-gap --reference-url https://example.com/blog --auto
```

---

## フィードのカスタマイズ

### 方法1: config.yaml を編集

```yaml
feeds:
  - name: "My Feed"
    url: "https://example.com/rss"
    lang: "en"
  - name: "日本語フィード"
    url: "https://example.jp/feed"
    lang: "ja"
```

### 方法2: テキストファイルで指定

`feeds.example.txt` を参考に、1行1フィードで記述:

```
# コメント行は無視されます
https://example.com/rss
https://example.jp/feed,ja,日本語フィード
```

フォーマット: `URL` または `URL,lang,name`

```bash
make run FEEDS_FILE=my-feeds.txt
```

---

## 設定 (`config.yaml`)

| セクション | 説明 |
|---|---|
| `feeds` | RSSフィードURLリスト（name, url, lang） |
| `window_days` | 取得する過去日数（デフォルト: 3） |
| `llm.primary` | プライマリLLM設定（api_base, model, api_key_env） |
| `llm.fallback` | フォールバックLLM設定 |
| `trusted_sources` | 信頼ソース一覧（ランキングに影響） |
| `interest_keywords` | `--interests` フィルタ用キーワード |
| `output` | 出力ディレクトリ・ファイル名テンプレート |

### LLM設定

プライマリ（Codex互換エンドポイント）に接続できない場合、自動的にフォールバック（OpenAI）に切り替わります。  
どちらも `openai` Python SDKを使用するため、OpenAI互換APIであれば何でも使えます。

```yaml
llm:
  primary:
    api_base: "https://your-codex-endpoint.com/v1"
    api_key_env: "CODEX_API_KEY"
    model: "codex"
  fallback:
    api_base: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"
    model: "gpt-4o-mini"
```

---

## 出力フォーマット

ダイジェストは以下のカテゴリに自動分類されます:

- 🔴 **Critical / Actively Exploited** — CVSS 9.0+、KEV登録済み、ゼロデイ、悪用確認済み
- ⚠️ **Notable** — 複数ソースで報道、注目度の高いニュース
- 🇯🇵 **Japan** — 日本語ソースのニュース
- 📰 **General** — その他のセキュリティニュース

出力例: `output/digest_2026-02-16.md`

---

## プロジェクト構成

```
├── Dockerfile           # コンテナ定義
├── Makefile             # make run 等のコマンド
├── config.yaml          # メイン設定ファイル
├── feeds.example.txt    # フィードリストのサンプル
├── main.py              # CLIエントリポイント
├── analyzer.py          # ギャップ分析（第三者ソース比較）
├── fetcher.py           # RSS取得・パース
├── dedup.py             # 重複排除（URL/CVE/タイトル類似度）
├── summarizer.py        # LLM要約（プライマリ→フォールバック）
├── formatter.py         # Markdown整形・カテゴリ分類
├── requirements.txt     # Python依存パッケージ
├── pyproject.toml       # ruff設定
├── tests/               # テスト
└── output/              # 生成されたダイジェスト
```

---

## 開発

### セットアップ

```bash
pip install -r requirements.txt ruff pytest
```

### コマンド

| コマンド | 説明 |
|---|---|
| `make lint` | ruff によるリント・フォーマットチェック |
| `make test` | pytest でテスト実行 |
| `make fmt` | ruff で自動フォーマット修正 |

### CI

GitHub Actions で `lint` と `test` が自動実行されます（push / PR時）。

---

## ドキュメント

- **[チューニング ハンズオン](docs/tuning-handson.md)** — フィード追加・キーワード調整・重複排除・LLM設定・analyze-gapを使った自己改善の手順をステップバイステップで解説

---

## License

MIT
