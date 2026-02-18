/**
 * 共通ユーティリティ: JSONデータ読み込み、日付フォーマット、最終更新表示
 */

async function loadJSON(filename) {
  const resp = await fetch("data/" + filename);
  if (!resp.ok) throw new Error("Failed to load " + filename + ": " + resp.status);
  return resp.json();
}

function formatDate(dateStr) {
  if (!dateStr) return "-";
  return dateStr;
}

function formatPrice(price) {
  if (price == null) return "-";
  return "$" + Number(price).toFixed(2);
}

function formatPct(pct) {
  if (pct == null) return "-";
  return (pct >= 0 ? "+" : "") + Number(pct).toFixed(1) + "%";
}

function showLastUpdated(accuracy) {
  var el = document.getElementById("last-updated");
  if (!el) return;
  if (accuracy && accuracy.updated_at) {
    var d = new Date(accuracy.updated_at);
    el.textContent = "\u6700\u7d42\u66f4\u65b0: " + d.toLocaleString("ja-JP");
    checkStaleness(d);
  }
}

function checkStaleness(updatedDate) {
  var now = new Date();
  var diffDays = (now - updatedDate) / (1000 * 60 * 60 * 24);
  if (diffDays > 10) {
    var alert = document.getElementById("stale-alert");
    if (alert) {
      alert.style.display = "block";
      alert.textContent =
        "\u26a0 \u30c7\u30fc\u30bf\u304c " +
        Math.floor(diffDays) +
        " \u65e5\u9593\u66f4\u65b0\u3055\u308c\u3066\u3044\u307e\u305b\u3093\u3002";
    }
  }
}

function hitBadge(hit) {
  if (hit === "\u7684\u4e2d") return '<span class="badge badge-hit">\u7684\u4e2d</span>';
  if (hit === "\u5916\u308c") return '<span class="badge badge-miss">\u5916\u308c</span>';
  return '<span class="badge badge-pending">\u672a\u78ba\u5b9a</span>';
}

function getLatestWeekDate(predictions) {
  if (!predictions || predictions.length === 0) return null;
  var dates = predictions.map(function (p) {
    return p.date;
  });
  return dates.sort().reverse()[0];
}
