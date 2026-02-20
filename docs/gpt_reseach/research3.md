# 静的サイト向け：AI株価アップサイド予測に「根拠ある投資判断支援」を追加するための調査報告書（書籍・実務資料含む）

## エグゼクティブサマリー

静的サイト（DBなし、JSONまたはスプレッドシート保存可）で「週次AIアップサイド予測」を投資判断支援として使える形に引き上げるには、モデル高度化より先に**①予測の品質（校正・再現性）の公開、②期待リターンだけでなくリスクと実行規律（サイズ・損切り・中立化）の提示、③バックテストの過剰最適化（データスヌーピング）対策**を“プロダクト要件”として組み込むのが最も費用対効果が高いです。citeturn2search2turn16search50turn17search13turn24search0turn24search7turn24search2  

学術論文に加え、実務家向け書籍は「何を測り、どう検証し、どう運用するか」を体系化しており、静的サイト運用に直接落とせます。特に、entity["people","Marcos López de Prado","quant researcher"]のentity["book","Machine Learning for Asset Managers","cambridge 2020 element"]は**理論なきバックテストの危険性**と**テストセット過学習**を明示し、研究プロセスを“実務手順”に落とす観点が強いです。citeturn25search1turn25search5  また、entity["people","Antti Ilmanen","portfolio manager author"]のentity["book","Expected Returns","wiley finance 2011"]は、**リスク・プレミアム、因子（value/momentum/volatility等）、期待リターン推定の考え方**を広くカバーし、サイトに載せる「根拠の文章テンプレ」を作りやすいです。citeturn25search4turn25search6  

最優先で追加すべき機能は次の3つです。  
- **校正ダッシュボード**（Brier / log-loss / reliability diagram）：確率予測が“確率として正しいか”を公開し、誤解（「0.8なら8割当たる」等）を検証可能にする。citeturn2search2turn16search50turn17search13turn16search51  
- **リスクカード**（ボラ・β・最大DD・想定損失・サイズ上限）：アップサイドと同じ画面で“耐えられるか”を提示し、過度なレバレッジ/集中を抑制する。低リスク/βの知見や、ボラに応じてリスク量を落とす考え方が根拠。citeturn2search0turn23search7turn4search49  
- **バックテスト公開の作法**（試行回数の透明化、Reality Check / PBO / Deflated Sharpeなどの過剰最適化対策）：週次で再計算し、JSONとして公開する。citeturn24search0turn24search7turn24search2turn24search9  

なお、公開サイトでのデータ利用は規約が最大のボトルネックになります。entity["organization","J-Quants API","jpx personal data api"]は**個人の私的利用に限定**され、第三者へのデータ配布やデータを用いたアプリ提供が禁止され得るため、公開サイトで生データを配布できません。citeturn7search0turn6search2  “派生スコアのみ公開”など、再配布に当たらない設計が必要です。

## 前提と現状

前提（未指定点の扱い）  
- 予測ホライズン：1週間＝5営業日（週次更新）  
- 対象ユニバース：日本株中心（必要に応じ米国株も）  
- 実装制約：静的サイトでAPIキーをブラウザへ露出できないため、**取得・推定・集計・バックテストはCI等でオフライン実行し、成果物JSONを配信**する  
- 保存先：Git（JSONコミット）または（管理用に）Google Sheets  

現状（GitHubコネクタで `nakaj1214/trader` を読取り）  
- 週次自動実行→予測生成→（Sheets連携）→`dashboard/data/*.json` を生成し静的サイトで表示、という配信パイプラインは既に存在。  
- テクニカル指標に加え、簡易な因子スコア（モメンタム/バリュー/クオリティ/低リスク）やリスク指標（ボラ・β・最大DD）を付与しており、判断支援の素地はある。  
- 一方、短期で極端なアップサイドが出る場合があり、**外れ値対策・誤差分布・校正**が未整備だと誤用リスクが高い。  
- GitHub Actionsのスケジュール実行は混雑で遅延し得るため、「更新時刻は成果物に焼き込む」「現地時間での週次更新の遅延を許容するUI表記」が望ましい。citeturn21search5  

## エビデンスベース

ここでは、サイト機能に直結する「測るべき指標」と「根拠」を、論文＋書籍＋公式/業界資料で整理します。

