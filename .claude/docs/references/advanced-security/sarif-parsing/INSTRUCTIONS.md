# SARIF パースのベストプラクティス

あなたは SARIF パースの専門家です。ユーザーが SARIF ファイルを効果的に読み取り、分析、処理するのを支援する役割を担います。

## 使用する場面

このスキルを使用する場面:
- SARIF 形式の静的解析スキャン結果の読み取りまたは解釈
- 複数のセキュリティツールからの検出結果の集約
- セキュリティアラートの重複排除またはフィルタリング
- SARIF ファイルからの特定の脆弱性の抽出
- CI/CD パイプラインへの SARIF データの統合
- SARIF 出力の他のフォーマットへの変換

## 使用しない場面

このスキルを使用しない場面:
- 静的解析スキャンの実行（代わりに CodeQL や Semgrep スキルを使用）
- CodeQL や Semgrep ルールの作成（それぞれのスキルを使用）
- ソースコードの直接分析（SARIF は既存のスキャン結果を処理するためのもの）
- SARIF 入力なしの検出結果のトリアージ（variant-analysis や audit スキルを使用）

## SARIF 構造の概要

SARIF 2.1.0 は現在の OASIS 標準です。すべての SARIF ファイルはこの階層構造を持ちます:

```
sarifLog
├── version: "2.1.0"
├── $schema: （オプション、IDE バリデーションを有効化）
└── runs[]（解析実行の配列）
    ├── tool
    │   ├── driver
    │   │   ├── name（必須）
    │   │   ├── version
    │   │   └── rules[]（ルール定義）
    │   └── extensions[]（プラグイン）
    ├── results[]（検出結果）
    │   ├── ruleId
    │   ├── level（error/warning/note）
    │   ├── message.text
    │   ├── locations[]
    │   │   └── physicalLocation
    │   │       ├── artifactLocation.uri
    │   │       └── region（startLine, startColumn 等）
    │   ├── fingerprints{}
    │   └── partialFingerprints{}
    └── artifacts[]（スキャンされたファイルのメタデータ）
```

### フィンガープリントが重要な理由

安定したフィンガープリントがなければ、実行間で検出結果を追跡できません:

- **ベースライン比較**: 「これは新しい検出結果か、以前にも見たものか？」
- **回帰検出**: 「この PR は新しい脆弱性を導入したか？」
- **抑制**: 「今後の実行でこの既知の誤検知を無視する」

ツールは異なるパスを報告するため（`/path/to/project/` vs `/github/workspace/`）、パスベースのマッチングは失敗します。フィンガープリントは*コンテンツ*（コードスニペット、ルール ID、相対位置）をハッシュして、環境に依存しない安定した識別子を作成します。

## ツール選択ガイド

| ユースケース | ツール | インストール |
|----------|------|--------------|
| 素早い CLI クエリ | jq | `brew install jq` / `apt install jq` |
| Python スクリプティング（シンプル） | pysarif | `pip install pysarif` |
| Python スクリプティング（高度） | sarif-tools | `pip install sarif-tools` |
| .NET アプリケーション | SARIF SDK | NuGet パッケージ |
| JavaScript/Node.js | sarif-js | npm パッケージ |
| Go アプリケーション | garif | `go get github.com/chavacava/garif` |
| バリデーション | SARIF Validator | sarifweb.azurewebsites.net |

## 戦略 1: jq による素早い分析

迅速な探索と一回限りのクエリ向け:

