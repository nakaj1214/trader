/**
 * index.html: 週次サマリーカード描画 + 的中率チャート
 */

(function () {
  async function init() {
    try {
      var data = await Promise.all([
        loadJSON("predictions.json"),
        loadJSON("accuracy.json"),
      ]);
      var predictions = data[0];
      var accuracy = data[1];

      showLastUpdated(accuracy);
      renderPredictionCards(predictions);
      renderAccuracyChart(accuracy);
      renderCumulativeStat(accuracy);
    } catch (e) {
      document.getElementById("prediction-cards").innerHTML =
        '<div class="empty-state">\u30c7\u30fc\u30bf\u3092\u8aad\u307f\u8fbc\u3081\u307e\u305b\u3093\u3067\u3057\u305f\u3002</div>';
      console.error(e);
    }
  }

  function renderPredictionCards(predictions) {
    var container = document.getElementById("prediction-cards");
    var latestDate = getLatestWeekDate(predictions);

    if (!latestDate) {
      container.innerHTML =
        '<div class="empty-state">\u4e88\u6e2c\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002</div>';
      return;
    }

    var latest = predictions.filter(function (p) {
      return p.date === latestDate;
    });

    var dateLabel = document.getElementById("latest-date");
    if (dateLabel) dateLabel.textContent = latestDate;

    var html = "";
    latest.forEach(function (p) {
      var changeClass = p.predicted_change_pct >= 0 ? "positive" : "negative";
      html +=
        '<div class="card">' +
        '  <div class="ticker">' +
        '    <a href="stock.html?ticker=' +
        encodeURIComponent(p.ticker) +
        '">' +
        p.ticker +
        "</a>" +
        "  </div>" +
        '  <div class="price-row">' +
        '    <span class="price">' +
        formatPrice(p.current_price) +
        " \u2192 " +
        formatPrice(p.predicted_price) +
        "</span>" +
        '    <span class="change ' +
        changeClass +
        '">' +
        formatPct(p.predicted_change_pct) +
        "</span>" +
        "  </div>" +
        '  <div class="price-row">' +
        '    <span class="price">\u5b9f\u7e3e: ' +
        formatPrice(p.actual_price) +
        "</span>" +
        "    " +
        hitBadge(p.hit) +
        "  </div>" +
        "</div>";
    });
    container.innerHTML = html;
  }

  function renderAccuracyChart(accuracy) {
    var canvas = document.getElementById("accuracy-chart");
    if (!canvas || !accuracy.weekly || accuracy.weekly.length === 0) return;

    var labels = accuracy.weekly.map(function (w) {
      return w.date;
    });
    var hitRates = accuracy.weekly.map(function (w) {
      return w.hit_rate_pct;
    });

    new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "\u7684\u4e2d\u7387 (%)",
            data: hitRates,
            backgroundColor: "rgba(37, 99, 235, 0.6)",
            borderColor: "rgba(37, 99, 235, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
        },
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

  document.addEventListener("DOMContentLoaded", init);
})();