因子（モメンタム、バリュー、低リスク）  
- モメンタムは古典研究で体系化され、以後の検証でも議論が継続しています。citeturn0search0turn18search5  
- バリュー（簿価/時価など）やサイズ等の因子を含む枠組みは標準的参照点です。citeturn0search1turn19search2turn19search0  
- 低β/低リスクの“アノマリー”やBAB（Betting Against Beta）の議論は、リスク指標をサイト表示する根拠として使えます。citeturn2search0turn2search1  
- 業界の実装知として、最小分散/低ボラ指数は制約付き最適化（セクター制約、流動性、リバランス等）で構築されます。指数プロバイダの方法論は「中立化ランキング」「リスク制約」の設計根拠になります。citeturn19search20turn19search3  

決算・利益ニュース、アナリスト  
- 決算後ドリフト（PEAD）は、イベント注釈や「決算前後で誤差が増える」等の注意喚起の根拠になります。citeturn18search9  
- 価格モメンタムと利益ニュース（サプライズ）を結び付ける研究は、「価格だけでなく、利益情報・改定情報を特徴量として足す」方向性を支持します。citeturn18search0  
- 推奨は“グロスで良く見えても”回転・コストで相殺され得るため、サイトが推奨/改定を扱うなら**回転率とコスト仮定を同時提示**すべきです。citeturn18search12turn18search7  

マクロとリスク調整（“当てる”より“リスクを落とす”に寄せる）  
- 予測変数の頑健性には限界がある、という包括的検証があるため、マクロは「当てに行く」より「レジーム判定（サイズを落とす）」に使うほうが堅牢です。citeturn2search3turn4search2  
- ボラに応じてリスク量を調整する考え方（volatility-managed / vol targeting）は学術的に整理されており、静的サイトの「推奨サイズ上限」に落とし込みやすい。citeturn23search7turn23search0  
- ストップロスの“価値が出る条件”をフレーム化する研究があり、「損切りルールを出すなら、何を期待しているか（ボラ低下、期待値改善など）を明記」するのが望ましいです。citeturn23search1turn23search20  

確率予測の評価と校正（投資向けの必須技能）  
- 確率予測評価の中心はBrier score（2乗誤差）とlog-loss（対数スコア）で、proper scoring ruleの理論枠組みが整理されています。citeturn2search2turn16search50  
- Brier scoreは信頼性（reliability）等へ分解でき、ダッシュボードで「どこが悪いか（過信か、分解能不足か）」を説明できます。citeturn16search51  
- 実装の定番校正法としてPlatt scaling（シグモイド当てはめ）と温度スケーリングがあり、温度スケーリングの有効性は現代MLで再確認されています。citeturn17search41turn17search13  

書籍・実務資料が与える“プロダクト設計の作法”  
- entity["book","Machine Learning for Asset Managers","cambridge 2020 element"]は「理論のないルール探索は危険」「OOS（アウト・オブ・サンプル）を優先」「テストセット過学習を警戒」といった、サイトに必要な“研究工程の規律”を明示します。citeturn25search1turn25search5  
- entity["book","Expected Returns","wiley finance 2011"]は、株・債券・代替資産を含む期待リターン推定、因子（value/momentum/volatility等）やリスク要因（成長/インフレ/流動性等）を広く扱い、サイトの「根拠説明テンプレ」「リスク要因カード」を作る土台になります。citeturn25search4turn25search6  
- entity["book","Advances in Financial Machine Learning","wiley 2018 hardcover"]は、金融MLが失敗しやすい理由（偽陽性、過剰最適化）と、それを避ける研究手順・検証観点にフォーカスします。citeturn24search15turn25search10  

バックテスト過剰最適化（公開サイトなら特に重要）  
- 同じデータを繰り返し探索することで偶然を掴む“データスヌーピング”を定式化し、検定手順を示した研究があります。citeturn24search0  
- バックテスト過剰最適化確率（PBO/CSCV）や、選択バイアスを補正するDeflated Sharpe、過剰最適化の社会的リスクを警告する論考もあります。サイトにバックテストを載せるなら「試行回数」「探索の自由度」「OOS期間」を同時に載せるべきです。citeturn24search7turn24search2turn24search9  

## 推奨機能セット

静的サイト制約（DBなし・APIキー露出不可）に合わせ、「オフラインで計算→JSON配信」で成立する機能を、必要入出力・更新頻度まで落とし込みます。

### 機能比較表（複雑度・データ要件・効果）

