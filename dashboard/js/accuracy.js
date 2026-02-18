/**
 * accuracy.html: 的中率推移チャート + 銘柄別ランキング
 */

(function () {
  async function init() {
    try {
      var data = await Promise.all([
        loadJSON("accuracy.json"),
        loadJSON("predictions.json"),
      ]);
      var accuracy = data[0];
      var predictions = data[1];

      showLastUpdated(accuracy);
      renderCumulativeStat(accuracy);
      renderWeeklyChart(accuracy);
      renderTickerRanking(predictions);
    } catch (e) {
      document.getElementById("accuracy-content").innerHTML =
        '<div class="empty-state">\u30c7\u30fc\u30bf\u3092\u8aad\u307f\u8fbc\u3081\u307e\u305b\u3093\u3067\u3057\u305f\u3002</div>';
      console.error(e);
    }
  }

  function renderCumulativeStat(accuracy) {
    var valueEl = document.getElementById("cumulative-value");
    var detailEl = document.getElementById("cumulative-detail");
    if (!valueEl || !accuracy.cumulative) return;

    valueEl.textContent = accuracy.cumulative.hit_rate_pct.toFixed(1) + "%";
    if (detailEl) {
      detailEl.textContent =
        accuracy.cumulative.hits +
        "/" +
        accuracy.cumulative.total +
        " \u7684\u4e2d";
    }
  }

  function renderWeeklyChart(accuracy) {
    var canvas = document.getElementById("weekly-chart");
    if (!canvas || !accuracy.weekly || accuracy.weekly.length === 0) return;

    var labels = accuracy.weekly.map(function (w) {
      return w.date;
    });
    var hitRates = accuracy.weekly.map(function (w) {
      return w.hit_rate_pct;
    });

    // 累計的中率の推移を計算
    var cumHits = 0;
    var cumTotal = 0;
    var cumRates = accuracy.weekly.map(function (w) {
      cumHits += w.hits;
      cumTotal += w.total;
      return cumTotal > 0 ? Math.round((cumHits / cumTotal) * 1000) / 10 : 0;
    });

    new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            type: "bar",
            label: "\u9031\u6b21\u7684\u4e2d\u7387 (%)",
            data: hitRates,
            backgroundColor: "rgba(37, 99, 235, 0.6)",
            borderColor: "rgba(37, 99, 235, 1)",
            borderWidth: 1,
            order: 2,
          },
          {
            type: "line",
            label: "\u7d2f\u8a08\u7684\u4e2d\u7387 (%)",
            data: cumRates,
            borderColor: "rgba(220, 38, 38, 1)",
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
            beginAtZero: true,
            max: 100,
            ticks: {
              callback: function (v) {
                return v + "%";
              },
            },
          },
        },
      },
    });
  }

  function renderTickerRanking(predictions) {
    var container = document.getElementById("ticker-ranking");
    if (!container) return;

    // 確定済みのみ集計
    var confirmed = predictions.filter(function (p) {
      return p.hit === "\u7684\u4e2d" || p.hit === "\u5916\u308c";
    });

    if (confirmed.length === 0) {
      container.innerHTML =
        '<div class="empty-state">\u78ba\u5b9a\u6e08\u307f\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002</div>';
      return;
    }

    // 銘柄別に集計
    var stats = {};
    confirmed.forEach(function (p) {
      if (!stats[p.ticker]) {
        stats[p.ticker] = { hits: 0, total: 0 };
      }
      stats[p.ticker].total++;
      if (p.hit === "\u7684\u4e2d") stats[p.ticker].hits++;
    });

    // 的中率でソート
    var ranking = Object.keys(stats)
      .map(function (ticker) {
        var s = stats[ticker];
        return {
          ticker: ticker,
          hits: s.hits,
          total: s.total,
          rate: s.total > 0 ? Math.round((s.hits / s.total) * 1000) / 10 : 0,
        };
      })
      .sort(function (a, b) {
        return b.rate - a.rate || b.hits - a.hits;
      });

    var html =
      '<div class="table-wrapper"><table>' +
      "<thead><tr>" +
      "<th>#</th>" +
      "<th>\u30c6\u30a3\u30c3\u30ab\u30fc</th>" +
      "<th>\u7684\u4e2d\u7387</th>" +
      "<th>\u7684\u4e2d/\u5168\u4f53</th>" +
      "</tr></thead><tbody>";

    ranking.forEach(function (r, i) {
      html +=
        "<tr>" +
        "<td>" +
        (i + 1) +
        "</td>" +
        '<td><a href="stock.html?ticker=' +
        encodeURIComponent(r.ticker) +
        '">' +
        r.ticker +
        "</a></td>" +
        "<td>" +
        r.rate.toFixed(1) +
        "%</td>" +
        "<td>" +
        r.hits +
        "/" +
        r.total +
        "</td>" +
        "</tr>";
    });

    html += "</tbody></table></div>";
    container.innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
