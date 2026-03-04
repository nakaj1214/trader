/**
 * jp/index.html: 日本株週次サマリーカード描画
 * predictions_jp.json を参照し、価格を円建て（JPY）で表示する。
 * 単元株（1単元=100株）の最低投資額も表示する。
 */

(function () {
  async function init() {
    try {
      var data = await Promise.all([
        loadJSON("predictions_jp.json"),
        loadJSON("accuracy.json").catch(function () { return null; }),
      ]);
      var predictionsJson = data[0];
      var predictions = predictionsJson.predictions || predictionsJson;
      var accuracy = data[1];

      if (accuracy) {
        showLastUpdated(accuracy);
        renderHeaderAccuracy(accuracy);
      }
      renderPredictionCards(predictions);
    } catch (e) {
      document.getElementById("prediction-cards").innerHTML =
        '<div class="empty-state">日本株データを読み込めませんでした。まだデータ収集中の可能性があります。</div>';
      console.error(e);
    }
  }

  /** 単元株の最低投資額を計算して文字列で返す（1単元=100株）。*/
  function formatUnitInfo(price) {
    if (!price) return null;
    var minInvestment = Math.round(Number(price)) * 100;
    return "1単元(100株)の最低投資額: ¥" + minInvestment.toLocaleString("ja-JP");
  }

  function renderPredictionCards(predictions) {
    var container = document.getElementById("prediction-cards");
    var filtered = filterPredictions(predictions);
    var latestDate = getLatestWeekDate(filtered);

    if (!latestDate) {
      container.innerHTML =
        '<div class="empty-state">日本株の予測データがありません。データ収集をお待ちください。</div>';
      return;
    }

    var latest = filtered.filter(function (p) {
      return p.date === latestDate;
    });

    var tickerMap = {};
    latest.forEach(function (p) {
      var existing = tickerMap[p.ticker];
      if (!existing || p.status === "予測済み") {
        tickerMap[p.ticker] = p;
      }
    });

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
      var displayPct = p.predicted_change_pct_clipped != null
        ? p.predicted_change_pct_clipped
        : p.predicted_change_pct;
      var flags = p.sanity_flags || [];
      var isClipped = flags.indexOf("CLIPPED") >= 0;
      var isWarn = flags.indexOf("WARN_HIGH") >= 0;
      var changeClass = displayPct >= 0 ? "positive" : "negative";

      // 日本株は円建て表示
      var curPrice = formatPrice(p.current_price, "JPY");
      var predPrice = formatPrice(p.predicted_price, "JPY");
      var actPrice = formatPrice(p.actual_price, "JPY");

      // ティッカー表示: "7203.T" → "7203.T (トヨタ自動車など)" の形
      var displayTicker = p.ticker;

      html +=
        '<div class="card">' +
        '  <div class="ticker">' +
        '    <a href="stock.html?ticker=' + encodeURIComponent(p.ticker) + '">' + displayTicker + "</a>" +
        (isClipped ? ' <span class="badge sanity-clipped">⚠ 不安定</span>' : "") +
        (isWarn ? ' <span class="badge sanity-warn">⚠ 注意</span>' : "") +
        "  </div>" +
        '  <div class="price-row">' +
        '    <span class="price">' + curPrice + " → " + predPrice + "</span>" +
        '    <span class="change ' + changeClass + '">' + formatPct(displayPct) +
        (isClipped ? ' <span class="sanity-original">(元値: ' + formatPct(p.predicted_change_pct) + ")</span>" : "") +
        "</span>" +
        "  </div>" +
        '  <div class="price-row">' +
        '    <span class="price">実績: ' + actPrice + "</span>" +
        "    " + hitBadge(p.hit) +
        "  </div>";

      // 単元株情報（日本株固有）
      var unitInfo = formatUnitInfo(p.current_price);
      if (unitInfo) {
        html += '  <div class="risk-row" style="color:#555;">' + unitInfo + "</div>";
      }

      // Phase 17+: セクター・市場区分（JP 株のみ）
      if (p.jp_listed_info) {
        var li = p.jp_listed_info;
        var sectorText = [li.sector_17, li.market_section].filter(Boolean).join(" | ");
        if (sectorText) {
          html += '  <div class="risk-row" style="color:#555;font-size:0.85em;">' + sectorText + "</div>";
        }
      }

      // Phase 17+: 追加財務指標（EPS・配当・営業利益率）
      if (p.jp_fundamentals) {
        var f = p.jp_fundamentals;
        var fundParts = [];
        if (f.eps != null) fundParts.push("EPS ¥" + Number(f.eps).toLocaleString("ja-JP", {maximumFractionDigits: 0}));
        if (f.forecast_eps != null) fundParts.push("予想EPS ¥" + Number(f.forecast_eps).toLocaleString("ja-JP", {maximumFractionDigits: 0}));
        if (f.dividend_annual != null) fundParts.push("配当 ¥" + Number(f.dividend_annual).toLocaleString("ja-JP", {maximumFractionDigits: 0}) + "/年");
        if (f.payout_ratio != null) fundParts.push("配当性向 " + (f.payout_ratio * 100).toFixed(0) + "%");
        if (f.operating_margin != null) fundParts.push("営業利益率 " + (f.operating_margin * 100).toFixed(1) + "%");
        if (fundParts.length > 0) {
          html += '  <div class="risk-row" style="font-size:0.85em;color:#444;">' + fundParts.join(" | ") + "</div>";
        }
      }

      if (p.risk) {
        var riskText = "値動き " + (p.risk.vol_20d_ann * 100).toFixed(0) + "%" +
          " | 最大下落 " + (p.risk.max_drawdown_1y * 100).toFixed(0) + "%";
        html += '  <div class="risk-row">' + riskText + "  </div>";
      }

      if (p.events && p.events.length > 0) {
        html += '  <div class="event-badges">';
        p.events.forEach(function (ev) {
          var label = ev.type === "earnings"
            ? "決算発表 " + ev.days_to + "日後"
            : "配当日 " + ev.days_to + "日後";
          html += '<span class="event-badge">' + label + "</span>";
        });
        html += "  </div>";
      }

      if (p.status === "予測済み") {
        if (displayPct > 0) {
          html += '<div class="action-row action-buy">▲ 買い候補（来週 ' + formatPct(displayPct) + '）</div>';
        } else {
          html += '<div class="action-row action-neutral">– 様子見（来週 ' + formatPct(displayPct) + '）</div>';
        }
        if (p.sizing && p.sizing.stop_loss_pct != null && p.current_price) {
          var stopPrice = p.current_price * (1 + p.sizing.stop_loss_pct);
          html += '<div class="action-stop">売るべき価格: ' + formatPrice(stopPrice, "JPY") + ' を下回ったら売ることを検討</div>';
        }
      }

      html += "</div>";
    });
    container.innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