| 機能 | Inputs（最低限） | Outputs（例） | 更新頻度 | 実装複雑度 | 期待効果 |
|---|---|---|---|---:|---:|
| 校正ダッシュボード | 予測確率＋実現勝敗 | Brier/log-loss/ECE、信頼度曲線bin | 週次 | 中 | 高 |
| 期待リターン×リスクカード | 予測リターン＋価格履歴 | 年率ボラ、β、最大DD、簡易Sharpe、区間幅 | 週次 | 低〜中 | 高 |
| 中立化ランキング | 予測リターン＋市場/セクター | α様残差、セクター内順位 | 週次 | 中 | 中〜高 |
| ストップ/サイズ規律 | ボラ/DD＋閾値設定 | 推奨サイズ上限、損切り水準・根拠 | 週次 | 中 | 中〜高 |
| イベント注釈 | 決算/配当/マクロ日程 | バッジ、注意喚起、誤差が増える局面 | 週次〜日次 | 低〜中 | 中 |
| バックテスト公開 | 長期価格＋ルール | 累積、Sharpe、DD、回転、分位別成績 | 週次 | 高 | 高 |
| SHAP風寄与度 | 特徴量＋係数/重み | 各特徴の寄与（%） | 週次 | 中 | 中 |
| アラート（静的＋外部通知） | 閾値/宛先 | alerts.json、メール/Slack通知 | 週次/日次 | 中 | 中 |

機能仕様の要点（文章テンプレまで含めた“使える形”）  
- 校正ダッシュボード：Brier/log-lossを“全期間”と“直近N週間”で併記し、信頼度曲線のbinには件数も載せる（少数binの誤解を防ぐ）。citeturn2search2turn16search50turn16search51turn17search13  
- リスクカード：低リスク因子やボラ調整の知見を根拠に、「ボラが高い銘柄はサイズを落とす」推奨を標準搭載。citeturn2search0turn23search7turn23search0  
- ストップ/サイズ規律：ストップは“当たる/当たらない”でなく、期待リターンとボラをどう変えるか（価値が出る条件）として説明する。citeturn23search1turn23search20  
- バックテスト公開：探索の自由度が増えるほど過剰最適化が増えるため、「試したルール数」「パラメータ探索幅」「OOS期間」をメタデータとして成果物JSONに残す。citeturn24search0turn24search7turn24search2turn24search9  

## データソースと取込設計

静的サイトでは、ブラウザからAPIキー付きAPIを直接叩けないため、**CI（例：GitHub Actions）で取得→JSON生成→コミット**が基本です。データソースは「配布可能性（再配布か否か）」と「更新頻度・レート制限」で選びます。

主要候補（ユーザ指定を優先）  
- entity["organization","EDINET","fsa disclosure system japan"]：提出書類の取得API仕様が公開されており、決算書類・有報のメタ情報/本文取得に使える（比率など派生指標生成向き）。citeturn5search48turn15search10  
- entity["organization","日本銀行","central bank japan"]：時系列統計データ検索サイトでAPI提供開始（JSON/CSV）。マクロレジーム特徴量（金融環境、物価、金利等）の公式ソースとして有用。citeturn12search0turn12search3  
- entity["organization","e-Stat","japan official statistics api"]：公的統計API。アプリ公開時はクレジット表示を要求。FAQで回数制限は現状なしとされるが、運用上は節度あるキャッシュが望ましい。citeturn12search1turn12search10turn12search7  
- entity["organization","FRED","st louis fed data service"]：マクロ系列の取得APIとパラメータが公式に整備され、JSON/CSVも指定可能。利用条件（Terms）も明確。citeturn15search0turn6search7turn15search1  
- entity["company","Alpha Vantage","market data api provider"]：無料枠の呼び出し制限が厳しめ（公式サポートにより日次上限などが明示される）。小規模ユニバース向き。citeturn7search3turn7search11  
- entity["company","Stooq","market data website"]：CSVでの取得例がある一方、APIがなく、ダウンロードにCAPTCHAが必要になる場合があり自動化に不向きな局面がある。規約原文取得が不安定なため、公開サービスでの利用は慎重に扱うべき。citeturn11search8turn11search19turn11search2  
- entity["organization","米国証券取引委員会","sec us regulator"]（EDGAR）：ユーザ指定の通り候補。アクセスにはレート制御（例：秒間10リクエスト）等の運用ガイドが示されている。citeturn5search3  
- entity["organization","J-Quants API","jpx personal data api"]：個人私的利用限定・再配布禁止の趣旨が明記されるため、**公開サイトで生データ配信は避け、派生スコアのみ公開**が基本。citeturn7search0turn6search2turn15search5  

