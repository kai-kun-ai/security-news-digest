# Security News Digest CLI

セキュリティニュースを自動収集・重複排除・要約し、マークダウン形式のダイジェストを生成するCLIツール。

## Features / 機能

- **RSS Feed Fetching** — Inoreader経由でセキュリティニュースフィードを取得
- **Deduplication** — URL、CVE ID、タイトル類似度による重複排除
- **LLM Summarization** — LLMによる日本語要約・カテゴリ分類（Codex/OpenAI対応）
- **Ranking** — 複数ソース・信頼ソース・CVSS・KEVによるランキング
- **Interest Filtering** — キーワードベースのフィルタリング
- **Markdown Output** — カテゴリ別マークダウンダイジェスト出力

## Setup / セットアップ

```bash
pip install -r requirements.txt
```

### Environment Variables / 環境変数

LLMを使用する場合、APIキーを環境変数に設定:

```bash
export CODEX_API_KEY="your-codex-api-key"
export OPENAI_API_KEY="your-openai-api-key"
```

## Usage / 使い方

```bash
# Basic usage (with LLM summarization)
python main.py

# Without LLM (heuristic categorization only)
python main.py --no-llm

# Filter by interest keywords
python main.py --interests

# Custom config file
python main.py --config my_config.yaml

# Custom output directory
python main.py --output-dir ./my_output
```

## Configuration / 設定

`config.yaml` で以下を設定可能:

- **feeds** — RSSフィードURL一覧
- **window_days** — 取得する過去日数（デフォルト: 3日）
- **llm** — LLM設定（プライマリ/フォールバック）
- **trusted_sources** — 信頼ソース一覧（ランキングに影響）
- **interest_keywords** — フィルタリング用キーワード
- **output** — 出力ディレクトリ・ファイル名テンプレート

## Output / 出力

ダイジェストは `output/digest_YYYY-MM-DD.md` に出力されます。

### Categories / カテゴリ

- 🔴 **Critical / Actively Exploited** — CVSS 9.0+, KEV, ゼロデイ
- ⚠️ **Notable** — 注目すべきニュース
- 🇯🇵 **Japan** — 日本語ソースのニュース
- 📰 **General** — その他

## License

MIT