```bash
# 整形表示
jq '.' results.sarif

# 合計検出数をカウント
jq '[.runs[].results[]] | length' results.sarif

# トリガーされたすべてのルール ID をリスト
jq '[.runs[].results[].ruleId] | unique' results.sarif

# エラーのみ抽出
jq '.runs[].results[] | select(.level == "error")' results.sarif

# ファイル位置付きの検出結果を取得
jq '.runs[].results[] | {
  rule: .ruleId,
  message: .message.text,
  file: .locations[0].physicalLocation.artifactLocation.uri,
  line: .locations[0].physicalLocation.region.startLine
}' results.sarif

# 深刻度でフィルタしてルールごとのカウントを取得
jq '[.runs[].results[] | select(.level == "error")] | group_by(.ruleId) | map({rule: .[0].ruleId, count: length})' results.sarif

# 特定ファイルの検出結果を抽出
jq --arg file "src/auth.py" '.runs[].results[] | select(.locations[].physicalLocation.artifactLocation.uri | contains($file))' results.sarif
```

## 戦略 2: pysarif による Python

完全なオブジェクトモデルでのプログラマティックアクセス向け:

```python
from pysarif import load_from_file, save_to_file

# SARIF ファイルを読み込み
sarif = load_from_file("results.sarif")

# runs と results をイテレート
for run in sarif.runs:
    tool_name = run.tool.driver.name
    print(f"Tool: {tool_name}")

    for result in run.results:
        print(f"  [{result.level}] {result.rule_id}: {result.message.text}")

        if result.locations:
            loc = result.locations[0].physical_location
            if loc and loc.artifact_location:
                print(f"    File: {loc.artifact_location.uri}")
                if loc.region:
                    print(f"    Line: {loc.region.start_line}")

# 変更した SARIF を保存
save_to_file(sarif, "modified.sarif")
```

## 戦略 3: sarif-tools による Python

集約、レポート、CI/CD 統合向け:

```python
from sarif import loader

# 単一ファイルを読み込み
sarif_data = loader.load_sarif_file("results.sarif")

# または複数ファイルを読み込み
sarif_set = loader.load_sarif_files(["tool1.sarif", "tool2.sarif"])

# サマリーレポートを取得
report = sarif_data.get_report()

# 深刻度別のヒストグラムを取得
errors = report.get_issue_type_histogram_for_severity("error")
warnings = report.get_issue_type_histogram_for_severity("warning")

# 結果をフィルタ
high_severity = [r for r in sarif_data.get_results()
                 if r.get("level") == "error"]
```

**sarif-tools CLI コマンド:**

```bash
# 検出結果のサマリー
sarif summary results.sarif

# すべての結果を詳細付きでリスト
sarif ls results.sarif

# 深刻度別に結果を取得
sarif ls --level error results.sarif

# 2つの SARIF ファイルを比較（新規/修正済み問題を発見）
sarif diff baseline.sarif current.sarif

# 他のフォーマットに変換
sarif csv results.sarif > results.csv
sarif html results.sarif > report.html
```

## 戦略 4: 複数の SARIF ファイルの集約

複数ツールの結果を結合する場合:

```python
import json
from pathlib import Path

def aggregate_sarif_files(sarif_paths: list[str]) -> dict:
    """複数の SARIF ファイルを1つに結合。"""
    aggregated = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": []
    }

    for path in sarif_paths:
        with open(path) as f:
            sarif = json.load(f)
            aggregated["runs"].extend(sarif.get("runs", []))

    return aggregated

def deduplicate_results(sarif: dict) -> dict:
    """フィンガープリントに基づいて重複検出結果を削除。"""
    seen_fingerprints = set()

    for run in sarif["runs"]:
        unique_results = []
        for result in run.get("results", []):
            # partialFingerprints を使用するか、位置からキーを作成
            fp = None
            if result.get("partialFingerprints"):
                fp = tuple(sorted(result["partialFingerprints"].items()))
            elif result.get("fingerprints"):
                fp = tuple(sorted(result["fingerprints"].items()))
            else:
                # フォールバック: ルール + 位置からフィンガープリントを作成
                loc = result.get("locations", [{}])[0]
                phys = loc.get("physicalLocation", {})
                fp = (
                    result.get("ruleId"),
                    phys.get("artifactLocation", {}).get("uri"),
                    phys.get("region", {}).get("startLine")
                )

            if fp not in seen_fingerprints:
                seen_fingerprints.add(fp)
                unique_results.append(result)

        run["results"] = unique_results

    return sarif
```

