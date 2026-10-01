# 実装要件書（REQ-042〜044: 価格取得の共通化と、自己学習の昇格判定の統計的補強）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の A4・A5（propose-one で選択）。
> 以前の要件書: REQ-001〜036 → [proposal_req001-036.md](proposal_req001-036.md)、REQ-037〜038 → [proposal_req037-038.md](proposal_req037-038.md)、REQ-039〜041（B1、実装済み・未コミット）→ [proposal_req039-041.md](proposal_req039-041.md)

## 背景

- **A4:** 週次の forward validation は、価格を1銘柄ずつ `yf.Ticker().history()` で取得し、各呼び出しの間に 0.5 秒待つ。これを価格基準2種類（配当込み・分割のみ）で2回行い、ベンチマークも別に取得する。同じ CI job の中で、learning もほぼ同じ銘柄を別途バッチで取得し直す。job の制限時間は30分である。deep candidate は1日25銘柄（schema 5 以降は対照群を含めて最大50銘柄）ずつ増えるので、数か月で制限時間を超える。
- **A5:** 自己学習の昇格判定は「独立観測30件以上、爆発率の lift ≥ 1.35、平均超過リターン > 0」だけで、有意性の検定も多重比較の補正もない。factor ラベル（約40種）× horizon（4つ）≒ 160通りを毎週見るため、偶然だけで「positive_candidate」が出る。また「爆発」の定義が3か所でばらばらで、同じ言葉で意味の違う値が集計されている。

## 共通の設計判断

- **戦略と snapshot は変えない。** `STRATEGY_VERSION`、`REPORT_SCHEMA_VERSION`、スコア計算、分類は一切変えない。評価・学習側だけの変更である。
- **本番の重みは引き続き自動更新しない。** 昇格判定を厳しくするだけで、「次期 strategy への提案に限る」という現設計は維持する。
- **A3 の許容範囲（取得失敗が5%以下なら継続）を維持する。**

---

## 要件一覧

### REQ-042: forward と learning の価格取得を1つのバッチ取得に共通化し、同じ CI job 内で使い回す（A4）

- **画面**: なし（週次 CI `forward_validation.yml` の処理）
- **対象ファイル**:
  - 新規: `src/data/forward_prices.py`
  - 変更: [scripts/rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)（`_fetch_adjusted_histories` の置き換え）
  - 変更: [scripts/rebuild_inflection_learning.py](../../scripts/rebuild_inflection_learning.py)（`_fetch_learning_histories` の置き換え）
  - 変更（必要な場合のみ）: [.github/workflows/forward_validation.yml](../../.github/workflows/forward_validation.yml)
  - テスト: `tests/test_inflection_forward.py`、`tests/test_inflection_learning.py`、新規 `tests/test_forward_prices.py`
- **Before（現状）**:
  - forward: `_fetch_adjusted_histories` を3回呼ぶ（total return 基準、split only 基準、ベンチマーク）。いずれも1銘柄ずつ `history()` を呼び、0.5秒待つ。
  - learning: `_fetch_learning_histories` で、50銘柄単位の `yf.download(auto_adjust=True)` を使って全銘柄を取り直す。
  - 両スクリプトは同じ job の中で順に実行されるが、データを共有しない。
- **After（期待）**:
  - `src/data/forward_prices.py` に、**生の OHLC と企業行動（配当・分割）を50銘柄単位のバッチで1回だけ取得し**、そこから2つの価格基準を導出する関数を置く。
    - total return 基準: 現在の `auto_adjust=True` の結果と同じ値（yfinance と同じく、`Adj Close / Close` の比を O/H/L/C に掛ける）
    - split only 基準: 現在の `history(auto_adjust=False, actions=True)` → `split_adjust_ohlc(...)` の結果と同じ値
  - **取得結果の値は、現行の処理と一致させる（挙動は変えない）。** 価格ハッシュ（`inflection_forward_price_hashes.enc`）が、切り替えだけを理由に「改訂」として大量に記録されないようにするためである。
  - 取得期間は、全銘柄共通で「最も早いシグナル日 − 45日」〜「今日 + 1日」とする（ベンチマークの20日 regime の計算に必要な35日分を含む）。
  - 取得した生データを、同じ job の中だけで使うローカルキャッシュ（gitignore 済みの `artifacts/price_cache/`）に保存する。learning は、キャッシュに含まれない銘柄だけを追加で取得する。
  - 再試行、取得失敗の許容（5%）、yfinance のログ抑制（銘柄名をログに出さない）は、現行と同じ規則にする。