取込の基本パターン（DBなし）  
- 原本データ：`data/raw/*.json`（非公開にしたい場合はリポジトリ外に保存し、派生成果物のみコミット）  
- 派生特徴量：`data/features/YYYY-MM-DD.json`  
- 予測：`data/predictions/YYYY-MM-DD.json`（公開）  
- 評価：`data/eval/metrics.json`（公開）  

Python疑似コード（FRED→JSON保存：APIキーはActions Secretで注入）  
```python
import os, json, requests, datetime

def fetch_fred_series(series_id: str, start="2000-01-01") -> dict:
    api_key = os.environ["FRED_API_KEY"]
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def main():
    out = {
        "asof_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "series": {
            "CPIAUCSL": fetch_fred_series("CPIAUCSL"),
            "FEDFUNDS": fetch_fred_series("FEDFUNDS"),
        },
    }
    with open("dashboard/data/macro_fred.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

if __name__ == "__main__":
    main()
```
（FREDのエンドポイント仕様、JSON/CSV指定、主要パラメータは公式に明示。）citeturn15search0turn15search1  

## 軽量モデリングとバックテスト

静的サイト要件では「推論はオフラインでOK」「ブラウザは可視化中心」と割り切れるため、モデルは複雑さより**検証可能性（評価・校正・再現性）**を優先します。

推奨モデル群（軽量で検証しやすい順）  
- ルールベース（因子スコア合成）：モメンタム/バリュー/低リスク等のz-score合成。説明が容易。citeturn0search0turn19search2turn2search0  
- ロジスティック回帰（確率の器）：`P(次週>0)` や `P(benchmark超過)` を、因子・イベント・マクロで推定し、校正（Platt/温度）で仕上げる。citeturn17search41turn17search13turn16search50  
- ヒューリスティック・アンサンブル：複数単純シグナルの平均/重み付き投票。探索幅を狭くし過剰最適化を抑える。citeturn24search0turn24search7  

評価指標（最低限そろえるべきセット）  
- 方向性：hit-rate（>0, >benchmark）、分位別成績  
- リターン：累積、年率、最大DD、回転率（売買頻度）  
- リスク調整：Sharpe等（コスト差し引き前後）citeturn4search49  
- 確率：Brier、log-loss、信頼度曲線（reliability diagram）citeturn2search2turn16search50turn16search51  

バックテストの過剰最適化対策（公開サイト必須）  
- Reality Check（データスヌーピング検定）で「たくさん試した結果の偶然」を抑える。citeturn24search0  
- PBO（CSCV）やDeflated Sharpeで“良さそうに見える”を補正する。citeturn24search7turn24search2  
- 書籍の観点では「理論を先に立てる」「OOSを優先」「テストセット過学習を警戒」が強調されます。citeturn25search1turn25search5  

校正（温度スケーリング）疑似コード  
```python
import numpy as np

def temperature_scale(logits: np.ndarray, y: np.ndarray, iters=200, lr=0.05):
    # logits: shape (n,)  / y: {0,1}
    T = 1.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-logits / T))
        # d/dT of log-loss (簡略化した近似; 実装はscipy.optimize推奨)
        grad = np.mean((p - y) * logits) / (T**2 + 1e-9)
        T = max(0.05, T - lr * grad)
    return T
```
（温度スケーリングはPlatt scalingの単純版として校正に有効とされる。）citeturn17search13turn17search41  

オフライン→静的配信のパイプライン（mermaid）  
```mermaid
flowchart LR
  A[公式/準公式データ取得<br/>EDINET・BOJ・e-Stat・FRED 等] --> B[ETL・特徴量生成<br/>価格/財務/マクロ/イベント]
  B --> C[予測生成<br/>期待リターン/確率]
  C --> D[校正<br/>温度スケーリング等]
  D --> E[バックテスト・評価<br/>成績/校正/コスト]
  E --> F[成果物JSON生成<br/>predictions/eval/alerts]
  F --> G[静的サイトで表示<br/>Chart.js等]
```

## 実装ロードマップと参考資料・サンプルスキーマ

有効コネクタ  
- 使用：github（`nakaj1214/trader` を読取り）

