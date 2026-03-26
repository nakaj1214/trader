# 設定ファイルの解析テクニック

bash スクリプトで `.claude/plugin-name.local.md` ファイルを解析するための完全ガイドです。

## ファイル構造

設定ファイルは YAML フロントマター付きの Markdown を使用します:

```markdown
---
field1: value1
field2: "value with spaces"
numeric_field: 42
boolean_field: true
list_field: ["item1", "item2", "item3"]
---

# Markdown コンテンツ

本文はフロントマターとは別に抽出できます。
プロンプト、ドキュメント、追加コンテキストに使用できます。
```

## フロントマターの解析

### フロントマターブロックの抽出

```bash
#!/bin/bash
FILE=".claude/my-plugin.local.md"

# Extract everything between --- markers (excluding the markers themselves)
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$FILE")
```

**仕組み:**
- `sed -n` - 自動出力を抑制
- `/^---$/,/^---$/` - 最初の `---` から2番目の `---` までの範囲
- `{ /^---$/d; p; }` - `---` 行を削除し、それ以外を出力

### 個別フィールドの抽出

**文字列フィールド:**
```bash
# Simple value
VALUE=$(echo "$FRONTMATTER" | grep '^field_name:' | sed 's/field_name: *//')

# Quoted value (removes surrounding quotes)
VALUE=$(echo "$FRONTMATTER" | grep '^field_name:' | sed 's/field_name: *//' | sed 's/^"\(.*\)"$/\1/')
```

**ブール値フィールド:**
```bash
ENABLED=$(echo "$FRONTMATTER" | grep '^enabled:' | sed 's/enabled: *//')

# Use in condition
if [[ "$ENABLED" == "true" ]]; then
  # Enabled
fi
```

**数値フィールド:**
```bash
MAX=$(echo "$FRONTMATTER" | grep '^max_value:' | sed 's/max_value: *//')

# Validate it's a number
if [[ "$MAX" =~ ^[0-9]+$ ]]; then
  # Use in numeric comparison
  if [[ $MAX -gt 100 ]]; then
    # Too large
  fi
fi
```

**リストフィールド（簡易）:**
```bash
# YAML: list: ["item1", "item2", "item3"]
LIST=$(echo "$FRONTMATTER" | grep '^list:' | sed 's/list: *//')
# Result: ["item1", "item2", "item3"]

# For simple checks:
if [[ "$LIST" == *"item1"* ]]; then
  # List contains item1
fi
```

**リストフィールド（jq を使った適切な解析）:**
```bash
# For proper list handling, use yq or convert to JSON
# This requires yq to be installed (brew install yq)

# Extract list as JSON array
LIST=$(echo "$FRONTMATTER" | yq -o json '.list' 2>/dev/null)

# Iterate over items
echo "$LIST" | jq -r '.[]' | while read -r item; do
  echo "Processing: $item"
done
```

## Markdown 本文の解析

### 本文コンテンツの抽出

```bash
#!/bin/bash
FILE=".claude/my-plugin.local.md"

# Extract everything after the closing ---
# Counts --- markers: first is opening, second is closing, everything after is body
BODY=$(awk '/^---$/{i++; next} i>=2' "$FILE")
```

**仕組み:**
- `/^---$/` - `---` 行にマッチ
- `{i++; next}` - カウンタをインクリメントして `---` 行をスキップ
- `i>=2` - 2番目の `---` 以降のすべての行を出力

**エッジケースの処理:** Markdown 本文に `---` が含まれていても、最初の2つの `---` のみをカウントするため正しく動作します。

### 本文をプロンプトとして使用

```bash
# Extract body
PROMPT=$(awk '/^---$/{i++; next} i>=2' "$RALPH_STATE_FILE")

# Feed back to Claude
echo '{"decision": "block", "reason": "'"$PROMPT"'"}' | jq .
```

**重要:** ユーザーコンテンツを含む JSON 構築には `jq -n --arg` を使用するとより安全です:

```bash
PROMPT=$(awk '/^---$/{i++; next} i>=2' "$FILE")

# Safe JSON construction
jq -n --arg prompt "$PROMPT" '{
  "decision": "block",
  "reason": $prompt
}'
```

## よくある解析パターン

### パターン: デフォルト値付きフィールド

```bash
VALUE=$(echo "$FRONTMATTER" | grep '^field:' | sed 's/field: *//' | sed 's/^"\(.*\)"$/\1/')

# Use default if empty
if [[ -z "$VALUE" ]]; then
  VALUE="default_value"
fi
```

### パターン: オプショナルフィールド

```bash
OPTIONAL=$(echo "$FRONTMATTER" | grep '^optional_field:' | sed 's/optional_field: *//' | sed 's/^"\(.*\)"$/\1/')

# Only use if present
if [[ -n "$OPTIONAL" ]] && [[ "$OPTIONAL" != "null" ]]; then
  # Field is set, use it
  echo "Optional field: $OPTIONAL"
fi
```