- **受入条件**:
  1. 同じ生データ（モック）から導出した2つの基準の値が、現行の `_fetch_adjusted_histories` の結果（それぞれの基準）と一致する。日付の index も含めて一致させ、価格ハッシュが変わらないことを確かめる。
  2. 100銘柄の取得で、yfinance の呼び出しが「バッチ数（2回）」で済み、銘柄ごとの `history()` 呼び出しがない。
  3. forward のあとに learning を実行すると、learning は forward が取得済みの銘柄を再取得しない（呼び出し回数で検証）。
  4. 取得失敗が5%以下なら継続し、5%を超えたら停止する（A3 の規則を維持）。ベンチマークの取得に失敗したら停止する。
  5. 例外やログに銘柄名が出ない（既存の秘匿テストを維持する）。
  6. `pytest tests/`、ruff、mypy が PASS する。
- **備考**:
  - yfinance の `download()` は、`actions` を銘柄ごとの `history()` にそのまま渡し、`history()` が `Dividends` / `Stock Splits` の列を削るのは `actions=False` のときだけである（yfinance 1.7.0 の `multi.py` L117・L169・L182、`scrapers/history.py` L620 で確認済み）。したがって、`download(auto_adjust=False, actions=True)` の1回の取得で、両方の基準を導出できる。
  - 実データでの同等性（新旧の取得で値が一致するか）は、実装後に少数の銘柄で手動確認する。

### REQ-043: 自己学習の昇格判定に、有意性検定と多重比較補正を入れる（A5 前半）

- **画面**: なし（`artifacts/inflection_learning*.json`）
- **対象ファイル**:
  - 変更: [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py)（`_factor_statistics`、`_lessons`、`build_learning_report` の `promotion_gate`）
  - テスト: `tests/test_inflection_learning.py`
- **Before（現状）**: factor ごとに、独立観測 ≥ 30、`explosion_rate_lift` ≥ 1.35（負の方向は ≤ 0.75）、平均超過リターンの符号だけで `positive_candidate` / `negative_candidate` を決める。検定も多重比較の補正もない。
- **After（期待）**:
  - 各 factor・各 horizon について、「その factor を持つ観測」と「持たない観測」の爆発の有無で2×2表を作り、**Fisher の正確検定**（片側。positive は「多い」方向、negative は「少ない」方向）の p 値を計算する。scipy は依存に含まれていないため、`math.comb` による超幾何分布で実装する。
  - 昇格の判定対象（`promotion_strategy_version` の行）の全 factor × 全 horizon の p 値に **Benjamini–Hochberg 法**を適用し、q 値を計算する。
  - 昇格の条件を次のすべてを満たすことに変える。
    1. 独立観測 ≥ 30（現行どおり）
    2. lift の閾値（現行どおり）
    3. 平均超過リターンの符号（現行どおり）
    4. **q 値 ≤ 0.10**（新規。`PROMOTION_MAX_Q_VALUE` として定数化する）
  - factor の統計に、`fisher_p_value`、`bh_q_value`、爆発率の **Wilson 95% 信頼区間**を追加する。
  - `promotion_gate` に、検定方法、補正方法、q 値の閾値、検定した数を記録する。
  - 公開用のサマリー（`public_learning_summary`）にも、これらの集計値を含める（銘柄名は含まない）。
- **受入条件**:
  1. Fisher の正確検定の p 値が、既知の値（教科書の例、または手計算した小さな表）と一致する。
  2. 爆発率の差が大きく件数も多い factor は昇格し、lift は閾値を超えるが件数が少なく q 値が大きい factor は昇格しない。
  3. 160通りの検定のうち1つだけが偶然 p ≈ 0.04 になる合成データで、BH 補正後は昇格しない。
  4. BH 法の q 値が、既知の例で正しい（単調性の補正を含む）。
  5. 爆発がまったくない、または全件が爆発の場合に、例外にならず p = 1 などの妥当な値を返す。
  6. 既存の learning テストが、昇格の判定以外は変わらず PASS する。
- **備考**: Beta-Binomial による縮小推定（レポート §4.2）は、Fisher 検定と BH 補正で偶然の昇格を十分に抑えられるため、今回は入れない。

### REQ-044: 「爆発」の定義を1か所に集約し、ボラティリティで正規化した定義を併記する（A5 後半）

- **画面**: なし
- **対象ファイル**:
  - 新規: `src/evaluation/explosion.py`
  - 変更: [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py)、[src/evaluation/inflection_recall.py](../../src/evaluation/inflection_recall.py)、[src/evaluation/inflection_backtest.py](../../src/evaluation/inflection_backtest.py)
  - テスト: 新規 `tests/test_explosion.py`、既存テスト
