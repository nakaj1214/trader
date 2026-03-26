# パフォーマンスチューニング

## メモリ設定

### CODEQL_RAM 環境変数

最大ヒープメモリ（MB 単位）を制御:

```bash
# 大規模コードベース向け 48GB
CODEQL_RAM=48000 codeql database analyze codeql.db ...

# 中規模コードベース向け 16GB
CODEQL_RAM=16000 codeql database analyze codeql.db ...
```

**ガイドライン:**
| コードベースサイズ | 推奨 RAM |
|---------------|-----------------|
| 小規模（10万行未満） | 4-8 GB |
| 中規模（10万〜100万行） | 8-16 GB |
| 大規模（100万行以上） | 32-64 GB |

## スレッド設定

### 解析スレッド

```bash
# 利用可能なすべてのコアを使用
codeql database analyze codeql.db --threads=0 ...

# 特定の数を使用
codeql database analyze codeql.db --threads=8 ...
```

**注意:** `--threads=0` は利用可能なすべてのコアを使用します。共有マシンでは明示的な数を使用してください。

## クエリレベルのタイムアウト

個々のクエリが無限に実行されるのを防止:

```bash
# クエリごとのタイムアウトを設定（ミリ秒単位）
codeql database analyze codeql.db --timeout=600000 ...
```

10分のタイムアウト（`600000`）は、暴走クエリをキャッチしつつ、正当な複雑な解析を止めません。大規模コードベースでのテイント追跡クエリにはより長い時間が必要な場合があります。

## 評価器診断

解析が遅い場合、`--evaluator-log` を使用してどのクエリが最も時間を消費しているかを特定:

```bash
codeql database analyze codeql.db \
  --evaluator-log=evaluator.log \
  --format=sarif-latest \
  --output=results.sarif \
  -- codeql/python-queries:codeql-suites/python-security-extended.qls

# ログを要約
codeql generate log-summary evaluator.log --format=text
```

要約には、クエリごとのタイミングとタプル数が表示されます。数百万のタプルを生成するクエリがボトルネックの可能性が高いです。

## ディスク容量

| フェーズ | 一般的なサイズ | 備考 |
|-------|-------------|-------|
| データベース作成 | ソースサイズの 2-10 倍 | コンパイル言語はビルドトレースのため大きい |
| 解析キャッシュ | 1-5 GB | データベースディレクトリに格納 |
| SARIF 出力 | 1-50 MB | 検出数による |

開始前に利用可能な容量を確認:

```bash
df -h .
du -sh codeql_*.db 2>/dev/null
```

## キャッシュ動作

CodeQL はクエリ評価結果をデータベースディレクトリ内にキャッシュします。同じクエリの後続実行は再評価をスキップします。

| シナリオ | キャッシュ効果 |
|----------|-------------|
| 同じパックを再実行 | 高速 — キャッシュ結果を使用 |
| 新しいクエリパックを追加 | 新しいクエリのみ評価 |
| `codeql database cleanup` | キャッシュをクリア — 完全な再評価を強制 |
| `--rerun` フラグ | この実行ではキャッシュを無視 |

**キャッシュをクリアすべきとき:**
- 新しいデータ拡張をデプロイした後（キャッシュに古い結果が残っている場合）
- 予期しないゼロ検出結果を調査する場合
- ベンチマーク比較前（一貫したタイミングを確保）

```bash
# 評価キャッシュをクリア
codeql database cleanup codeql_1.db
```

## パフォーマンスのトラブルシューティング

| 症状 | 考えられる原因 | 解決策 |
|---------|--------------|----------|
| 解析中の OOM | RAM 不足 | `CODEQL_RAM` を増やす |
| データベース作成が遅い | 複雑なビルド | `--threads` を使用、ビルドを簡素化 |
| クエリ実行が遅い | 大規模コードベース | クエリスコープを縮小、RAM を追加 |
| データベースが大きすぎる | ファイルが多すぎる | 除外設定を使用（[build-database ワークフロー](../workflows/build-database.md#1b-create-exclusion-config-interpreted-languages-only)を参照） |
| 単一クエリがハング | 暴走評価 | `--timeout` を使用し `--evaluator-log` を確認 |
| 繰り返し実行してもまだ遅い | キャッシュが使用されていない | 同じデータベースパスを使用しているか確認 |
