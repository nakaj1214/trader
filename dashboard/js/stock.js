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
        loadJSON("predictions.json"),
        loadJSON("stock_history.json"),
        loadJSON("accuracy.json"),
      ]);
      var predictions = data[0];
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
      renderEvidencePanel(latestWithRisk);
      renderExplanationsPanel(latestWithRisk);
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