- **Before（現状）**: 「爆発」の定義が3つあり、それぞれのファイルに直接書かれている。
  - learning: horizon 別の最大リターンの閾値（h5 15%、h20 25%、h60 40%、h120 60%）
  - backtest: `explosive_50pct`（保有期間中の最大リターン ≥ 50%）
  - recall: 最初の観測日から252営業日以内に、終値が +50%
- **After（期待）**:
  - `src/evaluation/explosion.py` に3つの定義を名前付きの定数として集約し、それぞれの意味をコメントで明記する。3つのモジュールはそこから import する。**値は変えない**（既存の集計結果を変えないため）。
  - learning と forward のレポートに、使った定義の一覧（`explosion_definitions`）を出す。
  - **ボラティリティで正規化した爆発**を、learning の各 horizon に**診断用の追加フィールド**として加える。
    - 定義: シグナル日までの60営業日の日次リターンの標準偏差を σ とし、保有期間中の最大リターン ≥ k × σ × √h（`k` は定数、既定 3.0）
    - σ の計算にはシグナル日以前のデータだけを使う（先読みしない）
    - 昇格判定には使わない（既存の爆発の定義を使い続ける）。値の動き方を見てから、別要件で採否を判断する。
    - `k` の既定値は 3.0 とする（`VOL_EXPLOSION_K` として定数化）。根拠: ドリフトのないランダムウォークでは、h 日間の最大値が 3σ√h を超える確率は反射原理により約 0.27%（2 × P(Z > 3)）である。「ノイズでは説明しにくい上昇」を示す目安として妥当である。診断用なので、後から変えても昇格判定には影響しない（2026-10-01、ユーザーから判断を一任）。
- **受入条件**:
  1. 3つのモジュールが `explosion.py` の定数を参照し、ファイル内に閾値の数値が直接書かれていない（grep で確認する）。
  2. 既存の learning・forward・recall のテストが変更なしで PASS する（値が変わっていない）。
  3. ボラティリティ正規化の爆発で、σ の計算にシグナル日より後のデータを使っていない（シグナル日より後の価格を変えても σ が変わらない）。
  4. 60営業日の履歴がない銘柄では、正規化の爆発が `None` になり、例外にならない。
  5. 値動きの穏やかな銘柄と荒い銘柄に同じ最大リターン（例: 30%）を与えたとき、穏やかな銘柄だけが正規化の爆発と判定される。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- REQ-037 / REQ-038（schema 5）: コミット済み
- REQ-039〜041（B1 過去検証）: 実装済み・**未コミット**

### 保留中（今回のスコープ外）
- **昇格に「連続する複数週で同じ方向」を条件に加える**（レポート A5）。週をまたいで昇格の履歴を保存する必要がある。今は learning の結果が90日で消える Actions artifact にしか残らないため、保存先の設計を含めて別要件にする。
- **Beta-Binomial（経験ベイズ）による縮小推定**。REQ-043 の備考のとおり。
- **ボラティリティ正規化の爆発を昇格判定に採用するか**。REQ-044 の診断値を見てから判断する。
- **【要調査・優先度高】split only 基準の二重調整の可能性が高い。** yfinance 1.7.0 の `_fix_bad_stock_splits`（`scrapers/history.py` L2953〜）のコメントによると、Yahoo は過去の価格データに分割調整を**適用して**返し、yfinance はその調整の欠落や二重適用を修復している。つまり `history(auto_adjust=False)` の OHLC はすでに分割調整済みである可能性が高い。その場合、`split_adjust_ohlc`（`src/data/live_quote.py`）が分割比でもう一度割るのは二重調整になる。
  - 影響範囲: (1) forward の trailing stop の評価のうち、分割をまたぐ trade。(2) **本番の Position Exit Monitor**。分割前に買った保有銘柄の「分割後の価格基準での買値」と高値（HWM）が実際より低く計算され、stop 価格が低くなって、売却アラートが出るべきときに出ない可能性がある。
  - 現時点の根拠はライブラリのソースだけで、実データでの確認はしていない。
  - REQ-042 では挙動を変えない（現行と値を一致させる）。次の作業として、**verify-before-fix で実データ（分割のあった銘柄）を使って確かめる**ことを推奨する。B1 の J-Quants キャッシュ（`AdjFactor` と `AdjC`）が、照合用の独立した参照データとして使える。
