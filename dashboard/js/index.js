/**
 * index.html: 週次サマリーカード描画（リスク情報 + イベントバッジ付き）
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
      renderHeaderAccuracy(accuracy);
      renderPredictionCards(predictions);
    } catch (e) {
      document.getElementById("prediction-cards").innerHTML =
        '<div class="empty-state">データを読み込めませんでした。</div>';
      console.error(e);
    }
  }

  function renderPredictionCards(predictions) {
    var container = document.getElementById("prediction-cards");
    var filtered = filterPredictions(predictions);
    var latestDate = getLatestWeekDate(filtered);

    if (!latestDate) {
      container.innerHTML =
        '<div class="empty-state">予測データがありません。</div>';
      return;
    }

    var latest = filtered.filter(function (p) {
      return p.date === latestDate;
    });

    // 重複排除: 同一ティッカーは「予測済み」を優先
    var tickerMap = {};
    latest.forEach(function (p) {
      var existing = tickerMap[p.ticker];
      if (!existing || p.status === "予測済み") {
        tickerMap[p.ticker] = p;
      }
    });

    // predicted_change_pct_clipped (あれば) 降順でソート
    var deduped = Object.keys(tickerMap)
      .map(function (k) { return tickerMap[k]; })
      .sort(function (a, b) {
        var av = a.predicted_change_pct_clipped != null ? a.predicted_change_pct_clipped : a.predicted_change_pct;
        var bv = b.predicted_change_pct_clipped != null ? b.predicted_change_pct_clipped : b.predicted_change_pct;
        return bv - av;
      });

    var dateLabel = document.getElementById("latest-date");
    if (dateLabel) dateLabel.textContent = latestDate;

    var html = "";
    deduped.forEach(function (p) {
      // Phase 5: clipped 値を優先表示
      var displayPct = p.predicted_change_pct_clipped != null
        ? p.predicted_change_pct_clipped
        : p.predicted_change_pct;
      var flags = p.sanity_flags || [];
      var isClipped = flags.indexOf("CLIPPED") >= 0;
      var isWarn = flags.indexOf("WARN_HIGH") >= 0;
      var changeClass = displayPct >= 0 ? "positive" : "negative";

      html +=
        '<div class="card">' +
        '  <div class="ticker">' +
        '    <a href="stock.html?ticker=' +
        encodeURIComponent(p.ticker) +
        '">' +
        p.ticker +
        "</a>" +
        (isClipped ? ' <span class="badge sanity-clipped">CLIPPED</span>' : "") +
        (isWarn ? ' <span class="badge sanity-warn">WARN</span>' : "") +
        "  </div>" +
        '  <div class="price-row">' +
        '    <span class="price">' +
        formatPrice(p.current_price) +
        " → " +
        formatPrice(p.predicted_price) +
        "</span>" +
        '    <span class="change ' +
        changeClass +
        '">' +
        formatPct(displayPct) +
        (isClipped ? ' <span class="sanity-original">(元値: ' + formatPct(p.predicted_change_pct) + ")</span>" : "") +
        "</span>" +
        "  </div>" +
        '  <div class="price-row">' +
        '    <span class="price">実績: ' +
        formatPrice(p.actual_price) +
        "</span>" +
        "    " +
        hitBadge(p.hit) +
        "  </div>";

      // Phase 1: リスク情報行
      if (p.risk) {
        html +=
          '  <div class="risk-row">' +
          "ボラ" + (p.risk.vol_20d_ann * 100).toFixed(0) + "%" +
          " | β" + p.risk.beta.toFixed(2) +
          " | DD" + (p.risk.max_drawdown_1y * 100).toFixed(0) + "%" +
          "  </div>";
      }

      // Phase 1: イベントバッジ
      if (p.events && p.events.length > 0) {
        html += '  <div class="event-badges">';
        p.events.forEach(function (ev) {
          var label =
            ev.type === "earnings"
              ? "決算" + ev.days_to + "日後"
              : "配当落ち" + ev.days_to + "日後";
          html += '<span class="event-badge">' + label + "</span>";
        });
        html += "  </div>";
      }

      html += "</div>";
    });
    container.innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