段階的ロードマップ（データ収集中の現状に合わせた優先順）  
- 低：成果物JSONに `as_of`（生成時刻）と `data_coverage`（対象期間・件数）を必須化（品質の最低限の透明化）  
- 中：校正ダッシュボード（Brier/log-loss/信頼度曲線）を追加し、週次で更新する（予測の“使って良い度”を可視化）citeturn2search2turn16search50turn16search51turn17search13  
- 中：リスクカード（ボラ・β・最大DD）＋サイズ上限（ボラターゲット）＋損切り案（閾値根拠）を追加citeturn23search7turn23search1turn4search49  
- 高：バックテストエンジンをオフライン実行し、過剰最適化対策（Reality Check / PBO / Deflated Sharpe）をメタデータ付きで公開citeturn24search0turn24search7turn24search2turn24search9  
- 中：データ源の権利整理（特にJ-Quants）と“派生スコアのみ公開”設計に統一citeturn7search0turn6search2  

法務・規約・表示（最低限の注意点）  
- 公開サイトが個別銘柄の売買時期を具体的に推奨し、報酬を得る等の態様では、entity["organization","金融庁","japan financial regulator"]の示す登録枠組みに抵触し得ます。一般情報の提供は登録不要の場合もある旨がガイドブックに示される一方、個別性が高い助言は登録が論点になります。citeturn20search1turn20search3turn20search9  
- 公的統計（e-Stat）はクレジット表示が求められます。citeturn12search1turn12search5  
- EDGAR等はレート制御など運用ルールが明示されます。citeturn5search3  

サンプルJSONスキーマ（最小構成の拡張例）  

`predictions.json`（週次予測の公開用）  
```json
{
  "as_of_jst": "2026-02-20T09:10:00+09:00",
  "horizon_trading_days": 5,
  "universe": "jp_equities",
  "benchmark": "TOPIX",
  "items": [
    {
      "ticker": "7203.T",
      "name": "トヨタ自動車",
      "current_price": 3000.0,
      "expected_return": 0.015,
      "pred_interval": { "p10": -0.020, "p50": 0.015, "p90": 0.055 },
      "prob_up": 0.62,
      "prob_outperform": 0.57,
      "risk": {
        "vol_ann": 0.22,
        "beta": 1.05,
        "max_drawdown_1y": 0.18
      },
      "signals": {
        "momentum_12_1_z": 0.8,
        "value_pb_z": -0.2,
        "quality_roe_z": 0.4,
        "low_risk_vol_z": 0.1,
        "composite_score_0_100": 66
      },
      "sizing": {
        "vol_target_ann": 0.10,
        "max_position_weight": 0.06,
        "stop_loss_rule": "cum_return <= -0.08 then reduce_exposure"
      },
      "explain": {
        "top_contributors": [
          { "feature": "momentum_12_1_z", "contribution": 0.42 },
          { "feature": "quality_roe_z", "contribution": 0.21 }
        ],
        "template_ja": "モメンタムと収益性が相対的に強く、リスク水準は市場並みです。"
      },
      "events": [
        { "type": "earnings", "date": "2026-02-26", "note": "決算予定（不確実性上昇）" }
      ]
    }
  ]
}
```

`eval.json`（成績・校正の公開用）  
```json
{
  "as_of_jst": "2026-02-20T09:10:00+09:00",
  "evaluation_window_weeks": 104,
  "performance": {
    "hit_rate": 0.54,
    "cagr": 0.08,
    "max_drawdown": 0.21,
    "turnover_annualized": 3.5
  },
  "risk_adjusted": {
    "sharpe": 0.62,
    "sharpe_cost_adjusted": 0.41
  },
  "calibration": {
    "brier": 0.205,
    "log_loss": 0.623,
    "ece": 0.031,
    "reliability_bins": [
      { "p_bin": "0.5-0.6", "n": 240, "empirical": 0.56 },
      { "p_bin": "0.6-0.7", "n": 180, "empirical": 0.61 }
    ]
  },
  "backtest_hygiene": {
    "num_rules_tested": 48,
    "num_parameters_tuned": 12,
    "oos_start": "2024-01-01",
    "notes": "探索規模は透明化。PBO等の導入を推奨。"
  }
}
```

参考として優先度の高い書籍・資料（一次/公式ページで確認できたもの）  
- entity["book","Machine Learning for Asset Managers","cambridge 2020 element"]（理論→検証→運用、テスト過学習、特徴重要度、ポートフォリオ構築など）citeturn25search1turn25search5  
- entity["book","Expected Returns","wiley finance 2011"]（期待リターン推定、因子・リスク要因、実務テンプレ）citeturn25search4turn25search6  
- entity["book","Advances in Financial Machine Learning","wiley 2018 hardcover"]（金融MLの失敗要因、偽陽性、研究工程の作法）citeturn24search15turn25search10