## 戦略 5: アクション可能なデータの抽出

```python
import json
from dataclasses import dataclass
from typing import Optional

@dataclass
class Finding:
    rule_id: str
    level: str
    message: str
    file_path: Optional[str]
    start_line: Optional[int]
    end_line: Optional[int]
    fingerprint: Optional[str]

def extract_findings(sarif_path: str) -> list[Finding]:
    """SARIF ファイルから構造化された検出結果を抽出。"""
    with open(sarif_path) as f:
        sarif = json.load(f)

    findings = []
    for run in sarif.get("runs", []):
        for result in run.get("results", []):
            loc = result.get("locations", [{}])[0]
            phys = loc.get("physicalLocation", {})
            region = phys.get("region", {})

            findings.append(Finding(
                rule_id=result.get("ruleId", "unknown"),
                level=result.get("level", "warning"),
                message=result.get("message", {}).get("text", ""),
                file_path=phys.get("artifactLocation", {}).get("uri"),
                start_line=region.get("startLine"),
                end_line=region.get("endLine"),
                fingerprint=next(iter(result.get("partialFingerprints", {}).values()), None)
            ))

    return findings

# フィルタと優先度付け
def prioritize_findings(findings: list[Finding]) -> list[Finding]:
    """深刻度で検出結果をソート。"""
    severity_order = {"error": 0, "warning": 1, "note": 2, "none": 3}
    return sorted(findings, key=lambda f: severity_order.get(f.level, 99))
```

## よくある落とし穴と解決策

### 1. パス正規化の問題

ツールによってパスの報告方法が異なります（絶対、相対、URI エンコード）:

```python
from urllib.parse import unquote
from pathlib import Path

def normalize_path(uri: str, base_path: str = "") -> str:
    """SARIF アーティファクト URI を一貫したパスに正規化。"""
    # file:// プレフィックスがあれば削除
    if uri.startswith("file://"):
        uri = uri[7:]

    # URL デコード
    uri = unquote(uri)

    # 相対パスの処理
    if not Path(uri).is_absolute() and base_path:
        uri = str(Path(base_path) / uri)

    # セパレータの正規化
    return str(Path(uri))
```

### 2. 実行間のフィンガープリント不一致

以下の場合にフィンガープリントが一致しないことがあります:
- 環境間でファイルパスが異なる
- ツールバージョンがフィンガープリントアルゴリズムを変更
- コードが再フォーマットされた（行番号の変更）

**解決策:** 複数のフィンガープリント戦略を使用:

```python
def compute_stable_fingerprint(result: dict, file_content: str = None) -> str:
    """環境非依存のフィンガープリントを計算。"""
    import hashlib

    components = [
        result.get("ruleId", ""),
        result.get("message", {}).get("text", "")[:100],  # 最初の 100 文字
    ]

    # コードスニペットが利用可能な場合追加
    if file_content and result.get("locations"):
        region = result["locations"][0].get("physicalLocation", {}).get("region", {})
        if region.get("startLine"):
            lines = file_content.split("\n")
            line_idx = region["startLine"] - 1
            if 0 <= line_idx < len(lines):
                # 空白を正規化
                components.append(lines[line_idx].strip())

    return hashlib.sha256("".join(components).encode()).hexdigest()[:16]
```

### 3. データの欠落または不完全

SARIF は多くのオプションフィールドを許容します。常に防御的なアクセスを使用:

```python
def safe_get_location(result: dict) -> tuple[str, int]:
    """結果からファイルと行を安全に抽出。"""
    try:
        loc = result.get("locations", [{}])[0]
        phys = loc.get("physicalLocation", {})
        file_path = phys.get("artifactLocation", {}).get("uri", "unknown")
        line = phys.get("region", {}).get("startLine", 0)
        return file_path, line
    except (IndexError, KeyError, TypeError):
        return "unknown", 0
```

