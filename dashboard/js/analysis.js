/**
 * Analysis page: Loads LLM-generated financial analysis data and renders
 * Markdown content as HTML using the marked library.
 *
 * Data structure:
 *   data/analysis/index.json -> { "AAPL": ["dcf", "comps"], ... }
 *   data/analysis/{ticker}.json -> [{ ticker, analysis_type, content, timestamp, model_used, token_count }]
 */

(function () {
  "use strict";

  var DATA_BASE = "data/analysis/";
  var INDEX_FILE = "index.json";

  var indexData = null;
  var currentAnalyses = null;

  var tickerSelect = null;
  var typeSelect = null;
  var contentSection = null;
  var analysisBody = null;
  var analysisMeta = null;
  var emptyState = null;
  var loadingState = null;
  var errorState = null;

  function initElements() {
    tickerSelect = document.getElementById("ticker-select");
    typeSelect = document.getElementById("type-select");
    contentSection = document.getElementById("analysis-content-section");
    analysisBody = document.getElementById("analysis-body");
    analysisMeta = document.getElementById("analysis-meta");
    emptyState = document.getElementById("analysis-empty");
    loadingState = document.getElementById("analysis-loading");
    errorState = document.getElementById("analysis-error");
  }

  function showLoading() {
    loadingState.style.display = "block";
    emptyState.style.display = "none";
    errorState.style.display = "none";
    contentSection.style.display = "none";
  }

  function showError(message) {
    errorState.textContent = message;
    errorState.style.display = "block";
    loadingState.style.display = "none";
    emptyState.style.display = "none";
    contentSection.style.display = "none";
  }

  function showEmpty() {
    emptyState.style.display = "block";
    loadingState.style.display = "none";
    errorState.style.display = "none";
    contentSection.style.display = "none";
  }

  function showContent() {
    contentSection.style.display = "block";
    loadingState.style.display = "none";
    emptyState.style.display = "none";
    errorState.style.display = "none";
  }

  function hideAll() {
    loadingState.style.display = "none";
    emptyState.style.display = "none";
    errorState.style.display = "none";
    contentSection.style.display = "none";
  }

  async function fetchJSON(url) {
    var resp = await fetch(url);
    if (!resp.ok) {
      throw new Error("Failed to load " + url + ": " + resp.status);
    }
    return resp.json();
  }

  function formatAnalysisType(type) {
    if (!type) return "";
    return type
      .replace(/_/g, " ")
      .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function formatTimestamp(timestamp) {
    if (!timestamp) return "";
    var d = new Date(timestamp);
    if (isNaN(d.getTime())) return timestamp;
    return d.toLocaleString("ja-JP", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function renderMarkdown(markdownText) {
    if (!markdownText) return "<p>No content available.</p>";
    if (typeof marked !== "undefined" && marked.parse) {
      return marked.parse(markdownText);
    }
    if (typeof marked !== "undefined" && typeof marked === "function") {
      return marked(markdownText);
    }
    var escaped = markdownText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return "<pre>" + escaped + "</pre>";
  }

  function populateTickerDropdown(tickers) {
    tickerSelect.innerHTML = '<option value="">-- Select Ticker --</option>';
    tickers.forEach(function (ticker) {
      var opt = document.createElement("option");
      opt.value = ticker;
      opt.textContent = ticker;
      tickerSelect.appendChild(opt);
    });
    tickerSelect.disabled = false;
  }

  function populateTypeDropdown(types) {
    typeSelect.innerHTML = '<option value="">-- Select Type --</option>';
    if (!types || types.length === 0) {
      typeSelect.disabled = true;
      return;
    }
    types.forEach(function (t) {
      var opt = document.createElement("option");
      opt.value = t;
      opt.textContent = formatAnalysisType(t);
      typeSelect.appendChild(opt);
    });
    typeSelect.disabled = false;

    if (types.length === 1) {
      typeSelect.value = types[0];
      onTypeChange();
    }
  }

  function renderAnalysis(analysis) {
    if (!analysis) {
      showEmpty();
      return;
    }

    var metaHtml = '<div class="analysis-meta-inner">';
    metaHtml += '<span class="analysis-meta-type">' + formatAnalysisType(analysis.analysis_type) + "</span>";
    if (analysis.timestamp) {
      metaHtml += '<span class="analysis-meta-date">Generated: ' + formatTimestamp(analysis.timestamp) + "</span>";
    }
    if (analysis.model_used) {
      metaHtml += '<span class="analysis-meta-model">Model: ' + analysis.model_used + "</span>";
    }
    if (analysis.token_count) {
      metaHtml += '<span class="analysis-meta-tokens">Tokens: ' + analysis.token_count.toLocaleString() + "</span>";
    }
    metaHtml += "</div>";
    analysisMeta.innerHTML = metaHtml;

    analysisBody.innerHTML = '<div class="markdown-content">' + renderMarkdown(analysis.content) + "</div>";
    showContent();
  }

  async function loadTickerData(ticker) {
    showLoading();
    try {
      currentAnalyses = await fetchJSON(DATA_BASE + ticker + ".json");

      var types = currentAnalyses.map(function (a) { return a.analysis_type; });
      populateTypeDropdown(types);
      hideAll();
    } catch (e) {
      console.error("Failed to load ticker data:", e);
      showError("Failed to load data for " + ticker + ".");
      currentAnalyses = null;
      typeSelect.innerHTML = '<option value="">Error</option>';
      typeSelect.disabled = true;
    }
  }

  function onTickerChange() {
    var ticker = tickerSelect.value;
    typeSelect.innerHTML = '<option value="">Select ticker first</option>';
    typeSelect.disabled = true;
    currentAnalyses = null;

    if (!ticker) {
      hideAll();
      return;
    }
    loadTickerData(ticker);
  }

  function onTypeChange() {
    var type = typeSelect.value;
    if (!type || !currentAnalyses) {
      hideAll();
      return;
    }

    var analysis = currentAnalyses.find(function (a) {
      return a.analysis_type === type;
    });

    if (!analysis) {
      showEmpty();
      return;
    }
    renderAnalysis(analysis);
  }

  async function init() {
    initElements();

    try {
      showLoading();
      indexData = await fetchJSON(DATA_BASE + INDEX_FILE);

      var tickers = Object.keys(indexData);
      if (tickers.length === 0) {
        showEmpty();
        tickerSelect.innerHTML = '<option value="">No analyses available</option>';
        return;
      }

      populateTickerDropdown(tickers);
      hideAll();

      tickerSelect.addEventListener("change", onTickerChange);
      typeSelect.addEventListener("change", onTypeChange);

      var params = new URLSearchParams(window.location.search);
      var urlTicker = params.get("ticker");
      var urlType = params.get("type");

      if (urlTicker) {
        tickerSelect.value = urlTicker;
        await loadTickerData(urlTicker);
        if (urlType && typeSelect.querySelector('option[value="' + urlType + '"]')) {
          typeSelect.value = urlType;
          onTypeChange();
        }
      }
    } catch (e) {
      console.error("Failed to load analysis index:", e);
      showError(
        "No analysis data available yet. Run the analysis pipeline first."
      );
      tickerSelect.innerHTML = '<option value="">No data</option>';
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
