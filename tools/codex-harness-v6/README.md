# Adaptive Codex Harness v6 — Quality-first, bounded execution

v5までのSmart Saverを整理統合し、第1〜4段階の仕組みを「通常経路を重くしない」形でまとめたアップグレーダーです。

## 方針

- GPT-5.6 Sol + highを固定。
- 通常は親Agent 1つ。明確に独立した重いworkstreamだけ最大2 Subagent。
- 大量ログ・大規模diff・重複探索を抑制。
- テストはrisk-based minimal regression。既存のまとまりへ追記を優先。
- Self Test / Version Migrationはinstall時に強制。
- 破壊的操作はCodex公式project rulesでapprovalへ送る。
- Architecture Checkはchanged-file ratchet。初期は`advisory`、ルールは空。
- Observabilityはローカルの件数/サイズ指標だけ。command本文・tool output本文は保存しない。
- Task Stateは長期/複数セッション時だけ手動使用。
- Harness Auditは手動。

## 導入

プロジェクト直下の`tools/`へ展開:

```text
project/
├─ AGENTS.md
├─ .codex/
├─ .agents/
├─ src/
└─ tools/
   └─ codex-harness-v6/
      ├─ install.py
      └─ payload/
```

確認:

```bash
python3 tools/codex-harness-v6/install.py --dry-run
```

反映:

```bash
python3 tools/codex-harness-v6/install.py
```

installerは変更対象を`.codex-harness-backup/v6-<timestamp>/`へ退避し、適用後Self Testに失敗した場合は自動rollbackします。

## 保持するプロジェクト固有資産

- `docs/`
- `memo/`
- `.codex/harness/commands.json` のコマンド定義（ログ予算だけ上限調整）
- `.codex/harness/config.json` の未知/既存プロジェクト設定
- 既存 `.codex/harness/architecture_rules.json`（存在する場合）
- 既存hooks（v6 telemetry hooksをmerge）

## Project rootがGit rootと異なる場合

Codexは既定で`.git`をproject rootとして扱うため、`project/src/.git`でHarnessが`project/.codex`にある構成では、Codexをworkspace rootから起動してください。

```bash
./.codex/harness/bin/codex-project
```

v6はuser-level `~/.codex/config.toml`を勝手に変更しません。

## v6で追加される主なもの

```text
.codex/
├─ rules/harness-safety.rules
├─ agents/*.toml
└─ harness/
   ├─ VERSION
   ├─ architecture_rules.json
   ├─ bin/codex-project
   └─ scripts/
      ├─ selftest.py
      ├─ architecture_check.py
      ├─ telemetry_hook.py
      ├─ telemetry_report.py
      ├─ harness_audit.py
      └─ task_state.py
```

## Architecture Ratchet

初期設定は次の通りで、何も強制しません。

```json
{
  "schema_version": 1,
  "mode": "advisory",
  "rules": []
}
```

実際に繰り返し発生するプロジェクト固有の逸脱だけを後からルール化してください。既存負債を一括修正する目的ではありません。

## Observability

```bash
python3 .codex/harness/scripts/telemetry_report.py --days 7
```

保存するのはevent/tool種別、command文字数、responseサイズ、Subagent起動数などです。command本文やtool output本文は保存しません。

## Harness audit

```bash
python3 .codex/harness/scripts/harness_audit.py
```

通常タスクごとに実行する必要はありません。Harness変更時や定期棚卸し用です。
