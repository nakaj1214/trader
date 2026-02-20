/**
 * stock.html: 銘柄別詳細ページ（価格推移チャート + 履歴テーブル + リスク・エビデンス・選出理由）
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
        '<div class="empty-state">ティッカーが指定されていません。</div>';
      return;
    }

    if (isTestTicker(ticker)) {
      document.getElementById("stock-content").innerHTML =
        '<div class="empty-state">テストデータは表示できません。</div>';
      return;
    }

    var titleEl = document.getElementById("stock-ticker");
    if (titleEl) titleEl.textContent = ticker;

    document.title = ticker + " - AI Stock Predictions";

    try {
      var data = await Promise.all([
        loadJSON(predictionsFile()),
        loadJSON("stock_history.json"),
        loadJSON("accuracy.json"),
      ]);
      var predictionsJson = data[0];
      var predictions = predictionsJson.predictions || predictionsJson;
      var history = data[1];
      var accuracy = data[2];

      showLastUpdated(accuracy);
      renderHeaderAccuracy(accuracy);

      var tickerPredictions = predictions.filter(function (p) {
        return p.ticker === ticker;
      });
      var tickerHistory = history[ticker] || [];

      if (tickerPredictions.length === 0 && tickerHistory.length === 0) {
        document.getElementById("stock-content").innerHTML =
          '<div class="empty-state">「' +
          ticker +
          '」のデータが見つかりません。</div>';
        return;
      }

      // 最新レコード（risk/events/evidence/explanations/sanity_flags がある可能性）
      var latestWithRisk = null;
      for (var i = tickerPredictions.length - 1; i >= 0; i--) {
        if (tickerPredictions[i].risk) {
          latestWithRisk = tickerPredictions[i];
          break;
        }
      }

      // Phase 5: 最新予測の sanity フラグ警告表示
      var latestPred = tickerPredictions.length > 0
        ? tickerPredictions[tickerPredictions.length - 1]
        : null;
      renderSanityBanner(latestPred);

      renderRiskPanel(latestWithRisk);
      renderSizingPanel(latestWithRisk);
      renderEvidencePanel(latestWithRisk);
      renderExplanationsPanel(latestWithRisk);
      renderShortInterestPanel(latestWithRisk);
      renderInstitutionalPanel(latestWithRisk);
      renderPriceChart(tickerHistory, ticker);
      renderHistoryTable(tickerPredictions);
    } catch (e) {
      document.getElementById("stock-content").innerHTML =
        '<div class="empty-state">データを読み込めませんでした。</div>';
      console.error(e);
    }
  }

  // --- Phase 5: sanity バナー ---

  function renderSanityBanner(prediction) {
    var container = document.getElementById("sanity-banner");
    if (!container) return;
    if (!prediction || !prediction.sanity_flags) {
      container.style.display = "none";
      return;
    }
    var flags = prediction.sanity_flags;
    var isClipped = flags.indexOf("CLIPPED") >= 0;
    var isWarn = flags.indexOf("WARN_HIGH") >= 0;

    if (!isClipped && !isWarn) {
      container.style.display = "none";
      return;
    }

    var displayPct = prediction.predicted_change_pct_clipped != null
      ? prediction.predicted_change_pct_clipped
      : prediction.predicted_change_pct;

    if (isClipped) {
      container.className = "alert alert-warning sanity-banner";
      container.innerHTML =
        "<strong>⚠ 予測が不安定（外れ値の可能性）</strong><br>" +
        "モデルの予測上昇率が異常に大きいため表示値をクリップしています。" +
        "表示値: " + formatPct(displayPct) +
        "（元の予測値: " + formatPct(prediction.predicted_change_pct) + "）";
    } else {
      container.className = "alert alert-warning sanity-banner";
      container.innerHTML =
        "<strong>⚠ 予測上昇率が高水準</strong><br>" +
        "予測上昇率が警告しきい値を超えています（" + formatPct(prediction.predicted_change_pct) + "）。参考程度にご確認ください。";
    }
    container.style.display = "";
  }

  // --- Phase 1: リスクパネル + イベントバッジ ---

  function renderRiskPanel(prediction) {
    var container = document.getElementById("risk-panel");
    if (!container) return;
    if (!prediction || !prediction.risk) {
      container.style.display = "none";
      return;
    }

    var r = prediction.risk;
    var html =
      '<div class="risk-metrics">' +
      "<span>ボラ(20日): " + (r.vol_20d_ann * 100).toFixed(0) + "%年率</span>" +
      "<span>β: " + r.beta.toFixed(2) + "</span>" +
      "<span>最大DD: " + (r.max_drawdown_1y * 100).toFixed(0) + "%</span>" +
      "</div>";

    // イベントバッジ
    if (prediction.events && prediction.events.length > 0) {
      html += '<div class="event-badges">';
      prediction.events.forEach(function (ev) {
        var label =
          ev.type === "earnings"
            ? "決算まで" + ev.days_to + "日"
            : "配当落ちまで" + ev.days_to + "日";
        html += '<span class="event-badge">' + label + "</span>";
      });
      html += "</div>";
    }

    container.innerHTML = html;
    container.style.display = "";
  }

  // --- Phase 8: サイジングパネル ---

  function renderSizingPanel(prediction) {
    var container = document.getElementById("sizing-panel");
    if (!container) return;
    if (!prediction || !prediction.sizing) {
      container.style.display = "none";
      return;
    }
    var s = prediction.sizing;
    var maxW = s.max_position_weight != null
      ? (s.max_position_weight * 100).toFixed(0) + "%"
      : "-";
    var sl = s.stop_loss_pct != null
      ? (s.stop_loss_pct * 100).toFixed(1) + "%"
      : "-";

    var stopPriceHtml = "";
    if (s.stop_loss_pct != null && prediction.current_price) {
      var stopPrice = prediction.current_price * (1 + s.stop_loss_pct);
      stopPriceHtml =
        '<div class="stop-loss-highlight">' +
        '<div class="stop-label">損切り価格（この価格を下回ったら売り）</div>' +
        '<div class="stop-price">' + formatPrice(stopPrice) + '</div>' +
        '<div class="stop-desc">現在価格 ' + formatPrice(prediction.current_price) + ' から ' + sl + ' 下落した水準</div>' +
        '</div>';
    }

    var targetPriceHtml = "";
    if (prediction.predicted_price) {
      targetPriceHtml =
        '<div class="target-price-row">' +
        '<span class="target-price-label">目標価格（予測）</span>' +
        '<span class="target-price-value">' + formatPrice(prediction.predicted_price) + '</span>' +
        '</div>';
    }

    container.innerHTML =
      '<h3>ポジションサイジング・売買ガイド</h3>' +
      '<div class="sizing-panel">' +
      '<div class="sizing-row">' +
      '<span class="sizing-label">最大保有比率</span>' +
      '<span class="sizing-value">' + maxW + "</span>" +
      "</div>" +
      '<div class="sizing-row">' +
      '<span class="sizing-label">損切り水準</span>' +
      '<span class="sizing-value sizing-stop">' + sl + "</span>" +
      "</div>" +
      "</div>" +
      stopPriceHtml +
      targetPriceHtml +
      '<p class="sizing-note">※ ' + (s.stop_loss_rationale || "") + '</p>';
    container.style.display = "";
  }

  // --- Phase 2: エビデンスパネル ---

  function renderEvidencePanel(prediction) {
    var container = document.getElementById("evidence-panel");
    if (!container) return;
    if (!prediction || !prediction.evidence) {
      container.style.display = "none";
      return;
    }

    var ev = prediction.evidence;
    var factors = [
      { label: "モメンタム", key: "momentum_z" },
      { label: "バリュー", key: "value_z" },
      { label: "収益性", key: "quality_z" },
      { label: "低リスク", key: "low_risk_z" },
    ];

    var html = '<h3>エビデンス指標 <span class="panel-note">選出銘柄内の相対位置</span></h3>';

    factors.forEach(function (f) {
      var z = ev[f.key];
      if (z == null) {
        html +=
          '<div class="evidence-row">' +
          '<span class="evidence-label">' + f.label + "</span>" +
          '<span class="evidence-na">データなし</span>' +
          "</div>";
        return;
      }
      var pct = Math.min(Math.abs(z) / 3 * 100, 100);
      var cls = z >= 0 ? "evidence-support" : "evidence-oppose";
      var icon = z >= 0 ? "▲ 支持" : "▼ 反対";
      html +=
        '<div class="evidence-row">' +
        '<span class="evidence-label">' + f.label + "</span>" +
        '<div class="evidence-bar-track">' +
        '<div class="evidence-bar ' + cls + '" style="width:' + pct + '%"></div>' +
        "</div>" +
        '<span class="evidence-z">' + (z >= 0 ? "+" : "") + z.toFixed(2) + "</span>" +
        '<span class="' + cls + '">' + icon + "</span>" +
        "</div>";
    });

    if (ev.composite != null) {
      html += '<div class="evidence-composite">合成スコア: ' + ev.composite + " / 100</div>";
    }

    container.innerHTML = html;
    container.style.display = "";
  }

  // --- Phase 3: 選出理由パネル ---

  function renderExplanationsPanel(prediction) {
    var container = document.getElementById("explanations-panel");
    if (!container) return;
    if (!prediction || !prediction.explanations || !prediction.explanations.factors || prediction.explanations.factors.length === 0) {
      container.style.display = "none";
      return;
    }

    var expl = prediction.explanations;
    var html = "<h3>選出理由</h3>";
    html += '<p class="explanation-intro">この銘柄がトップ10に入った主因:</p>';

    var nums = ["①", "②", "③"];
    expl.factors.forEach(function (f, i) {
      html +=
        '<div class="explanation-item">' +
        "<span>" + (nums[i] || "") + " " + f.text + " (+" + f.impact.toFixed(3) + ")</span>" +
        "</div>";
    });

    html += '<p class="explanation-note">' + expl.note + "</p>";

    container.innerHTML = html;
    container.style.display = "";
  }

  // --- Phase 11: 空売り補助情報パネル ---

  function renderShortInterestPanel(prediction) {
    var container = document.getElementById("short-interest-panel");
    if (!container) return;
    if (!prediction || !prediction.short_interest) {
      container.style.display = "none";
      return;
    }
    var si = prediction.short_interest;
    var ratioStr = si.short_ratio != null ? si.short_ratio.toFixed(1) + " 日" : "-";
    var pctStr = si.short_pct_float != null ? (si.short_pct_float * 100).toFixed(1) + "%" : "-";
    var signalMap = { high_short: "高（空売り圧力大）", moderate_short: "中程度", neutral: "低〜中（通常）" };
    var signalLabel = signalMap[si.signal] || si.signal;

    container.innerHTML =
      "<h3>空売り状況 <span class=\"panel-note\">参考情報</span></h3>" +
      "<div class=\"info-rows\">" +
      "<div class=\"info-row\"><span class=\"info-label\">Short Ratio</span><span class=\"info-value\">" + ratioStr + "</span></div>" +
      "<div class=\"info-row\"><span class=\"info-label\">空売り比率</span><span class=\"info-value\">" + pctStr + "</span></div>" +
      "<div class=\"info-row\"><span class=\"info-label\">シグナル</span><span class=\"info-value\">" + signalLabel + "</span></div>" +
      "</div>" +
      "<p class=\"panel-note\">" + (si.data_note || "") + "</p>";
    container.style.display = "";
  }

  // --- Phase 12: 機関投資家保有パネル ---

  function renderInstitutionalPanel(prediction) {
    var container = document.getElementById("institutional-panel");
    if (!container) return;
    if (!prediction || !prediction.institutional) {
      container.style.display = "none";
      return;
    }
    var inst = prediction.institutional;
    var pctStr = inst.institutional_pct != null ? (inst.institutional_pct * 100).toFixed(1) + "%" : "-";
    var holders = inst.top5_holders && inst.top5_holders.length > 0
      ? inst.top5_holders.join("、")
      : "-";

    container.innerHTML =
      "<h3>主要機関保有者 <span class=\"panel-note\">参考情報</span></h3>" +
      "<div class=\"info-rows\">" +
      "<div class=\"info-row\"><span class=\"info-label\">機関保有率</span><span class=\"info-value\">" + pctStr + "</span></div>" +
      "<div class=\"info-row\"><span class=\"info-label\">上位5機関</span><span class=\"info-value\">" + holders + "</span></div>" +
      "</div>" +
      "<p class=\"panel-note\">" + (inst.data_note || "") + "</p>";
    container.style.display = "";
  }

  // --- 価格推移チャート ---

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
            label: "予測価格",
            data: predictedPrices,
            borderColor: "rgba(37, 99, 235, 1)",
            backgroundColor: "rgba(37, 99, 235, 0.1)",
            borderWidth: 2,
            fill: false,
            tension: 0.1,
          },
          {
            label: "実績価格",
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
            text: ticker + " 価格推移",
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

  // --- 予測履歴テーブル ---

  function renderHistoryTable(predictions) {
    var container = document.getElementById("history-table");
    if (!container || predictions.length === 0) {
      if (container)
        container.innerHTML =
          '<div class="empty-state">予測履歴がありません。</div>';
      return;
    }

    // 日付降順でソート
    var sorted = predictions.slice().sort(function (a, b) {
      return b.date.localeCompare(a.date);
    });

    var html =
      '<div class="table-wrapper"><table>' +
      "<thead><tr>" +
      "<th>日付</th>" +
      "<th>予測価格</th>" +
      "<th>実績価格</th>" +
      "<th>予測上昇率</th>" +
      "<th>結果</th>" +
      "</tr></thead><tbody>";

    sorted.forEach(function (p) {
      // Phase 5: sanity フラグ表示
      var flags = p.sanity_flags || [];
      var isClipped = flags.indexOf("CLIPPED") >= 0;
      var isWarn = flags.indexOf("WARN_HIGH") >= 0;
      var displayPct = p.predicted_change_pct_clipped != null
        ? p.predicted_change_pct_clipped
        : p.predicted_change_pct;
      var pctCell = formatPct(displayPct);
      if (isClipped) {
        pctCell += ' <span class="badge sanity-clipped">CLIPPED</span>';
      } else if (isWarn) {
        pctCell += ' <span class="badge sanity-warn">WARN</span>';
      }

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
        pctCell +
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
