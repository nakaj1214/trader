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
  if (hit === "\u7684\u4e2d") return '<span class="badge badge-hit">\u7684\u4e2d</span>';
  if (hit === "\u5916\u308c") return '<span class="badge badge-miss">\u5916\u308c</span>';
  return '<span class="badge badge-pending">\u672a\u78ba\u5b9a</span>';
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
      " \u7684\u4e2d";
  }
}

// --- ヘルプモーダル ---

var HELP_CONTENT =
  '<h3>\u3053\u306e\u30b7\u30b9\u30c6\u30e0\u3067\u3067\u304d\u308b\u3053\u3068</h3>' +
  '<ul>' +
  '<li>\u6bce\u9031\u306e\u4e0a\u6607\u4e88\u6e2c\u9298\u67c4\u3092 Slack \u3067\u53d7\u3051\u53d6\u308b</li>' +
  '<li>\u5fc5\u8981\u306b\u5fdc\u3058\u3066 LINE \u3067\u300cSlack\u78ba\u8a8d\u30ea\u30de\u30a4\u30f3\u30c9\u300d\u3092\u53d7\u3051\u53d6\u308b\uff08\u88dc\u52a9\u901a\u77e5\uff09</li>' +
  '<li>Web\u753b\u9762\u3067\u4e88\u6e2c\u5c65\u6b74\u30fb\u7684\u4e2d\u7387\u30fb\u30ea\u30b9\u30af\u6307\u6a19\u3092\u78ba\u8a8d\u3059\u308b</li>' +
  '<li>\u4eee\u60f3\u6295\u8cc7\u306e\u30b7\u30df\u30e5\u30ec\u30fc\u30b7\u30e7\u30f3\u3092\u884c\u3046</li>' +
  '</ul>' +
  '<h3>\u5404\u30da\u30fc\u30b8\u306e\u8aac\u660e</h3>' +
  '<ul>' +
  '<li><strong>\u30b5\u30de\u30ea\u30fc (index.html)</strong>: \u6700\u65b0\u9031\u306e\u4e88\u6e2c\u4e00\u89a7\u3068\u7d2f\u8a08\u7684\u4e2d\u7387</li>' +
  '<li><strong>\u7684\u4e2d\u7387 (accuracy.html)</strong>: \u9031\u6b21\u7684\u4e2d\u7387\u30fb\u8aa4\u5dee\u5206\u6790\u30fb\u6226\u7565\u6bd4\u8f03</li>' +
  '<li><strong>\u9298\u67c4\u8a73\u7d30 (stock.html)</strong>: \u9298\u67c4\u3054\u3068\u306e\u4e88\u6e2c\u5c65\u6b74\u30fb\u30ea\u30b9\u30af\u30fb\u30a8\u30d3\u30c7\u30f3\u30b9</li>' +
  '<li><strong>\u6295\u8cc7\u30b7\u30df\u30e5\u30ec\u30fc\u30bf (simulator.html)</strong>: \u4eee\u60f3\u6295\u8cc7\u306e\u640d\u76ca\u30b7\u30df\u30e5\u30ec\u30fc\u30b7\u30e7\u30f3</li>' +
  '</ul>' +
  '<h3>\u30ab\u30fc\u30c9\u306e\u8aad\u307f\u65b9</h3>' +
  '<ul>' +
  '<li>\u9298\u67c4\u540d\u30fb\u73fe\u5728\u4fa1\u683c \u2192 \u4e88\u6e2c\u4fa1\u683c\u30fb\u4e88\u6e2c\u4e0a\u6607\u7387</li>' +
  '<li>\u5b9f\u7e3e\u4fa1\u683c\u3068\u7684\u4e2d/\u5916\u308c\u30d0\u30c3\u30b8</li>' +
  '<li>\u30ea\u30b9\u30af\u884c: <code>\u30dc\u30e230% | \u03b21.20 | DD-15%</code>' +
  '<ul>' +
  '<li>\u30dc\u30e2 = \u5e74\u7387\u63db\u7b97\u30dc\u30e9\u30c6\u30a3\u30ea\u30c6\u30a3\uff08\u5024\u52d5\u304d\u306e\u5927\u304d\u3055\uff09</li>' +
  '<li>\u03b2 = S&amp;P 500 \u306b\u5bfe\u3059\u308b\u611f\u5fdc\u5ea6\uff081.0\u8d85\u3067\u5e02\u5834\u3088\u308a\u5927\u304d\u304f\u52d5\u304f\uff09</li>' +
  '<li>DD = \u904e\u53bb1\u5e74\u306e\u6700\u5927\u4e0b\u843d\u5e45</li>' +
  '</ul></li>' +
  '<li>\u30a4\u30d9\u30f3\u30c8\u30d0\u30c3\u30b8: \u6c7a\u7b97\u767a\u8868\u30fb\u914d\u5f53\u843d\u65e5\u304c\u8fd1\u3044\u5834\u5408\u306b\u8868\u793a</li>' +
  '</ul>' +
  '<h3>\u4e88\u6e2c\u30ac\u30fc\u30c9\u30ec\u30fc\u30eb\u30d0\u30c3\u30b8</h3>' +
  '<ul>' +
  '<li><span class="badge sanity-warn">WARN</span> \u4e88\u6e2c\u4e0a\u6607\u7387\u304c\u8b66\u544a\u3057\u304d\u3044\u5024\uff08\u00b120%\uff09\u3092\u8d85\u3048\u3066\u3044\u307e\u3059</li>' +
  '<li><span class="badge sanity-clipped">CLIPPED</span> \u4e0a\u9650\uff08\u00b130%\uff09\u3092\u8d85\u3048\u305f\u305f\u3081\u8868\u793a\u5024\u3092\u30af\u30ea\u30c3\u30d7\u3057\u3066\u3044\u307e\u3059\u3002\u5143\u5024\u306f\u300c\uff08\u5143\u5024: +XX%\uff09\u300d\u3067\u4ed8\u8a18\u3055\u308c\u307e\u3059</li>' +
  '</ul>' +
  '<h3>\u7684\u4e2d\u7387\u30da\u30fc\u30b8\u306e\u8aad\u307f\u65b9</h3>' +
  '<ul>' +
  '<li>\u7d2f\u8a08\u7684\u4e2d\u7387: \u5168\u671f\u9593\u306e\u7684\u4e2d\u6570 / \u5168\u4e88\u6e2c\u6570</li>' +
  '<li>\u4e88\u6e2c\u8aa4\u5dee\u5206\u6790: MAE\uff08\u5e73\u5747\u4e88\u6e2c\u8aa4\u5dee\uff09\u304c\u5c0f\u3055\u3044\u307b\u3069\u7cbe\u5ea6\u304c\u9ad8\u3044</li>' +
  '<li>\u6226\u7565\u6bd4\u8f03: AI\u4e88\u6e2c\u30fb12-1\u30e2\u30e1\u30f3\u30bf\u30e0\u30fb SPY\u306e\u7d2f\u7a4d\u30ea\u30bf\u30fc\u30f3\u3092\u6bd4\u8f03\uff08CAGR / \u6700\u5927DD / Sharpe\uff09</li>' +
  '</ul>' +
  '<h3>\u30b7\u30df\u30e5\u30ec\u30fc\u30bf\u306e\u4f7f\u3044\u65b9</h3>' +
  '<ul>' +
  '<li>\u6295\u8cc7\u91d1\u984d\uff08$\uff09\u3092\u5165\u529b\u3057\u3066\u300c\u30b7\u30df\u30e5\u30ec\u30fc\u30b7\u30e7\u30f3\u5b9f\u884c\u300d\u3092\u30af\u30ea\u30c3\u30af</li>' +
  '<li>\u6bce\u9031\u7b49\u91d1\u984d\u3067\u5168\u9298\u67c4\u306b\u6295\u8cc7\u3057\u305f\u5834\u5408\u306e\u4eee\u60f3\u640d\u76ca\u3092\u8868\u793a</li>' +
  '<li>\u624b\u6570\u6599\u30fb\u7a0e\u91d1\u30fb\u70ba\u66ff\u30b3\u30b9\u30c8\u306f\u542b\u307e\u308c\u307e\u305b\u3093</li>' +
  '</ul>' +
  '<p class="help-note">\u203b \u672c\u30b7\u30b9\u30c6\u30e0\u306f\u6295\u8cc7\u5224\u65ad\u306e\u88dc\u52a9\u3067\u3059\u3002\u4e88\u6e2c\u306f\u5c06\u6765\u306e\u5229\u76ca\u3092\u4fdd\u8a3c\u3057\u307e\u305b\u3093\u3002</p>';

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
    '<h2 id="help-modal-title">\u30d8\u30eb\u30d7</h2>' +
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
