// Labels and number formatting shared by the views. Everything inserted as HTML goes through escapeHtml.

export const CLASSES = {
  EARLY_CANDIDATE: {
    label: "有力候補",
    modifier: "early",
    description: "業績と値動きの点数が高く、直近20日で上昇し、売買量も増えている銘柄。いちばん注目する分類です。",
  },
  WATCH: {
    label: "様子見",
    modifier: "watch",
    description: "点数は基準を超えたが、有力候補の条件（高い点数・上昇・売買量の増加）のどれかが足りない銘柄。",
  },
  OVEREXTENDED: {
    label: "上がりすぎ",
    modifier: "over",
    description: "直近20日で+50%以上、または60日で+100%以上上がった銘柄。初動を過ぎたとみなし、候補から外しています。",
  },
  NONE: {
    label: "基準未満",
    modifier: "none",
    description: "詳しく調べた結果、点数が基準に届かなかった銘柄。",
  },
};

export const SCORE_LABELS = {
  revenue_growth: "売上の伸び",
  revenue_acceleration: "売上の伸びの加速",
  operating_profit_growth: "営業利益の伸び",
  margin_improvement: "利益率の改善",
  turned_profitable: "黒字転換",
  upward_revision: "業績予想の上方修正",
  major_order: "大型受注",
  capacity_expansion: "設備の増強",
  strategic_partnership: "提携",
  new_product_or_business: "新製品・新事業",
  return_20d: "20日の上昇",
  return_60d: "60日の上昇",
  volume_ratio: "売買量の増加",
  near_52w_high: "1年の高値圏",
  near_listing_high: "上場来の高値圏",
  extreme_runup_penalty: "急騰しすぎ（減点）",
  equity_financing_penalty: "増資の懸念（減点）",
  going_concern_penalty: "継続企業の疑義（減点）",
  negative_cfo_penalty: "営業キャッシュフローが赤字（減点）",
};

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);

export const isNumber = (value) => typeof value === "number" && Number.isFinite(value);

export function classInfo(classification) {
  return CLASSES[classification] ?? { label: String(classification ?? "-"), modifier: "none", description: "" };
}

export function formatNumber(value, digits = 0) {
  if (!isNumber(value)) return "-";
  return value.toLocaleString("ja-JP", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatPct(value, digits = 1) {
  if (!isNumber(value)) return "-";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
  return `${sign}${formatNumber(Math.abs(value), digits)}%`;
}

/** A signed percentage with ▲/▼ and the up/down color: the arrow carries the meaning, not the color alone. */
export function change(value, digits = 1) {
  if (!isNumber(value)) return '<span class="change">-</span>';
  const direction = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "";
  return `<span class="change change--${direction}">${arrow}${formatPct(value, digits)}</span>`;
}

export function formatYen(value) {
  if (!isNumber(value)) return "-";
  if (Math.abs(value) >= 1e8) return `${formatNumber(value / 1e8, 1)}億円`;
  if (Math.abs(value) >= 1e4) return `${formatNumber(value / 1e4, 0)}万円`;
  return `${formatNumber(value, value < 100 ? 1 : 0)}円`;
}

export function formatRatio(value) {
  return isNumber(value) ? `${formatNumber(value, 2)}倍` : "-";
}

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

export function formatDate(iso, { year = false } = {}) {
  if (typeof iso !== "string" || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return "-";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const weekday = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${year ? `${y}/` : ""}${m}/${d}(${weekday})`;
}

export function formatDateTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/** The stock code without the exchange suffix ("7203.T" -> "7203"). */
export const stockCode = (ticker) => String(ticker ?? "").replace(/\.T$/, "");

export function median(values) {
  const sorted = values.filter(isNumber).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

/** Whole calendar days from an ISO date to today in Japan. */
export function daysSince(iso) {
  const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
  return Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${iso}T00:00:00Z`)) / 86_400_000);
}
