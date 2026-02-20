/**
 * accuracy.html: 的中率推移チャート + 銘柄別ランキング + 予測誤差分析
 */

(function () {
  async function init() {
    try {
      var data = await Promise.all([
        loadJSON("accuracy.json"),
        loadJSON("predictions.json"),
        loadJSON("comparison.json").catch(function () { return null; }),
      ]);
      var accuracy = data[0];
      var predictionsJson = data[1];
      var predictions = predictionsJson.predictions || predictionsJson;
      var comparison = data[2];

      showLastUpdated(accuracy);
      renderHeaderAccuracy(accuracy);
      renderCumulativeStat(accuracy);
      renderWeeklyChart(accuracy);
      renderErrorAnalysis(accuracy);
      renderCalibration(accuracy);
      renderBacktestHygiene(comparison);
      renderComparison(comparison);
      renderTickerRanking(filterPredictions(predictions));
    } catch (e) {
      document.getElementById("accuracy-content").innerHTML =
        '<div class="empty-state">データを読み込めませんでした。</div>';
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
        " 的中";
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
            label: "週次的中率 (%)",
            data: hitRates,
            backgroundColor: "rgba(37, 99, 235, 0.6)",
            borderColor: "rgba(37, 99, 235, 1)",
            borderWidth: 1,
            order: 2,
          },
          {
            type: "line",
            label: "累計的中率 (%)",
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

  // --- Phase 4: 予測誤差分析 ---

  function renderErrorAnalysis(accuracy) {
    var section = document.getElementById("error-analysis-section");
    if (!section) return;
    if (!accuracy.error_analysis || accuracy.error_analysis.mae_pct == null) {
      section.style.display = "none";
      return;
    }

    section.style.display = "";
    var ea = accuracy.error_analysis;

    // MAE 表示
    var maeEl = document.getElementById("mae-value");
    if (maeEl) {
      maeEl.textContent = ea.mae_pct.toFixed(1) + "%";
    }

    // バーチャート
    renderErrorChart(ea.bins);

    // テーブル
    renderErrorTable(ea.bins);
  }

  function renderErrorChart(bins) {
    var canvas = document.getElementById("error-chart");
    if (!canvas || !bins || bins.length === 0) return;

    var labels = bins.map(function (b) { return b.range; });
    var predicted = bins.map(function (b) { return b.avg_predicted_pct; });
    var actual = bins.map(function (b) { return b.avg_actual_pct; });

    new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "予測平均 (%)",
            data: predicted,
            backgroundColor: "rgba(37, 99, 235, 0.6)",
            borderColor: "rgba(37, 99, 235, 1)",
            borderWidth: 1,
          },
          {
            label: "実績平均 (%)",
            data: actual,
            backgroundColor: "rgba(22, 163, 74, 0.6)",
            borderColor: "rgba(22, 163, 74, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          title: {
            display: true,
            text: "予測上昇率 vs 実際変動率",
          },
        },
        scales: {
          y: {
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

  function renderErrorTable(bins) {
    var container = document.getElementById("error-table");
    if (!container || !bins || bins.length === 0) {
      if (container) container.innerHTML = "";
      return;
    }

    var html =
      '<div class="table-wrapper"><table>' +
      "<thead><tr>" +
      "<th>予測帯</th>" +
      "<th>予測平均</th>" +
      "<th>実績平均</th>" +
      "<th>的中率</th>" +
      "<th>件数</th>" +
      "</tr></thead><tbody>";

    bins.forEach(function (b) {
      html +=
        "<tr>" +
        "<td>" + b.range + "</td>" +
        "<td>" + formatPct(b.avg_predicted_pct) + "</td>" +
        "<td>" + formatPct(b.avg_actual_pct) + "</td>" +
        "<td>" + b.hit_rate_pct.toFixed(1) + "%</td>" +
        "<td>" + b.count + "</td>" +
        "</tr>";
    });

    html += "</tbody></table></div>";
    container.innerHTML = html;
  }

  // --- Phase 7: 校正ダッシュボード ---

  function renderCalibration(accuracy) {
    var section = document.getElementById("calibration-section");
    if (!section) return;
    var cal = accuracy && accuracy.calibration;
    if (!cal || !cal.overall || cal.overall.n_calibrated < 30) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";
    renderCalibrationStats(cal.overall, cal.recent_n_weeks);
    renderCalibrationChart(cal.overall);
  }

  function renderCalibrationStats(overall, recent) {
    var container = document.getElementById("calibration-stats");
    if (!container) return;

    function statRow(label, value) {
      return (
        '<div class="calibration-stat-row">' +
        '<span class="calibration-stat-label">' + label + "</span>" +
        '<span class="calibration-stat-value">' + (value != null ? value : "-") + "</span>" +
        "</div>"
      );
    }

    function groupHtml(title, s) {
      if (!s) return "";
      return (
        '<div class="calibration-stat-group">' +
        "<h3>" + title + "</h3>" +
        statRow("Brier スコア", s.brier_score != null ? s.brier_score.toFixed(4) : null) +
        statRow("Log-Loss", s.log_loss != null ? s.log_loss.toFixed(4) : null) +
        statRow("ECE", s.ece != null ? s.ece.toFixed(4) : null) +
        statRow("件数", s.n_calibrated) +
        "</div>"
      );
    }

    var recentTitle = recent
      ? "直近 " + (recent.n_weeks || 12) + " 週"
      : "";

    container.innerHTML =
      groupHtml("全期間", overall) +
      groupHtml(recentTitle, recent);
  }

  function renderCalibrationChart(overall) {
    var canvas = document.getElementById("calibration-chart");
    if (!canvas || !overall || !overall.reliability_bins || overall.reliability_bins.length === 0) return;

    var bins = overall.reliability_bins;
    var labels = bins.map(function (b) { return b.p_bin; });
    var empiricals = bins.map(function (b) { return b.empirical; });
    var meanPreds = bins.map(function (b) { return b.mean_pred; });

    new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            type: "bar",
            label: "実測率（実際の上昇割合）",
            data: empiricals,
            backgroundColor: "rgba(37, 99, 235, 0.6)",
            borderColor: "rgba(37, 99, 235, 1)",
            borderWidth: 1,
            order: 2,
          },
          {
            type: "line",
            label: "予測確率（平均）",
            data: meanPreds,
            borderColor: "rgba(220, 38, 38, 1)",
            backgroundColor: "transparent",
            borderWidth: 2,
            pointRadius: 5,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          title: {
            display: true,
            text: "信頼性ダイアグラム（予測確率 vs 実測率）",
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ": " + (ctx.parsed.y * 100).toFixed(1) + "%";
              },
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 1.0,
            ticks: {
              callback: function (v) { return (v * 100).toFixed(0) + "%"; },
            },
          },
        },
      },
    });
  }

  // --- Phase 9: バックテスト品質開示 ---

  function renderBacktestHygiene(comparison) {
    var section = document.getElementById("backtest-hygiene-section");
    if (!section) return;
    var hygiene = comparison && comparison.backtest_hygiene;
    if (!hygiene) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";

    var statusLabel = {
      insufficient_trials: "試行数不足",
      computed: "算出済み",
      partial: "一部算出済み",
    };

    function fmt(v) {
      return v != null ? v : "-";
    }

    var html =
      '<div class="hygiene-panel">' +
      '<div class="hygiene-status hygiene-status-' + (hygiene.hygiene_status || "") + '">' +
      "ステータス: " + (statusLabel[hygiene.hygiene_status] || hygiene.hygiene_status) +
      "</div>" +
      '<div class="hygiene-rows">' +
      '<div class="hygiene-row"><span class="hygiene-label">検証したルール数</span><span class="hygiene-value">' + fmt(hygiene.num_rules_tested) + "</span></div>" +
      '<div class="hygiene-row"><span class="hygiene-label">チューニングパラメータ数</span><span class="hygiene-value">' + fmt(hygiene.num_parameters_tuned) + "</span></div>" +
      '<div class="hygiene-row"><span class="hygiene-label">OOS 開始日</span><span class="hygiene-value">' + fmt(hygiene.oos_start) + "</span></div>" +
      '<div class="hygiene-row"><span class="hygiene-label">評価週数</span><span class="hygiene-value">' + fmt(hygiene.data_coverage_weeks) + " 週</span></div>" +
      '<div class="hygiene-row"><span class="hygiene-label">Reality Check p 値</span><span class="hygiene-value">' + fmt(hygiene.reality_check_pvalue) + "</span></div>" +
      '<div class="hygiene-row"><span class="hygiene-label">PBO</span><span class="hygiene-value">' + fmt(hygiene.pbo) + "</span></div>" +
      '<div class="hygiene-row"><span class="hygiene-label">Deflated Sharpe</span><span class="hygiene-value">' + fmt(hygiene.deflated_sharpe) + "</span></div>" +
      "</div>" +
      '<p class="hygiene-notes">' + hygiene.transaction_cost_note + "<br>" + hygiene.survivorship_bias_note + "</p>" +
      (hygiene.hygiene_note ? '<p class="hygiene-note-detail">' + hygiene.hygiene_note + "</p>" : "") +
      "</div>";

    var panel = document.getElementById("backtest-hygiene-panel");
    if (panel) panel.innerHTML = html;
  }

  // --- Phase 6: 戦略比較 ---

  function renderComparison(comparison) {
    var section = document.getElementById("comparison-section");
    if (!section) return;
    if (!comparison || !comparison.strategies || Object.keys(comparison.strategies).length === 0) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";

    var strategies = comparison.strategies;
    renderComparisonChart(strategies);
    renderComparisonTable(strategies);
  }

  function renderComparisonChart(strategies) {
    var canvas = document.getElementById("comparison-chart");
    if (!canvas) return;

    var colors = {
      ai:             { border: "rgba(37, 99, 235, 1)",  bg: "rgba(37, 99, 235, 0.1)" },
      momentum_12_1:  { border: "rgba(22, 163, 74, 1)",  bg: "rgba(22, 163, 74, 0.1)" },
      benchmark_spy:  { border: "rgba(156, 163, 175, 1)", bg: "rgba(156, 163, 175, 0.1)" },
    };

    var datasets = [];
    Object.keys(strategies).forEach(function (key) {
      var s = strategies[key];
      if (!s.equity_curve || s.equity_curve.length === 0) return;
      var c = colors[key] || { border: "rgba(100,100,100,1)", bg: "rgba(100,100,100,0.1)" };
      datasets.push({
        label: s.label,
        data: s.equity_curve.map(function (pt) { return pt.equity; }),
        borderColor: c.border,
        backgroundColor: c.bg,
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        pointRadius: 0,
      });
    });

    if (datasets.length === 0) return;

    // ラベルは AI 戦略の日付を使用 (なければ最初の戦略)
    var labelSource = strategies.ai || strategies[Object.keys(strategies)[0]];
    var labels = labelSource.equity_curve.map(function (pt) { return pt.date; });

    new Chart(canvas, {
      type: "line",
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        plugins: {
          title: { display: true, text: "累積リターン比較 (初期値=1.0)" },
          legend: { position: "top" },
        },
        scales: {
          y: {
            ticks: {
              callback: function (v) { return v.toFixed(2); },
            },
          },
        },
      },
    });
  }

  function renderComparisonTable(strategies) {
    var container = document.getElementById("comparison-table");
    if (!container) return;

    var html =
      '<div class="table-wrapper"><table>' +
      "<thead><tr>" +
      "<th>戦略</th>" +
      "<th>年率 (CAGR)</th>" +
      "<th>最大DD</th>" +
      "<th>Sharpe</th>" +
      "</tr></thead><tbody>";

    Object.keys(strategies).forEach(function (key) {
      var s = strategies[key];
      var cagr = s.cagr != null ? (s.cagr >= 0 ? "+" : "") + (s.cagr * 100).toFixed(1) + "%" : "-";
      var dd   = s.max_drawdown != null ? (s.max_drawdown * 100).toFixed(1) + "%" : "-";
      var sh   = s.sharpe != null ? s.sharpe.toFixed(2) : "-";
      html +=
        "<tr>" +
        "<td>" + s.label + "</td>" +
        "<td>" + cagr + "</td>" +
        "<td>" + dd + "</td>" +
        "<td>" + sh + "</td>" +
        "</tr>";
    });

    html += "</tbody></table></div>";
    container.innerHTML = html;
  }

  // --- 銘柄別ランキング ---

  function renderTickerRanking(predictions) {
    var container = document.getElementById("ticker-ranking");
    if (!container) return;

    // 確定済みのみ集計
    var confirmed = predictions.filter(function (p) {
      return p.hit === "的中" || p.hit === "外れ";
    });

    if (confirmed.length === 0) {
      container.innerHTML =
        '<div class="empty-state">確定済みデータがありません。</div>';
      return;
    }

    // 銘柄別に集計
    var stats = {};
    confirmed.forEach(function (p) {
      if (!stats[p.ticker]) {
        stats[p.ticker] = { hits: 0, total: 0 };
      }
      stats[p.ticker].total++;
      if (p.hit === "的中") stats[p.ticker].hits++;
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
      "<th>ティッカー</th>" +
      "<th>的中率</th>" +
      "<th>的中/全体</th>" +
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
