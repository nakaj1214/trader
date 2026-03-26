# SARIF jq クエリリファレンス

一般的な SARIF パースタスクのためのすぐに使える jq クエリ。

## 基本的な探索

```bash
# 整形表示
jq '.' results.sarif

# SARIF バージョンを取得
jq '.version' results.sarif

# すべての run からツール名をリスト
jq '.runs[].tool.driver.name' results.sarif

# run 数をカウント
jq '.runs | length' results.sarif
```

## 結果クエリ

```bash
# 合計結果数
jq '[.runs[].results[]] | length' results.sarif

# 深刻度レベル別カウント
jq 'reduce .runs[].results[] as $r ({}; .[$r.level] += 1)' results.sarif

# ユニークなルール ID をリスト
jq '[.runs[].results[].ruleId] | unique | sort' results.sarif

# ルールごとのカウント
jq '[.runs[].results[]] | group_by(.ruleId) | map({rule: .[0].ruleId, count: length}) | sort_by(-.count)' results.sarif
```

## 結果のフィルタリング

```bash
# エラーのみ
jq '.runs[].results[] | select(.level == "error")' results.sarif

# 警告のみ
jq '.runs[].results[] | select(.level == "warning")' results.sarif

# 特定のルール ID
jq --arg rule "SQL_INJECTION" '.runs[].results[] | select(.ruleId == $rule)' results.sarif

# ファイルパス（部分一致）
jq --arg file "auth" '.runs[].results[] | select(.locations[].physicalLocation.artifactLocation.uri | contains($file))' results.sarif

# ファイル拡張子
jq '.runs[].results[] | select(.locations[].physicalLocation.artifactLocation.uri | test("\\.py$"))' results.sarif

# 複合条件
jq '.runs[].results[] | select(.level == "error" and (.ruleId | startswith("SEC")))' results.sarif
```

## 位置の抽出

```bash
# 各結果のファイルと行
jq '.runs[].results[] | {
  rule: .ruleId,
  file: .locations[0].physicalLocation.artifactLocation.uri,
  line: .locations[0].physicalLocation.region.startLine
}' results.sarif

# 影響を受けるユニークなファイル
jq '[.runs[].results[].locations[].physicalLocation.artifactLocation.uri] | unique | sort' results.sarif

# ファイルごとにグループ化された結果
jq '[.runs[].results[] | {file: .locations[0].physicalLocation.artifactLocation.uri, result: .}] | group_by(.file) | map({file: .[0].file, count: length})' results.sarif
```

## ルール情報

```bash
# 深刻度付きの全ルールをリスト
jq '.runs[].tool.driver.rules[] | {id: .id, name: .name, level: .defaultConfiguration.level}' results.sarif

# ID でルール説明を取得
jq --arg id "RULE001" '.runs[].tool.driver.rules[] | select(.id == $id)' results.sarif

# ヘルプ URL 付きのルール
jq '.runs[].tool.driver.rules[] | select(.helpUri) | {id: .id, help: .helpUri}' results.sarif
```

## フィンガープリント

```bash
# フィンガープリント付きの結果
jq '.runs[].results[] | select(.fingerprints or .partialFingerprints) | {rule: .ruleId, fp: (.fingerprints // .partialFingerprints)}' results.sarif

# すべての部分フィンガープリントを抽出
jq '[.runs[].results[].partialFingerprints] | add' results.sarif
```

## 集約とレポート

```bash
# 深刻度とルール別のサマリー
jq '[.runs[].results[]] | group_by(.level) | map({level: .[0].level, rules: (group_by(.ruleId) | map({rule: .[0].ruleId, count: length}))})' results.sarif

# 最も頻出するルール上位 10
jq '[.runs[].results[]] | group_by(.ruleId) | map({rule: .[0].ruleId, count: length}) | sort_by(-.count) | .[0:10]' results.sarif

# 最も問題の多いファイル
jq '[.runs[].results[] | .locations[0].physicalLocation.artifactLocation.uri] | group_by(.) | map({file: .[0], count: length}) | sort_by(-.count) | .[0:10]' results.sarif
```

## 出力フォーマッティング

```bash
# CSV 形式の出力
jq -r '.runs[].results[] | [.ruleId, .level, .locations[0].physicalLocation.artifactLocation.uri, .locations[0].physicalLocation.region.startLine, .message.text] | @csv' results.sarif

# タブ区切り
jq -r '.runs[].results[] | [.ruleId, .level, .locations[0].physicalLocation.artifactLocation.uri // "N/A"] | @tsv' results.sarif

# Markdown テーブル
echo "| ルール | レベル | ファイル | 行 |"
echo "|------|-------|------|------|"
jq -r '.runs[].results[] | "| \(.ruleId) | \(.level) | \(.locations[0].physicalLocation.artifactLocation.uri // "N/A") | \(.locations[0].physicalLocation.region.startLine // "N/A") |"' results.sarif
```

## 比較と差分

```bash
# file1 にあって file2 にないルールを見つける
comm -23 <(jq -r '[.runs[].results[].ruleId] | unique | sort[]' file1.sarif) <(jq -r '[.runs[].results[].ruleId] | unique | sort[]' file2.sarif)

# 結果数を比較
echo "File 1: $(jq '[.runs[].results[]] | length' file1.sarif)"
echo "File 2: $(jq '[.runs[].results[]] | length' file2.sarif)"
```

## 変換

```bash
# 最小限の SARIF を抽出（結果のみ）
jq '{version: .version, runs: [.runs[] | {tool: {driver: {name: .tool.driver.name}}, results: .results}]}' results.sarif

# エラーのみの新しい SARIF をフィルタして作成
jq '.runs[].results = [.runs[].results[] | select(.level == "error")]' results.sarif > errors-only.sarif

# 複数の SARIF ファイルをマージ
jq -s '{version: "2.1.0", runs: [.[].runs[]]}' file1.sarif file2.sarif > merged.sarif
```

## バリデーションチェック

```bash
# バージョンが 2.1.0 か確認
jq -e '.version == "2.1.0"' results.sarif && echo "Valid version" || echo "Invalid version"

# 空の結果を確認
jq -e '[.runs[].results[]] | length > 0' results.sarif && echo "Has results" || echo "No results"

# すべての結果に位置情報があるか確認
jq '[.runs[].results[] | select(.locations | length == 0)] | length' results.sarif
```
