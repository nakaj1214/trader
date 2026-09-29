# trader 自己学習機能：旧v2データ取り込みに関する現状の問題

作成日: 2026-09-14

## 1. 背景

`trader` リポジトリでは、自己学習機能を使って以下を蓄積・分析する方針になっている。

- 予測が外れた理由
- 爆発銘柄が爆発した要因
- 各factorと将来リターンの関係
- 将来のstrategy改善候補

現在、以下の旧3日分の暗号化スナップショットが存在する。

- `dashboard/data/inflection/2026-09-09.enc`
- `dashboard/data/inflection/2026-09-10.enc`
- `dashboard/data/inflection/2026-09-11.enc`

これらは、現在のv3とは異なる旧strategyで生成されている。

- strategy: `jp-inflection-shadow-v2`
- report schema: `3`

一方、現在の自己学習・forward validation系は主に以下を対象としている。

- strategy: `jp-inflection-shadow-v3`
- report schema: `4`
- 保存先: `dashboard/data/inflection/v3/`

---

## 2. 旧3日分をそのままv3へ移してはいけない理由

旧v2/schema3と現行v3/schema4では、候補データの意味・定義が一部異なる。

代表例として、旧v2には以下の項目がある。

- `breakout_52w`

現行v3では、これがより明確に分離されている。

- `near_52w_high`
- `near_listing_high`

旧 `breakout_52w` は、短い上場履歴の銘柄でも取得可能期間内の高値を基準としていたため、
現行の `near_52w_high` と完全に同じ意味ではない。

そのため、以下のような変換は不適切。

```text
旧 breakout_52w = True
        ↓
near_52w_high = True
```

これは元データの意味を変えてしまい、学習結果を歪める可能性がある。

### 安全な扱い

旧データはそのまま保持し、学習側でのみ互換変換する。

例:

```text
legacy_breakout_52w: true
```

として、現行factorとは別物として扱う。

---

## 3. 旧ファイルは移動・変更しない

推奨する保存構成は以下。

```text
dashboard/data/inflection/
├─ 2026-09-09.enc   # v2/schema3
├─ 2026-09-10.enc   # v2/schema3
├─ 2026-09-11.enc   # v2/schema3
└─ v3/
   ├─ 2026-09-14.enc
   ├─ 2026-09-15.enc
   └─ ...
```

旧3ファイルは、

- リネームしない
- v3ディレクトリへ移動しない
- 再暗号化しない
- 中身を書き換えない

方針とする。

自己学習loaderだけが、

- root直下の旧schema3
- `v3/` 配下のschema4

を別々に読み込む。

---

## 4. 今回新たに見つかった重要な問題

現在の自己学習ロジックでは、promotion対象のstrategyを次の方法で決めている。

> 読み込んだ観測データのうち、最も新しい日付のデータが持つ `strategy_version`

つまり概念上は以下。

```text
latest_observation
    ↓
latest_strategy_version
    ↓
promotion対象strategy
```

これは通常は問題ないが、今回旧v2データを自己学習へ追加すると問題になる。

### 問題ケース

例えばv3スナップショットがまだ存在しない、または読み込みに失敗した場合、

```text
2026-09-09 v2
2026-09-10 v2
2026-09-11 v2
```

しか自己学習側から見えない。

すると、

```text
latest_strategy_version = jp-inflection-shadow-v2
```

となり、旧v2がpromotion対象と判定される。

---

## 5. 「3日しかないから安全」とは限らない

現在のpromotion条件には、最低観測数として以下が設定されている。

```text
PROMOTION_MIN_OBSERVATIONS = 30
```

ここで注意すべきなのは、

**30日ではなく30 observationである**

という点。

1日あたり最大25候補を保存している場合、

```text
25候補 × 3日 = 最大75 observations
```

となる。

そのため、たった3日分でも条件上は30件を超える可能性がある。

その結果、旧v2のfactor統計から、

- `positive_candidate`
- `negative_candidate`

が生成される可能性がある。

これは意図しない。

---

## 6. 推奨する安全な設計

旧v2は「学習材料」として使うが、
現行strategyのpromotion判定には使わない。

### v2/schema3

用途:

- 過去予測の事後分析
- 予測失敗原因の蓄積
- 爆発銘柄の特徴分析
- factor統計の参考
- strategy間比較

使用しない用途:

- 現行strategyのpromotion判定
- production weight変更候補の生成

### v3/schema4

用途:

- 累積分析
- prediction miss分析
- 爆発銘柄分析
- factor統計
- promotion候補判定

---

## 7. promotion対象を明示的にする

現在の

```text
最新日付のstrategy = promotion対象
```

という暗黙的な判定をやめる。

以下のどちらかを推奨。

### 案A: production strategyを明示指定

例:

```python
PROMOTION_STRATEGY_VERSION = "jp-inflection-shadow-v3"
```

自己学習レポートでは、

```text
promotion_scope_strategy_version = jp-inflection-shadow-v3
```

を明示する。

### 案B: CLI引数で指定

例:

```bash
python scripts/rebuild_inflection_learning.py   --promotion-strategy-version jp-inflection-shadow-v3
```

将来v4へ移行した場合も明示的に変更できる。

### 推奨

案B。

理由:

- 将来strategy versionが増えてもコード変更不要
- GitHub Actions側でproduction strategyを明示できる
- 誤って旧strategyがpromotion対象になる事故を防げる
- テストしやすい

---

## 8. 推奨する最終構成

```text
v2/schema3 snapshots
        ↓
legacy schema loader
        ↓
canonical learning observation
        ↓
strategy_version = v2 を保持
legacy_breakout_52w を保持
        ↓
累積分析 / postmortem
        │
        └─ promotionには使用しない


v3/schema4 snapshots
        ↓
current schema loader
        ↓
canonical learning observation
        ↓
strategy_version = v3 を保持
near_52w_high / near_listing_high を保持
        ↓
累積分析 / postmortem
        ↓
promotion対象
```

---

## 9. forward validationとの分離

forward validationは今まで通り、

```text
dashboard/data/inflection/v3/
```

のみを見る。

旧v2はforward validationへ混ぜない。

理由:

- strategy定義が違う
- schemaが違う
- forward validationの同一条件比較を壊さないため

つまり、

```text
forward validation
→ v3のみ

self-learning
→ v2 + v3

promotion
→ v3のみ
```

とする。

---

## 10. 実装時に必要なテスト

最低限、以下を追加する。

### schema3互換読込

- v2/schema3を正常に読み込める
- `breakout_52w` を `near_52w_high` に変換しない
- `legacy_breakout_52w` として保持する
- `strategy_version=v2` を保持する

### schema4読込

- 現行v3/schema4の挙動を変更しない
- `near_52w_high`
- `near_listing_high`

を従来通り保持する

### 複数strategy混在

v2 + v3を同時に読み込んでも、

- cumulative analysisには両方入る
- promotion statisticsにはv3のみ入る

ことを確認する。

### v3が存在しない場合

v2だけ存在しても、

```text
promotion_scope_strategy_version = v3
promotion observations = 0
lessons = []
```

などとなり、

**v2からpromotion候補が生成されない**

ことを確認する。

### duplicate対策

将来同じ日付・tickerが複数strategyに存在した場合も誤って消さないよう、

```text
(signal_date, ticker, strategy_version)
```

単位で識別することを検討する。

---

## 11. 現在の実装状況（2026-09-14 対応済み）

セクション12の方針1〜3, 5, 6, 8を実装した。

- `build_learning_report()` に `promotion_strategy_version` を必須引数として追加。
  「最新observationのstrategy」ではなく明示指定した値でpromotion対象をgateする。
- `scripts/rebuild_inflection_learning.py` に `--promotion-strategy-version`
  （デフォルト `jp-inflection-shadow-v3`）を追加し、CIからも明示指定するようにした。
- `load_inflection_learning_observations()` がschema 3とschema 4の両方を読み込めるよう
  拡張。schema 3の `breakout_52w` は `legacy_breakout_52w` として保持し、
  `near_52w_high` / `near_listing_high` には一切マッピングしない。
- `--legacy-snapshot-dir`（デフォルト `dashboard/data/inflection` 直下）を追加し、
  root直下の旧3日分もself-learningの累積分析に取り込むようにした。promotion統計には
  含まれない。
- `factor_labels()` は値が存在するフィールドのみラベル化するよう変更（schema3行に
  `near_52w_high` ラベルが付かないようにするため）。

- 旧3ファイルの移動・リネーム・再暗号化・中身変更: なし（方針どおり維持）
- 追加テスト: `tests/test_inflection_learning.py` にschema3読込・legacy専用エラー・
  「legacyのみでpromotion候補ゼロ」「新しい日付のlegacyがpromotion対象を乗っ取らない」
  回帰テストを追加。全255テストがpass。

未実施（セクション12の4, 7, 9, 10）:

- v2+v3混在時の重複キー対策 `(signal_date, ticker, strategy_version)` は将来課題のまま
- mainへのマージ判断はユーザー側で実施

---

## 12. 次に実装する場合の方針

安全に実装する場合は、次の順序を推奨する。

1. promotion strategyを明示指定できるようにする
2. schema3専用legacy loaderを追加
3. v2の `breakout_52w` をlegacy factorとして保持
4. root直下の旧3日分もself-learningへ取り込む
5. v2 + v3の累積分析を可能にする
6. promotionはv3のみに限定
7. forward validationはv3のみのまま維持
8. テスト追加
9. CIで確認
10. 問題がなければmainへ反映

---

## 結論

旧3日分は捨てる必要はなく、自己学習の材料として利用価値がある。

ただし、

**旧v2/schema3を現行v3/schema4として扱ってはいけない。**

また、

**旧データを取り込む前に、promotion対象strategyを明示的に固定・指定できるようにする必要がある。**

最終的には以下の分離が安全。

```text
分析:
v2 + v3

promotion:
v3のみ

forward validation:
v3のみ
```
