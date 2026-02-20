/**
 * Phase 10: マクロ指標バナー描画
 * macro.json が存在する場合のみ #macro-banner を表示する。
 */

(function () {
  function renderMacroBanner(macro) {
    var banner = document.getElementById("macro-banner");
    if (!banner || !macro) return;

    var regime = macro.regime || {};
    var series = macro.series || {};
    var isRiskOff = regime.is_risk_off === true;

    // 系列サマリーテキストを組み立て
    var parts = [];
    if (series.FEDFUNDS && series.FEDFUNDS.latest_value != null) {
      parts.push("FF金利: " + series.FEDFUNDS.latest_value.toFixed(2) + series.FEDFUNDS.unit);
    }
    if (series.T10Y2Y && series.T10Y2Y.latest_value != null) {
      var spread = series.T10Y2Y.latest_value;
      parts.push("10Y-2Y: " + (spread >= 0 ? "+" : "") + spread.toFixed(2) + series.T10Y2Y.unit);
    }
    if (series.VIXCLS && series.VIXCLS.latest_value != null) {
      parts.push("VIX: " + series.VIXCLS.latest_value.toFixed(1));
    }

    var seriesText = parts.join(" | ");
    var note = regime.note || "";
    var asOf = macro.data_as_of_utc ? "データ基準: " + macro.data_as_of_utc.slice(0, 10) : "";

    banner.className = "macro-banner" + (isRiskOff ? " risk-off" : "");
    banner.style.display = "";
    banner.innerHTML =
      '<div class="macro-banner-inner">' +
      '<span class="macro-banner-label">' + (isRiskOff ? "リスクオフ" : "マクロ") + "</span>" +
      '<span class="macro-banner-series">' + seriesText + "</span>" +
      (note ? '<span class="macro-banner-note">' + note + "</span>" : "") +
      (asOf ? '<span class="macro-banner-asof">' + asOf + "</span>" : "") +
      "</div>";
  }

  // macro.json は存在しない場合もあるため、失敗時はバナーを非表示のまま
  loadJSON("macro.json")
    .then(function (macro) {
      renderMacroBanner(macro);
    })
    .catch(function () {
      // macro.json なし: バナーを表示しない
    });
})();