### パターン: 複数フィールドの一括解析

```bash
# Parse all fields in one pass
while IFS=': ' read -r key value; do
  # Remove quotes if present
  value=$(echo "$value" | sed 's/^"\(.*\)"$/\1/')

  case "$key" in
    enabled)
      ENABLED="$value"
      ;;
    mode)
      MODE="$value"
      ;;
    max_size)
      MAX_SIZE="$value"
      ;;
  esac
done <<< "$FRONTMATTER"
```

## 設定ファイルの更新

### アトミックな更新

破損を防ぐために、常にテンプファイル + アトミックな移動を使用します:

```bash
#!/bin/bash
FILE=".claude/my-plugin.local.md"
NEW_VALUE="updated_value"

# Create temp file
TEMP_FILE="${FILE}.tmp.$$"

# Update field using sed
sed "s/^field_name: .*/field_name: $NEW_VALUE/" "$FILE" > "$TEMP_FILE"

# Atomic replace
mv "$TEMP_FILE" "$FILE"
```

### 単一フィールドの更新

```bash
# Increment iteration counter
CURRENT=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//')
NEXT=$((CURRENT + 1))

# Update file
TEMP_FILE="${FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT/" "$FILE" > "$TEMP_FILE"
mv "$TEMP_FILE" "$FILE"
```

### 複数フィールドの更新

```bash
# Update several fields at once
TEMP_FILE="${FILE}.tmp.$$"

sed -e "s/^iteration: .*/iteration: $NEXT_ITERATION/" \
    -e "s/^pr_number: .*/pr_number: $PR_NUMBER/" \
    -e "s/^status: .*/status: $NEW_STATUS/" \
    "$FILE" > "$TEMP_FILE"

mv "$TEMP_FILE" "$FILE"
```

## バリデーションテクニック

### ファイルの存在と読み取り可能性の確認

```bash
FILE=".claude/my-plugin.local.md"

if [[ ! -f "$FILE" ]]; then
  echo "Settings file not found" >&2
  exit 1
fi

if [[ ! -r "$FILE" ]]; then
  echo "Settings file not readable" >&2
  exit 1
fi
```

### フロントマター構造のバリデーション

```bash
# Count --- markers (should be exactly 2 at start)
MARKER_COUNT=$(grep -c '^---$' "$FILE" 2>/dev/null || echo "0")

if [[ $MARKER_COUNT -lt 2 ]]; then
  echo "Invalid settings file: missing frontmatter markers" >&2
  exit 1
fi
```

### フィールド値のバリデーション

```bash
MODE=$(echo "$FRONTMATTER" | grep '^mode:' | sed 's/mode: *//')

case "$MODE" in
  strict|standard|lenient)
    # Valid mode
    ;;
  *)
    echo "Invalid mode: $MODE (must be strict, standard, or lenient)" >&2
    exit 1
    ;;
esac
```

### 数値範囲のバリデーション

```bash
MAX_SIZE=$(echo "$FRONTMATTER" | grep '^max_size:' | sed 's/max_size: *//')

if ! [[ "$MAX_SIZE" =~ ^[0-9]+$ ]]; then
  echo "max_size must be a number" >&2
  exit 1
fi

if [[ $MAX_SIZE -lt 1 ]] || [[ $MAX_SIZE -gt 10000000 ]]; then
  echo "max_size out of range (1-10000000)" >&2
  exit 1
fi
```

## エッジケースと注意点

### 値のクォート

YAML ではクォートありとなしの両方の文字列が使用できます:

```yaml
# These are equivalent:
field1: value
field2: "value"
field3: 'value'
```

**両方に対応:**
```bash
# Remove surrounding quotes if present
VALUE=$(echo "$FRONTMATTER" | grep '^field:' | sed 's/field: *//' | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\\(.*\\)'$/\\1/")
```

### Markdown 本文内の ---

Markdown 本文に `---` が含まれていても、最初の2つだけをマッチするため解析は正しく動作します:

```markdown
---
field: value
---

# 本文

これはセパレータです:
---

セパレータの後のコンテンツ。
```

`awk '/^---$/{i++; next} i>=2'` パターンはこれを正しく処理します。

### 空の値

欠落または空のフィールドの処理:

```yaml
field1:
field2: ""
field3: null
```

**解析:**
```bash
VALUE=$(echo "$FRONTMATTER" | grep '^field1:' | sed 's/field1: *//')
# VALUE will be empty string

# Check for empty/null
if [[ -z "$VALUE" ]] || [[ "$VALUE" == "null" ]]; then
  VALUE="default"
fi
```

### 特殊文字

特殊文字を含む値は注意深い処理が必要です:

```yaml
message: "Error: Something went wrong!"
path: "/path/with spaces/file.txt"
regex: "^[a-zA-Z0-9_]+$"
```

**安全な解析:**
```bash
# Always quote variables when using
MESSAGE=$(echo "$FRONTMATTER" | grep '^message:' | sed 's/message: *//' | sed 's/^"\(.*\)"$/\1/')

echo "Message: $MESSAGE"  # Quoted!
```

