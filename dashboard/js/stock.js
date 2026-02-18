/**
 * stock.html: 銘柄別詳細ページ（価格推移チャート + 履歴テーブル）
 */

(function () {
  function getTickerFromURL() {
    var params = new URLSearchParams(window.location.search);
    return params.get("ticker");
  }

  async function init() {
    var ticker = getTickerFromURL();
    if (!ticker) {
      document.getElementById("stock-content").innerHTML =
        '<div class="empty-state">\u30c6\u30a3\u30c3\u30ab\u30fc\u304c\u6307\u5b9a\u3055\u308c\u3066\u3044\u307e\u305b\u3093\u3002</div>';
      return;
    }

    var titleEl = document.getElementById("stock-ticker");
    if (titleEl) titleEl.textContent = ticker;

    document.title = ticker + " - AI Stock Predictions";

    try {
      var data = await Promise.all([
        loadJSON("predictions.json"),
        loadJSON("stock_history.json"),
        loadJSON("accuracy.json"),
      ]);
      var predictions = data[0];
      var history = data[1];
      var accuracy = data[2];

      showLastUpdated(accuracy);

      var tickerPredictions = predictions.filter(function (p) {
        return p.ticker === ticker;
      });
      var tickerHistory = history[ticker] || [];

      if (tickerPredictions.length === 0 && tickerHistory.length === 0) {
        document.getElementById("stock-content").innerHTML =
          '<div class="empty-state">\u300c' +
          ticker +
          '\u300d\u306e\u30c7\u30fc\u30bf\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002</div>';
        return;
      }

      renderPriceChart(tickerHistory, ticker);
      renderHistoryTable(tickerPredictions);
    } catch (e) {
      document.getElementById("stock-content").innerHTML =
        '<div class="empty-state">\u30c7\u30fc\u30bf\u3092\u8aad\u307f\u8fbc\u3081\u307e\u305b\u3093\u3067\u3057\u305f\u3002</div>';
      console.error(e);
    }
  }

  function renderPriceChart(history, ticker) {
    var canvas = document.getElementById("price-chart");
    if (!canvas || history.length === 0) return;

    var labels = history.map(function (h) {
      return h.date;
    });
    var predictedPrices = history.map(function (h) {
      return h.predicted_price;
    });
    var actualPrices = history.map(function (h) {
      return h.actual_price != null ? h.actual_price : null;
    });

    new Chart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "\u4e88\u6e2c\u4fa1\u683c",
            data: predictedPrices,
            borderColor: "rgba(37, 99, 235, 1)",
            backgroundColor: "rgba(37, 99, 235, 0.1)",
            borderWidth: 2,
            fill: false,
            tension: 0.1,
          },
          {
            label: "\u5b9f\u7e3e\u4fa1\u683c",
            data: actualPrices,
            borderColor: "rgba(22, 163, 74, 1)",
            backgroundColor: "rgba(22, 163, 74, 0.1)",
            borderWidth: 2,
            fill: false,
            tension: 0.1,
            spanGaps: false,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          title: {
            display: true,
            text: ticker + " \u4fa1\u683c\u63a8\u79fb",
          },
        },
        scales: {
          y: {
            ticks: {
              callback: function (v) {
                return "$" + v;
              },
            },
          },
        },
      },
    });
  }

  function renderHistoryTable(predictions) {
    var container = document.getElementById("history-table");
    if (!container || predictions.length === 0) {
      if (container)
        container.innerHTML =
          '<div class="empty-state">\u4e88\u6e2c\u5c65\u6b74\u304c\u3042\u308a\u307e\u305b\u3093\u3002</div>';
      return;
    }

    // 日付降順でソート
    var sorted = predictions.slice().sort(function (a, b) {
      return b.date.localeCompare(a.date);
    });

    var html =
      '<div class="table-wrapper"><table>' +
      "<thead><tr>" +
      "<th>\u65e5\u4ed8</th>" +
      "<th>\u4e88\u6e2c\u4fa1\u683c</th>" +
      "<th>\u5b9f\u7e3e\u4fa1\u683c</th>" +
      "<th>\u4e88\u6e2c\u4e0a\u6607\u7387</th>" +
      "<th>\u7d50\u679c</th>" +
      "</tr></thead><tbody>";

    sorted.forEach(function (p) {
      html +=
        "<tr>" +
        "<td>" +
        formatDate(p.date) +
        "</td>" +
        "<td>" +
        formatPrice(p.predicted_price) +
        "</td>" +
        "<td>" +
        formatPrice(p.actual_price) +
        "</td>" +
        "<td>" +
        formatPct(p.predicted_change_pct) +
        "</td>" +
        "<td>" +
        hitBadge(p.hit) +
        "</td>" +
        "</tr>";
    });

    html += "</tbody></table></div>";
    container.innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