### 4. 大規模ファイルのパフォーマンス

非常に大きな SARIF ファイル（100MB 以上）の場合:

```python
import ijson  # pip install ijson

def stream_results(sarif_path: str):
    """ファイル全体を読み込まずに結果をストリーム。"""
    with open(sarif_path, "rb") as f:
        # results 配列をストリーム
        for result in ijson.items(f, "runs.item.results.item"):
            yield result
```

### 5. スキーマバリデーション

不正なファイルを検出するため、処理前にバリデーション:

```bash
# ajv-cli を使用
npm install -g ajv-cli
ajv validate -s sarif-schema-2.1.0.json -d results.sarif

# Python jsonschema を使用
pip install jsonschema
```

```python
from jsonschema import validate, ValidationError
import json

def validate_sarif(sarif_path: str, schema_path: str) -> bool:
    """スキーマに対して SARIF ファイルをバリデーション。"""
    with open(sarif_path) as f:
        sarif = json.load(f)
    with open(schema_path) as f:
        schema = json.load(f)

    try:
        validate(sarif, schema)
        return True
    except ValidationError as e:
        print(f"Validation error: {e.message}")
        return False
```

## CI/CD 統合パターン

### GitHub Actions

```yaml
- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results.sarif

- name: Check for high severity
  run: |
    HIGH_COUNT=$(jq '[.runs[].results[] | select(.level == "error")] | length' results.sarif)
    if [ "$HIGH_COUNT" -gt 0 ]; then
      echo "Found $HIGH_COUNT high severity issues"
      exit 1
    fi
```

### 新規問題での失敗

```python
from sarif import loader

def check_for_regressions(baseline: str, current: str) -> int:
    """ベースラインにない新規問題の数を返す。"""
    baseline_data = loader.load_sarif_file(baseline)
    current_data = loader.load_sarif_file(current)

    baseline_fps = {get_fingerprint(r) for r in baseline_data.get_results()}
    new_issues = [r for r in current_data.get_results()
                  if get_fingerprint(r) not in baseline_fps]

    return len(new_issues)
```

## 主要原則

1. **まずバリデーション**: 処理前に SARIF 構造を確認
2. **オプションを処理**: 多くのフィールドがオプション; 防御的なアクセスを使用
3. **パスを正規化**: ツールによってパスの報告方法が異なる; 早期に正規化
4. **賢くフィンガープリント**: 安定した重複排除のために複数の戦略を組み合わせ
5. **大規模ファイルをストリーム**: 100MB 以上のファイルには ijson 等を使用
6. **思慮深く集約**: ファイル結合時にツールのメタデータを保持

## スキルリソース

すぐに使えるクエリテンプレートは [{baseDir}/resources/jq-queries.md]({baseDir}/resources/jq-queries.md) を参照:
- 一般的な SARIF 操作のための 40 以上の jq クエリ
- 深刻度フィルタリング、ルール抽出、集約パターン

Python ユーティリティは [{baseDir}/resources/sarif_helpers.py]({baseDir}/resources/sarif_helpers.py) を参照:
- `normalize_path()` - ツール固有のパスフォーマットを処理
- `compute_fingerprint()` - パスを無視した安定したフィンガープリント
- `deduplicate_results()` - 実行間で重複を除去

## リファレンスリンク

- [OASIS SARIF 2.1.0 仕様](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html)
- [Microsoft SARIF チュートリアル](https://github.com/microsoft/sarif-tutorials)
- [SARIF SDK (.NET)](https://github.com/microsoft/sarif-sdk)
- [sarif-tools (Python)](https://github.com/microsoft/sarif-tools)
- [pysarif (Python)](https://github.com/Kjeld-P/pysarif)
- [GitHub SARIF サポート](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning)
- [SARIF Validator](https://sarifweb.azurewebsites.net/)
