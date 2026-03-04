/**
 * 共通ユーティリティ: JSONデータ読み込み、日付フォーマット、最終更新表示
 *
 * Phase 16: 市場別ページ対応
 * - MARKET: URL パスから "jp" / "us" を自動判定
 * - DATA_BASE: サブディレクトリ (us/ jp/) では "../data/" を使用
 */

var MARKET = (function () {
  var path = window.location.pathname;
  if (path.indexOf("/jp/") !== -1) return "jp";
  return "us";
})();

var DATA_BASE = (function () {
  var path = window.location.pathname;
  if (path.indexOf("/us/") !== -1 || path.indexOf("/jp/") !== -1) return "../data/";
  return "data/";
})();

/** 市場に応じた predictions ファイル名を返す。 */
function predictionsFile() {
  if (MARKET === "jp") return "predictions_jp.json";
  var path = window.location.pathname;
  if (path.indexOf("/us/") !== -1) return "predictions_us.json";
  return "predictions.json";  // ルート: 後方互換
}

async function loadJSON(filename) {
  const resp = await fetch(DATA_BASE + filename);
  if (!resp.ok) throw new Error("Failed to load " + filename + ": " + resp.status);
  return resp.json();
}

function formatDate(dateStr) {
  if (!dateStr) return "-";
  return dateStr;
}

/**
 * 価格を通貨フォーマットで返す。
 * @param {number} price
 * @param {string} [currency] "USD"（デフォルト）または "JPY"。
 *   省略時は MARKET から自動判定。
 */
function formatPrice(price, currency) {
  if (price == null) return "-";
  currency = currency || (MARKET === "jp" ? "JPY" : "USD");
  if (currency === "JPY") {
    return "\u00a5" + Math.round(Number(price)).toLocaleString("ja-JP");
  }
  return "$" + Number(price).toFixed(2);
}

function formatPct(pct) {
  if (pct == null) return "-";
  return (pct >= 0 ? "+" : "") + Number(pct).toFixed(1) + "%";
}

function showLastUpdated(accuracy) {
  var el = document.getElementById("last-updated");
  if (!el) return;
  if (accuracy && accuracy.updated_at) {
    var d = new Date(accuracy.updated_at);
    el.textContent = "\u6700\u7d42\u66f4\u65b0: " + d.toLocaleString("ja-JP");
    checkStaleness(d);
  }
}

function checkStaleness(updatedDate) {
  var now = new Date();
  var diffDays = (now - updatedDate) / (1000 * 60 * 60 * 24);
  if (diffDays > 10) {
    var alert = document.getElementById("stale-alert");
    if (alert) {
      alert.style.display = "block";
      alert.textContent =
        "\u26a0 \u30c7\u30fc\u30bf\u304c " +
        Math.floor(diffDays) +
        " \u65e5\u9593\u66f4\u65b0\u3055\u308c\u3066\u3044\u307e\u305b\u3093\u3002";
    }
  }
}

function hitBadge(hit) {
  if (hit === "\u7684\u4e2d") return '<span class="badge badge-hit">当たり</span>';
  if (hit === "\u5916\u308c") return '<span class="badge badge-miss">はずれ</span>';
  return '<span class="badge badge-pending">結果待ち</span>';
}

function getLatestWeekDate(predictions) {
  if (!predictions || predictions.length === 0) return null;
  var dates = predictions.map(function (p) {
    return p.date;
  });
  return dates.sort().reverse()[0];
}

function isTestTicker(ticker) {
  return ticker === "E2E_TEST";
}

function filterPredictions(predictions) {
  return predictions.filter(function (p) {
    return !isTestTicker(p.ticker);
  });
}

function renderHeaderAccuracy(accuracy) {
  var valueEl = document.getElementById("header-accuracy-value");
  var detailEl = document.getElementById("header-accuracy-detail");
  if (!valueEl || !accuracy || !accuracy.cumulative) return;

  valueEl.textContent = accuracy.cumulative.hit_rate_pct.toFixed(1) + "%";
  if (detailEl) {
    detailEl.textContent =
      accuracy.cumulative.hits +
      "/" +
      accuracy.cumulative.total +
      " 当たり";
  }
}

// --- ヘルプモーダル ---

var HELP_CONTENT =
  '<h3>このダッシュボードの使い方</h3>' +
  '<p>AIが「来週上がりそうな株」を毎週予測します。このサイトでは、その予測結果と過去の成績を確認できます。</p>' +
  '<h3>各ページの説明</h3>' +
  '<ul>' +
  '<li><strong>サマリー</strong>: 今週の予測一覧。「買い候補」「様子見」がひと目でわかります</li>' +
  '<li><strong>成績</strong>: 過去の予測がどれくらい当たったかの記録</li>' +
  '<li><strong>銘柄詳細</strong>: 個別の株の予測履歴・株価チャート</li>' +
  '</ul>' +
  '<h3>カードの見方</h3>' +
  '<ul>' +
  '<li><strong>現在価格 → 予測価格</strong>: 今の株価と、来週AIが予測した株価</li>' +
  '<li><strong>予測上昇率</strong>: 来週どれくらい上がる（下がる）と予測しているか</li>' +
  '<li><strong>当たり / はずれ</strong>: 過去の予測が実際に当たったかどうか</li>' +
  '<li><strong>値動き ○%</strong>: この株がどれくらい激しく動くか（大きいほどリスクが高い）</li>' +
  '<li><strong>最大下落 ○%</strong>: 過去1年で最も大きく下がった幅</li>' +
  '</ul>' +
  '<h3>注意マークについて</h3>' +
  '<ul>' +
  '<li><span class="badge sanity-warn">⚠ 注意</span> 予測の変動が大きく、精度が低い可能性があります</li>' +
  '<li><span class="badge sanity-clipped">⚠ 不安定</span> 予測が極端すぎるため、表示値を調整しています</li>' +
  '</ul>' +
  '<p class="help-note">※ このシステムは投資判断の参考情報です。予測は将来の利益を保証しません。</p>';

function initHelpModal() {
  var overlay = document.createElement("div");
  overlay.id = "help-modal";
  overlay.className = "modal-overlay";
  overlay.style.display = "none";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "help-modal-title");

  overlay.innerHTML =
    '<div class="modal-content">' +
    '<div class="modal-header">' +
    '<h2 id="help-modal-title">使い方ガイド</h2>' +
    '<button class="modal-close" id="help-close" aria-label="\u9589\u3058\u308b">&#x2715;</button>' +
    '</div>' +
    '<div class="modal-body">' + HELP_CONTENT + '</div>' +
    '<div class="modal-footer">' +
    '<button class="modal-footer-btn" id="help-close-footer">\u9589\u3058\u308b</button>' +
    '</div>' +
    '</div>';

  document.body.appendChild(overlay);

  function openModal() {
    overlay.style.display = "flex";
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    overlay.style.display = "none";
    document.body.style.overflow = "";
  }

  var helpBtn = document.getElementById("help-btn");
  if (helpBtn) {
    helpBtn.addEventListener("click", openModal);
  }

  overlay.querySelector("#help-close").addEventListener("click", closeModal);
  overlay.querySelector("#help-close-footer").addEventListener("click", closeModal);

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeModal();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay.style.display !== "none") closeModal();
  });
}

document.addEventListener("DOMContentLoaded", initHelpModal);
