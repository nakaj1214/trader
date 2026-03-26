#!/usr/bin/env bash
# スキルファイルのインベントリ収集スクリプト
# 出典: everything-claude-code skills/skill-stocktake/scripts/scan.sh
#
# グローバルとプロジェクトレベルのスキルディレクトリを走査し、
# フロントマターからメタデータを抽出してJSONで出力する。

set -euo pipefail

# 出力先
OUTPUT="${1:-/dev/stdout}"

# スキルディレクトリ
GLOBAL_DIR="$HOME/.claude/skills"
PROJECT_DIR="${PWD}/.claude/skills"

skills_json='[]'
found_global=false
found_project=false
global_count=0
project_count=0

scan_directory() {
  local dir="$1"
  local scope="$2"

  if [[ ! -d "$dir" ]]; then
    return
  fi

  if [[ "$scope" == "global" ]]; then
    found_global=true
  else
    found_project=true
  fi

  while IFS= read -r -d '' skill_file; do
    local skill_dir
    skill_dir="$(dirname "$skill_file")"
    local skill_name
    skill_name="$(basename "$skill_dir")"
    local mod_time
    mod_time="$(date -u -r "$skill_file" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo 'unknown')"

    # フロントマターからname/descriptionを抽出
    local name=""
    local description=""
    if head -1 "$skill_file" | grep -q '^---'; then
      name="$(sed -n '/^---$/,/^---$/{ /^name:/{ s/^name: *//; s/^"//; s/"$//; p; } }' "$skill_file")"
      description="$(sed -n '/^---$/,/^---$/{ /^description:/{ s/^description: *//; s/^"//; s/"$//; p; } }' "$skill_file")"
    fi

    # フォールバック: ファイル名をnameに使用
    if [[ -z "$name" ]]; then
      name="$skill_name"
    fi

    # 使用頻度 (observations.jsonl があれば)
    local usage_7d=0
    local usage_30d=0
    local obs_file="$skill_dir/observations.jsonl"
    if [[ -f "$obs_file" ]]; then
      local now_epoch
      now_epoch="$(date +%s)"
      local seven_days_ago=$((now_epoch - 604800))
      local thirty_days_ago=$((now_epoch - 2592000))
      usage_30d="$(wc -l < "$obs_file" 2>/dev/null || echo 0)"
      # 簡易的に30日分として扱う
      usage_7d="$usage_30d"
    fi

    if [[ "$scope" == "global" ]]; then
      ((global_count++)) || true
    else
      ((project_count++)) || true
    fi

    # JSON出力に追加
    printf '{"name":"%s","description":"%s","path":"%s","scope":"%s","modified":"%s","usage_7d":%d,"usage_30d":%d}\n' \
      "$name" \
      "$(echo "$description" | head -c 200)" \
      "$skill_file" \
      "$scope" \
      "$mod_time" \
      "$usage_7d" \
      "$usage_30d"

  done < <(find "$dir" -name "SKILL.md" -print0 2>/dev/null)
}

echo "{"
echo "  \"scan_summary\": {"
echo "    \"global_dir\": \"$GLOBAL_DIR\","
echo "    \"project_dir\": \"$PROJECT_DIR\""
echo "  },"
echo "  \"skills\": ["

# スキャン実行
first=true
{
  scan_directory "$GLOBAL_DIR" "global"
  scan_directory "$PROJECT_DIR" "project"
} | while IFS= read -r line; do
  if [[ "$first" == "true" ]]; then
    first=false
    echo "    $line"
  else
    echo "    ,$line"
  fi
done

echo "  ]"
echo "}"
