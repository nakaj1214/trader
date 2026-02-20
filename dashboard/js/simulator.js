/**
 * simulator.html: 料金シミュレータ（予測に従って投資した場合の損益計算）
 */

(function () {
  var predictions = [];
  var simChart = null;

  async function init() {
    try {
      var data = await Promise.all([
        loadJSON("predictions.json"),
        loadJSON("accuracy.json"),
      ]);
      var predictionsJson = data[0];
      predictions = predictionsJson.predictions || predictionsJson;
      var accuracy = data[1];

      showLastUpdated(accuracy);
      renderHeaderAccuracy(accuracy);

      document.getElementById("sim-run").addEventListener("click", runSimulation);
      // 初回自動実行
      runSimulation();
    } catch (e) {
      document.getElementById("simulator-content").innerHTML =
        '<div class="empty-state">\u30c7\u30fc\u30bf\u3092\u8aad\u307f\u8fbc\u3081\u307e\u305b\u3093\u3067\u3057\u305f\u3002</div>';
      console.error(e);
    }
  }

  function validateAmount(amount) {
    return typeof amount === "number" && isFinite(amount) && amount > 0;
  }

  function runSimulation() {
    var amountInput = document.getElementById("sim-amount");
    var errorEl = document.getElementById("sim-error");
    var amount = Number(amountInput.value);

    if (!validateAmount(amount)) {
      errorEl.style.display = "block";
      document.getElementById("sim-results-area").style.display = "none";
      document.getElementById("sim-empty").style.display = "none";
      return;
    }
    errorEl.style.display = "none";

    // 対象レコード: actual_price != null, current_price > 0, not E2E_TEST
    var valid = predictions.filter(function (p) {
      return p.actual_price != null && p.current_price > 0 && !isTestTicker(p.ticker);
    });

    // 週ごとにグルーピング
    var weekMap = {};
    valid.forEach(function (p) {
      if (!weekMap[p.date]) weekMap[p.date] = [];
      weekMap[p.date].push(p);
    });

    var weeks = Object.keys(weekMap).sort();

    // 全週除外チェック
    if (weeks.length === 0) {
      document.getElementById("sim-results-area").style.display = "none";
      document.getElementById("sim-empty").style.display = "block";
      return;
    }

    document.getElementById("sim-results-area").style.display = "block";
    document.getElementById("sim-empty").style.display = "none";

    // 各週の損益を計算
    var weeklyResults = [];
    var tickerPnl = {};
    var totalPnl = 0;

    weeks.forEach(function (date) {
      var items = weekMap[date];
      var perStock = amount / items.length;
      var weekPnl = 0;

      items.forEach(function (p) {
        var pnl = perStock * (p.actual_price - p.current_price) / p.current_price;
        weekPnl += pnl;

        if (!tickerPnl[p.ticker]) {
          tickerPnl[p.ticker] = { pnl: 0, count: 0 };
        }
        tickerPnl[p.ticker].pnl += pnl;
        tickerPnl[p.ticker].count++;
      });

      totalPnl += weekPnl;
      weeklyResults.push({ date: date, pnl: weekPnl, cumPnl: totalPnl });
    });

    var totalReturnPct = (totalPnl / amount) * 100;

    renderSummary(amount, totalPnl, totalReturnPct, weeks.length);
    renderChart(weeklyResults);
    renderTable(tickerPnl, amount);
  }

  function renderSummary(amount, totalPnl, returnPct, weekCount) {
    var container = document.getElementById("sim-summary");
    var pnlClass = totalPnl >= 0 ? "positive" : "negative";
    var pnlSign = totalPnl >= 0 ? "+" : "";
    var retSign = returnPct >= 0 ? "+" : "";

    container.innerHTML =
      '<div class="sim-result-card">' +
      '  <div class="sim-result-value">' + formatPrice(amount) + '</div>' +
      '  <div class="sim-result-label">\u6295\u8cc7\u91d1\u984d</div>' +
      '</div>' +
      '<div class="sim-result-card">' +
      '  <div class="sim-result-value ' + pnlClass + '">' +
      pnlSign + formatPrice(totalPnl) +
      '</div>' +
      '  <div class="sim-result-label">\u7d2f\u8a08\u640d\u76ca</div>' +
      '</div>' +
      '<div class="sim-result-card">' +
      '  <div class="sim-result-value ' + pnlClass + '">' +
      retSign + returnPct.toFixed(1) + '%' +
      '</div>' +
      '  <div class="sim-result-label">\u7d2f\u8a08\u640d\u76ca\u7387</div>' +
      '</div>' +
      '<div class="sim-result-card">' +
      '  <div class="sim-result-value">' + weekCount + '\u9031</div>' +
      '  <div class="sim-result-label">\u5bfe\u8c61\u671f\u9593</div>' +
      '</div>';
  }

  function renderChart(weeklyResults) {
    var canvas = document.getElementById("sim-chart");
    if (!canvas) return;

    var labels = weeklyResults.map(function (w) { return w.date; });
    var weeklyPnl = weeklyResults.map(function (w) { return Math.round(w.pnl * 100) / 100; });
    var cumPnl = weeklyResults.map(function (w) { return Math.round(w.cumPnl * 100) / 100; });

    if (simChart) simChart.destroy();

    simChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            type: "bar",
            label: "\u9031\u6b21\u640d\u76ca ($)",
            data: weeklyPnl,
            backgroundColor: weeklyPnl.map(function (v) {
              return v >= 0 ? "rgba(22, 163, 74, 0.6)" : "rgba(220, 38, 38, 0.6)";
            }),
            borderColor: weeklyPnl.map(function (v) {
              return v >= 0 ? "rgba(22, 163, 74, 1)" : "rgba(220, 38, 38, 1)";
            }),
            borderWidth: 1,
            order: 2,
          },
          {
            type: "line",
            label: "\u7d2f\u8a08\u640d\u76ca ($)",
            data: cumPnl,
            borderColor: "rgba(37, 99, 235, 1)",
            backgroundColor: "transparent",
            borderWidth: 2,
            pointRadius: 3,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          y: {
            ticks: {
              callback: function (v) { return "$" + v.toLocaleString(); },
            },
          },
        },
      },
    });
  }

  function renderTable(tickerPnl, amount) {
    var container = document.getElementById("sim-table");
    if (!container) return;

    var rows = Object.keys(tickerPnl)
      .map(function (ticker) {
        var t = tickerPnl[ticker];
        return {
          ticker: ticker,
          pnl: t.pnl,
          pct: (t.pnl / amount) * 100,
          count: t.count,
        };
      })
      .sort(function (a, b) { return b.pnl - a.pnl; });

    var html =
      '<div class="table-wrapper"><table>' +
      "<thead><tr>" +
      "<th>\u30c6\u30a3\u30c3\u30ab\u30fc</th>" +
      "<th>\u640d\u76ca ($)</th>" +
      "<th>\u640d\u76ca\u7387</th>" +
      "<th>\u56de\u6570</th>" +
      "</tr></thead><tbody>";

    rows.forEach(function (r) {
      var pnlClass = r.pnl >= 0 ? "positive" : "negative";
      var sign = r.pnl >= 0 ? "+" : "";
      html +=
        "<tr>" +
        '<td><a href="stock.html?ticker=' + encodeURIComponent(r.ticker) + '">' + r.ticker + "</a></td>" +
        '<td class="change ' + pnlClass + '">' + sign + "$" + Math.abs(r.pnl).toFixed(2) + "</td>" +
        '<td class="change ' + pnlClass + '">' + sign + r.pct.toFixed(1) + "%</td>" +
        "<td>" + r.count + "</td>" +
        "</tr>";
    });

    html += "</tbody></table></div>";
    container.innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