## パフォーマンス最適化

### 解析結果のキャッシュ

設定を複数回読み取る場合:

```bash
# Parse once
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$FILE")

# Extract multiple fields from cached frontmatter
FIELD1=$(echo "$FRONTMATTER" | grep '^field1:' | sed 's/field1: *//')
FIELD2=$(echo "$FRONTMATTER" | grep '^field2:' | sed 's/field2: *//')
FIELD3=$(echo "$FRONTMATTER" | grep '^field3:' | sed 's/field3: *//')
```

**やってはいけないこと:** 各フィールドごとにファイルを再解析すること。

### 遅延読み込み

必要な場合のみ設定を解析する:

```bash
#!/bin/bash
input=$(cat)

# Quick checks first (no file I/O)
tool_name=$(echo "$input" | jq -r '.tool_name')
if [[ "$tool_name" != "Write" ]]; then
  exit 0  # Not a write operation, skip
fi

# Only now check settings file
if [[ -f ".claude/my-plugin.local.md" ]]; then
  # Parse settings
  # ...
fi
```

## デバッグ

### 解析された値の出力

```bash
#!/bin/bash
set -x  # Enable debug tracing

FILE=".claude/my-plugin.local.md"

if [[ -f "$FILE" ]]; then
  echo "Settings file found" >&2

  FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$FILE")
  echo "Frontmatter:" >&2
  echo "$FRONTMATTER" >&2

  ENABLED=$(echo "$FRONTMATTER" | grep '^enabled:' | sed 's/enabled: *//')
  echo "Enabled: $ENABLED" >&2
fi
```

### 解析のバリデーション

```bash
# Show what was parsed
echo "Parsed values:" >&2
echo "  enabled: $ENABLED" >&2
echo "  mode: $MODE" >&2
echo "  max_size: $MAX_SIZE" >&2

# Verify expected values
if [[ "$ENABLED" != "true" ]] && [[ "$ENABLED" != "false" ]]; then
  echo "  Unexpected enabled value: $ENABLED" >&2
fi
```

## 代替手段: yq の使用

複雑な YAML の場合、`yq` の使用を検討してください:

```bash
# Install: brew install yq

# Parse YAML properly
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$FILE")

# Extract fields with yq
ENABLED=$(echo "$FRONTMATTER" | yq '.enabled')
MODE=$(echo "$FRONTMATTER" | yq '.mode')
LIST=$(echo "$FRONTMATTER" | yq -o json '.list_field')

# Iterate list properly
echo "$LIST" | jq -r '.[]' | while read -r item; do
  echo "Item: $item"
done
```

**利点:**
- 適切な YAML 解析
- 複雑な構造に対応
- リスト/オブジェクトのサポートが充実

**欠点:**
- yq のインストールが必要
- 追加の依存関係
- すべてのシステムで利用可能とは限らない

**推奨:** シンプルなフィールドには sed/grep を、複雑な構造には yq を使用。

## 完全な例

```bash
#!/bin/bash
set -euo pipefail

# Configuration
SETTINGS_FILE=".claude/my-plugin.local.md"

# Quick exit if not configured
if [[ ! -f "$SETTINGS_FILE" ]]; then
  # Use defaults
  ENABLED=true
  MODE=standard
  MAX_SIZE=1000000
else
  # Parse frontmatter
  FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$SETTINGS_FILE")

  # Extract fields with defaults
  ENABLED=$(echo "$FRONTMATTER" | grep '^enabled:' | sed 's/enabled: *//')
  ENABLED=${ENABLED:-true}

  MODE=$(echo "$FRONTMATTER" | grep '^mode:' | sed 's/mode: *//' | sed 's/^"\(.*\)"$/\1/')
  MODE=${MODE:-standard}

  MAX_SIZE=$(echo "$FRONTMATTER" | grep '^max_size:' | sed 's/max_size: *//')
  MAX_SIZE=${MAX_SIZE:-1000000}

  # Validate values
  if [[ "$ENABLED" != "true" ]] && [[ "$ENABLED" != "false" ]]; then
    echo "  Invalid enabled value, using default" >&2
    ENABLED=true
  fi

  if ! [[ "$MAX_SIZE" =~ ^[0-9]+$ ]]; then
    echo "  Invalid max_size, using default" >&2
    MAX_SIZE=1000000
  fi
fi

# Quick exit if disabled
if [[ "$ENABLED" != "true" ]]; then
  exit 0
fi

# Use configuration
echo "Configuration loaded: mode=$MODE, max_size=$MAX_SIZE" >&2

# Apply logic based on settings
case "$MODE" in
  strict)
    # Strict validation
    ;;
  standard)
    # Standard validation
    ;;
  lenient)
    # Lenient validation
    ;;
esac
```

これにより、デフォルト値、バリデーション、エラーリカバリを備えた堅牢な設定処理が実現されます。
