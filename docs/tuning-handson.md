# チューニング ハンズオン

本ドキュメントでは、Security News Digest のフィード設定・重複排除・ランキング・LLM要約を
実際に手を動かしながら調整する手順を解説します。

---

## 目次

1. [事前準備](#事前準備)
2. [Step 1: まず動かしてみる](#step-1-まず動かしてみる)
3. [Step 2: フィードを追加する](#step-2-フィードを追加する)
4. [Step 3: 取得窓（window_days）を調整する](#step-3-取得窓window_daysを調整する)
5. [Step 4: 信頼ソースを設定する](#step-4-信頼ソースを設定する)
6. [Step 5: 興味キーワードをチューニングする](#step-5-興味キーワードをチューニングする)
7. [Step 6: 重複排除の精度を確認する](#step-6-重複排除の精度を確認する)
8. [Step 7: LLM要約の品質を調整する](#step-7-llm要約の品質を調整する)
9. [Step 8: analyze-gap で自己改善する](#step-8-analyze-gap-で自己改善する)
10. [チューニングのコツ](#チューニングのコツ)

---

## 事前準備

```bash
git clone https://github.com/kai-kun-ai/security-news-digest.git
cd security-news-digest
```

### LLM無しで試す場合

APIキー不要。ヒューリスティックモードで動作確認できます。

```bash
make run-no-llm
```

### LLMありで試す場合

```bash
export CODEX_API_KEY="your-key"       # プライマリ
export OPENAI_API_KEY="your-key"      # フォールバック
make run
```

---

## Step 1: まず動かしてみる

まずはデフォルト設定でダイジェストを生成します。

```bash
make run-no-llm
```

`output/digest_YYYY-MM-DD.md` が生成されます。中身を確認してください:

```bash
cat output/digest_*.md
```

確認ポイント:
- 記事はいくつ取得できたか（ターミナル出力の `Fetched N articles` を確認）
- カテゴリ分けは妥当か（🔴 Critical に本当に重要なものが入っているか）
- 日本語ニュースは 🇯🇵 セクションに入っているか
- 明らかに欠けているニュースはないか

---

## Step 2: フィードを追加する

### 方法A: config.yaml を直接編集

```yaml
feeds:
  # 既存フィード
  - name: "SecurityNews (EN)"
    url: "https://www.inoreader.com/stream/user/1005194803/tag/SecurityNews"
    lang: "en"

  # 追加例: The Hacker News の直接RSS
  - name: "The Hacker News"
    url: "https://feeds.feedburner.com/TheHackersNews"
    lang: "en"

  # 追加例: CISA Alerts
  - name: "CISA Alerts"
    url: "https://www.cisa.gov/cybersecurity-advisories/all.xml"
    lang: "en"
```

### 方法B: フィードリストファイルを使う

```bash
# feeds.txt を作成
cat > my-feeds.txt << 'EOF'
# セキュリティニュース
https://feeds.feedburner.com/TheHackersNews,en,The Hacker News
https://www.bleepingcomputer.com/feed/,en,BleepingComputer
https://www.cisa.gov/cybersecurity-advisories/all.xml,en,CISA
https://www.security-next.com/feed,ja,Security NEXT
EOF

# フィードリストを指定して実行
make run-no-llm FEEDS_FILE=my-feeds.txt
```

### 効果を確認

```bash
# 前回と今回の記事数を比較
# ターミナル出力: "Fetched N articles" → "M unique article groups"
```

> **💡 コツ**: フィードを増やしすぎると処理時間とLLMコストが増加します。
> まずは5〜10フィードから始めて、`analyze-gap` で不足を補う運用がおすすめです。

---

## Step 3: 取得窓（window_days）を調整する

デフォルトは過去3日分です。

```yaml
# config.yaml
window_days: 3   # 過去3日（デフォルト）
# window_days: 7   # 週次まとめなら7日
# window_days: 1   # デイリー実行なら1日でもOK
```

### 判断基準

| 運用パターン | 推奨値 |
|---|---|
| 毎日実行 | 1〜2 |
| 2〜3日に1回 | 3（デフォルト） |
| 週次まとめ | 7 |
| 見逃し防止重視 | 5〜7 |

> **⚠️ 注意**: 値を大きくすると記事数が増え、LLMトークン消費も増えます。

---

## Step 4: 信頼ソースを設定する

信頼ソースに登録されたメディアの記事はランキングスコアが +2 されます。

```yaml
trusted_sources:
  - "BleepingComputer"
  - "The Hacker News"
  - "CISA"
  - "Krebs on Security"
  - "SecurityWeek"
  - "Dark Reading"
  - "GBHackers"
  - "Ars Technica"
  # 追加例
  - "The Register"
  - "JPCERT/CC"
  - "IPA"
```

### 信頼ソースの決め方

- **速報性**: 脆弱性情報をいち早く報じるか
- **正確性**: 誤報が少ないか
- **深さ**: 技術的な分析があるか
- **関連性**: 自分の業務に関連するニュースを扱っているか

信頼ソースの記事が上位に来ることを確認:

```bash
make run-no-llm
# 出力の 🔴 Critical や ⚠️ Notable に信頼ソースの記事が多いかチェック
```

---

## Step 5: 興味キーワードをチューニングする

`--interests` フラグで使われるキーワードリストです。

```yaml
interest_keywords:
  # 脆弱性関連
  - "CVE"
  - "KEV"
  - "RCE"
  - "zero-day"
  - "actively exploited"

  # 自分の技術スタックに合わせて追加
  - "Kubernetes"
  - "Docker"
  - "AWS"
  - "GitHub Actions"

  # 組織固有のキーワード
  - "Apache"        # Apacheを多用しているなら
  - "PostgreSQL"    # DBに依存しているなら
  - "OAuth"         # 認証基盤に関連するなら
```

### チューニングの手順

1. まず `--interests` 無しでフル実行:
   ```bash
   make run-no-llm
   ```

2. 次に `--interests` 付きで実行:
   ```bash
   make run-interests
   ```

3. 差分を確認:
   - フルで出て interests で消えた記事 → 本当に不要か確認
   - 残った記事 → 自分に必要なものだけか確認

4. 足りないキーワードを追加、ノイズになるキーワードを削除

> **💡 コツ**: キーワードは「部分一致」です。`"auth"` を入れると `"authentication"`, `"authorization"`, `"OAuth"` すべてにマッチします。
> 短すぎるキーワードは誤検知の原因になるので注意してください。

---

## Step 6: 重複排除の精度を確認する

重複排除は3段階で行われます:

1. **URL完全一致** — 同じURLの記事を統合
2. **CVE一致** — 同じCVE-IDを持つ記事を統合
3. **タイトル類似度** — 正規化後のタイトルが75%以上類似なら統合

### よくある問題と対処

#### 問題: 別の記事が誤って統合される
同じCVEを含む別トピックの記事が1つのグループに統合されることがあります。

```bash
# --no-llm で実行し、グループ数を確認
make run-no-llm
# "M unique article groups" が極端に少ない場合は過剰統合の疑い
```

対処: `dedup.py` の `titles_similar` 閾値を調整（デフォルト0.75）

```python
# dedup.py
def titles_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    # threshold を上げると統合が厳しくなる（0.85など）
    # threshold を下げると統合が緩くなる（0.65など）
```

#### 問題: 同じニュースが複数回出る
統合されるべき記事が別グループになっている場合。

対処:
- `SOURCE_SUFFIXES` にソース名のサフィックスを追加
- `threshold` を下げる（0.70など）

---

## Step 7: LLM要約の品質を調整する

### temperature を調整する

```yaml
llm:
  # ...
  temperature: 0.3    # デフォルト（安定した出力）
  # temperature: 0.1  # より保守的（事実重視）
  # temperature: 0.5  # より創造的（読みやすさ重視）
```

| 値 | 特徴 |
|---|---|
| 0.1 | 事実に忠実、硬い文体 |
| 0.3 | バランス（デフォルト） |
| 0.5 | 読みやすいが、たまに不正確 |

### max_tokens を調整する

```yaml
llm:
  max_tokens: 1024    # デフォルト
  # max_tokens: 2048  # 記事が多い場合（20+グループ）
  # max_tokens: 512   # コスト節約
```

### モデルを変更する

```yaml
llm:
  primary:
    model: "codex"             # デフォルト
  fallback:
    model: "gpt-4o-mini"      # デフォルト
    # model: "gpt-4o"         # より高品質だがコスト増
```

### 要約品質の確認方法

```bash
# 1) LLM無しで実行（ベースライン）
python3 main.py digest --no-llm --output-dir output-baseline

# 2) LLMありで実行
python3 main.py digest --output-dir output-llm

# 3) 比較
diff output-baseline/digest_*.md output-llm/digest_*.md
```

確認ポイント:
- CVE-IDが要約に含まれているか
- CVSSスコアが記載されているか
- カテゴリ分けが妥当か（LLMの方がヒューリスティックより精度が高いはず）

---

## Step 8: analyze-gap で自己改善する

ここが本ツールの核心です。第三者のセキュリティまとめブログと比較して、自分が拾えなかった記事を分析します。

### 1. まずダイジェストを生成

```bash
make run-no-llm
```

### 2. 参照元と比較

```bash
# 例: 他のセキュリティブログと比較
python3 main.py analyze-gap \
  --reference-url https://example.com/security-weekly-roundup \
  --config config.yaml
```

### 3. 対話セッションで分析

```
analyze-gap> list
[1] Apache Struts RCE CVE-2026-XXXX (feed_missing)
[2] Windows SmartScreen Bypass (dedup_merged)
[3] 某社ランサムウェア被害 (interest_filtered)

analyze-gap> detail 1
Title: Apache Struts RCE CVE-2026-XXXX
URL: https://securitynews.example.com/apache-struts-rce
Cause: feed_missing
Detail: 参照記事のドメイン(securitynews.example.com)が設定されたRSSフィード群に含まれていない可能性が高い。

analyze-gap> suggest
## 分析サマリー
検出ギャップ数: 3

## 改善提案
### 1. フィード追加
- [ ] securitynews.example.com のRSSフィードを追加
      config.yaml:
        feeds:
          - name: "SecurityNews Example"
            url: "https://securitynews.example.com/feed"
            lang: "en"

### 2. キーワード追加
- [ ] interest_keywords に "SmartScreen" を追加

analyze-gap> show-fix 1
config.yamlのfeedsに該当ソースのRSSを追加する。例:
feeds:
  - name: securitynews.example.com
    url: https://securitynews.example.com/feed
    lang: en

analyze-gap> apply 1
About to apply change: Append feed placeholder for domain: securitynews.example.com
Proceed? [y/N] y
Applied. Diff:
(差分が表示される)

analyze-gap> quit
```

### 4. 改善後に再実行して確認

```bash
# 設定変更後に再度ダイジェストを生成
make run-no-llm

# もう一度 analyze-gap で漏れが減ったか確認
python3 main.py analyze-gap \
  --reference-url https://example.com/security-weekly-roundup \
  --auto
```

### 自動モードでレポートだけ出す

```bash
python3 main.py analyze-gap \
  --reference-url https://example.com/blog \
  --auto --no-llm
```

---

## チューニングのコツ

### 1. 段階的に調整する

一度に全部変えずに、1つずつ変更して効果を確認しましょう。

```
フィード追加 → 再実行 → 確認
  ↓
キーワード調整 → 再実行 → 確認
  ↓
信頼ソース追加 → 再実行 → 確認
  ↓
analyze-gap で残りの漏れを確認
```

### 2. 定期的に analyze-gap を回す

週に1回、信頼できるセキュリティブログと比較して漏れをチェックする運用がおすすめです。

```bash
# 週次チェック例
python3 main.py analyze-gap \
  --reference-url https://trusted-blog.example.com/weekly \
  --auto >> gap-report.log
```

### 3. コストとカバレッジのバランス

| 設定 | カバレッジ | コスト |
|---|---|---|
| フィード少 + window短 + LLM無し | 低 | ほぼゼロ |
| フィード中 + window 3日 + gpt-4o-mini | 中 | 低 |
| フィード多 + window 7日 + gpt-4o | 高 | 中〜高 |

まずは「フィード中 + window 3日 + gpt-4o-mini」で始めて、`analyze-gap` の結果を見ながら足りないフィードを追加していくのが効率的です。

### 4. 原因別の対処優先度

| 原因 | 頻度 | 対処コスト | 優先度 |
|---|---|---|---|
| feed_missing | 高 | 低（RSS追加のみ） | ⭐⭐⭐ 最優先 |
| interest_filtered | 中 | 低（キーワード追加） | ⭐⭐ |
| outside_window | 低 | 低（window_days変更） | ⭐ |
| dedup_merged | 低 | 中（閾値調整は副作用あり） | 要注意 |
| low_rank | 低 | 中（ランキング調整） | 後回し可 |

---

## 設定ファイルのサンプル（チューニング済み例）

```yaml
# config.yaml（チューニング例）

feeds:
  - name: "Inoreader EN"
    url: "https://www.inoreader.com/stream/user/1005194803/tag/SecurityNews"
    lang: "en"
  - name: "Inoreader GoogleNews"
    url: "https://www.inoreader.com/stream/user/1005194803/tag/GoogleNewsFeed"
    lang: "en"
  - name: "Inoreader JP"
    url: "https://www.inoreader.com/stream/user/1005194803/tag/SecurityNews_JP"
    lang: "ja"
  # analyze-gap で追加したフィード
  - name: "CISA Alerts"
    url: "https://www.cisa.gov/cybersecurity-advisories/all.xml"
    lang: "en"
  - name: "JPCERT/CC"
    url: "https://www.jpcert.or.jp/rss/jpcert-all.rdf"
    lang: "ja"

window_days: 3

llm:
  primary:
    api_base: "https://codex.example.com/v1"
    api_key_env: "CODEX_API_KEY"
    model: "codex"
  fallback:
    api_base: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"
    model: "gpt-4o-mini"
  max_tokens: 1024
  temperature: 0.3

trusted_sources:
  - "BleepingComputer"
  - "The Hacker News"
  - "CISA"
  - "Krebs on Security"
  - "SecurityWeek"
  - "Dark Reading"
  - "GBHackers"
  - "Ars Technica"
  - "The Register"
  - "JPCERT/CC"

interest_keywords:
  - "CVE"
  - "KEV"
  - "RCE"
  - "zero-day"
  - "actively exploited"
  - "auth bypass"
  - "privilege escalation"
  - "ransomware"
  - "supply chain"
  - "Kubernetes"
  - "Docker"
  - "AWS"
  - "Azure"
  - "GitHub Actions"
  - "SSRF"
  - "Active Directory"

output:
  directory: "output"
  filename_template: "digest_{date}.md"
```
