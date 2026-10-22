// Small inline-SVG charts: no library, colors from CSS custom properties, a readout for touch and mouse.
// Each chart draws at its real pixel width (and redraws on resize), so axis text stays the same size everywhere.
import { escapeHtml, formatDate, formatNumber, formatPct } from "./format.js";

const FALLBACK_WIDTH = 600; // until the figure is laid out (a hidden tab has no width yet)
const MIN_WIDTH = 260;

function responsive(figure, draw) {
  let drawn = 0;
  const render = (width) => {
    const size = Math.max(MIN_WIDTH, Math.round(width));
    if (size === drawn) return;
    drawn = size;
    draw(size);
  };
  render(FALLBACK_WIDTH);
  new ResizeObserver(([entry]) => {
    if (entry.contentRect.width > 0) render(entry.contentRect.width);
  }).observe(figure);
}

function trackPointer(svg, width, count, firstX, span, onIndex) {
  const pick = (event) => {
    const rect = svg.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * width;
    const index = count === 1 ? 0 : Math.round(((x - firstX) / span) * (count - 1));
    onIndex(Math.min(count - 1, Math.max(0, index)));
  };
  svg.addEventListener("pointermove", pick);
  svg.addEventListener("pointerdown", pick);
  svg.addEventListener("pointerleave", () => onIndex(null));
}

function emptyFigure(text) {
  const figure = document.createElement("figure");
  figure.className = "chart";
  figure.innerHTML = `<p class="chart__caption">${escapeHtml(text)}</p>`;
  return figure;
}

/**
 * Close prices as a line with volume bars below.
 * series: [[date, close, volume], ...]; markers: Map(date -> "early" | "watch") drawn on the line.
 */
export function priceChart(series, { markers = new Map(), height = 210, volume = true, label = "株価の推移" } = {}) {
  if (!Array.isArray(series) || series.length < 2) return emptyFigure("株価のデータがありません。");
  const figure = document.createElement("figure");
  figure.className = "chart";
  const closes = series.map((row) => row[1]);
  let min = Math.min(...closes);
  let max = Math.max(...closes);
  if (min === max) [min, max] = [min * 0.99, max * 1.01];
  const first = series[0];
  const last = series[series.length - 1];
  const period = formatPct((last[1] / first[1] - 1) * 100);
  const summary = `${label}: ${formatDate(first[0])} ${formatNumber(first[1])}円から ${formatDate(last[0])} ${formatNumber(last[1])}円（${period}）`;
  const idle = `${formatDate(last[0])} 終値 ${formatNumber(last[1])}円 ・ 期間 ${period}`;

  const draw = (width) => {
    const pad = { top: 10, right: 52, bottom: volume ? 52 : 24, left: 4 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const x = (index) => pad.left + (index * plotWidth) / (series.length - 1);
    const y = (value) => pad.top + ((max - value) / (max - min)) * plotHeight;
    const base = pad.top + plotHeight;
    const line = series.map((row, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(row[1]).toFixed(1)}`).join("");
    const area = `${line}L${x(series.length - 1).toFixed(1)},${base}L${x(0).toFixed(1)},${base}Z`;

    const grid = [max, (max + min) / 2, min]
      .map((value) => {
        const top = y(value).toFixed(1);
        return `<line class="chart__grid" x1="${pad.left}" x2="${pad.left + plotWidth}" y1="${top}" y2="${top}"/>
          <text class="chart__axis" x="${width - pad.right + 6}" y="${top}" dominant-baseline="middle">${formatNumber(value)}</text>`;
      })
      .join("");

    let bars = "";
    if (volume) {
      const volumes = series.map((row) => (typeof row[2] === "number" ? row[2] : 0));
      const maxVolume = Math.max(...volumes, 1);
      const barTop = base + 6;
      const barHeight = 24;
      const barWidth = Math.max(1, (plotWidth / series.length) * 0.7);
      bars = volumes
        .map((value, index) => {
          const h = (value / maxVolume) * barHeight;
          return `<rect class="chart__volume" x="${(x(index) - barWidth / 2).toFixed(1)}" y="${(barTop + barHeight - h).toFixed(1)}" width="${barWidth.toFixed(1)}" height="${h.toFixed(1)}"/>`;
        })
        .join("");
    }

    const dots = series
      .map((row, index) => (markers.has(row[0]) ? [row, index] : null))
      .filter(Boolean)
      .map(([row, index]) => `<circle class="chart__marker chart__marker--${markers.get(row[0])}" cx="${x(index).toFixed(1)}" cy="${y(row[1]).toFixed(1)}" r="4"/>`)
      .join("");

    const dates = [0, Math.floor((series.length - 1) / 2), series.length - 1]
      .map((index, position) => {
        const anchor = ["start", "middle", "end"][position];
        return `<text class="chart__axis" x="${x(index).toFixed(1)}" y="${height - 4}" text-anchor="${anchor}">${formatDate(series[index][0])}</text>`;
      })
      .join("");

    figure.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${escapeHtml(summary)}">
        ${grid}<path class="chart__area" d="${area}"/><path class="chart__line" d="${line}"/>${bars}${dots}${dates}
        <line class="chart__cursor" y1="${pad.top}" y2="${base}" visibility="hidden"/>
        <circle class="chart__dot" r="4" visibility="hidden"/>
      </svg>
      <p class="chart__readout" aria-hidden="true"></p>`;

    const svg = figure.querySelector("svg");
    const cursor = figure.querySelector(".chart__cursor");
    const dot = figure.querySelector(".chart__dot");
    const readout = figure.querySelector(".chart__readout");
    readout.textContent = idle;
    trackPointer(svg, width, series.length, pad.left, plotWidth, (index) => {
      const visible = index === null ? "hidden" : "visible";
      cursor.setAttribute("visibility", visible);
      dot.setAttribute("visibility", visible);
      if (index === null) {
        readout.textContent = idle;
        return;
      }
      const [date, close, vol] = series[index];
      cursor.setAttribute("x1", x(index));
      cursor.setAttribute("x2", x(index));
      dot.setAttribute("cx", x(index));
      dot.setAttribute("cy", y(close));
      const volumeText = typeof vol === "number" ? ` ・ 出来高 ${formatNumber(vol)}株` : "";
      readout.textContent = `${formatDate(date, { year: true })} 終値 ${formatNumber(close, close < 100 ? 1 : 0)}円${volumeText}`;
    });
  };
  responsive(figure, draw);
  return figure;
}

/** Stacked bars of how many names each class had per stored market day. */
export function countsChart(days, classes) {
  if (!days.length) return emptyFigure("記録がありません。");
  const figure = document.createElement("figure");
  figure.className = "chart";
  const height = 190;
  const totals = days.map((day) => classes.reduce((sum, item) => sum + (day.counts?.[item.key] ?? 0), 0));
  const top = Math.max(...totals, 1);
  const describe = (day) =>
    `${formatDate(day.date, { year: true })} ` + classes.map((item) => `${item.label} ${day.counts?.[item.key] ?? 0}`).join(" ・ ");

  const draw = (width) => {
    const pad = { top: 10, right: 34, bottom: 24, left: 4 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const slot = plotWidth / days.length;
    const barWidth = Math.max(2, slot * 0.7);
    const base = pad.top + plotHeight;
    const bars = days
      .map((day, index) => {
        let stacked = 0;
        return classes
          .map((item) => {
            const count = day.counts?.[item.key] ?? 0;
            if (!count) return "";
            const h = (count / top) * plotHeight;
            stacked += h;
            const left = pad.left + index * slot + (slot - barWidth) / 2;
            return `<rect class="chart__bar--${item.modifier}" x="${left.toFixed(1)}" y="${(base - stacked).toFixed(1)}" width="${barWidth.toFixed(1)}" height="${h.toFixed(1)}"/>`;
          })
          .join("");
      })
      .join("");
    const axis = `
      <line class="chart__grid" x1="${pad.left}" x2="${pad.left + plotWidth}" y1="${pad.top}" y2="${pad.top}"/>
      <text class="chart__axis" x="${width - pad.right + 6}" y="${pad.top}" dominant-baseline="middle">${top}</text>
      <text class="chart__axis" x="${width - pad.right + 6}" y="${base}" dominant-baseline="middle">0</text>
      <text class="chart__axis" x="${pad.left}" y="${height - 4}">${formatDate(days[0].date)}</text>
      <text class="chart__axis" x="${pad.left + plotWidth}" y="${height - 4}" text-anchor="end">${formatDate(days[days.length - 1].date)}</text>`;
    figure.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${escapeHtml(`日ごとの候補数（${days.length}営業日）`)}">
        ${axis}${bars}<line class="chart__cursor" y1="${pad.top}" y2="${base}" visibility="hidden"/>
      </svg>
      <p class="chart__readout" aria-hidden="true"></p>`;
    const svg = figure.querySelector("svg");
    const cursor = figure.querySelector(".chart__cursor");
    const readout = figure.querySelector(".chart__readout");
    readout.textContent = describe(days[days.length - 1]);
    const center = (index) => pad.left + index * slot + slot / 2;
    // Bars are centered in their slots, so the pointer maps onto slot centers.
    trackPointer(svg, width, days.length, center(0), center(days.length - 1) - center(0) || 1, (index) => {
      cursor.setAttribute("visibility", index === null ? "hidden" : "visible");
      if (index === null) {
        readout.textContent = describe(days[days.length - 1]);
        return;
      }
      cursor.setAttribute("x1", center(index));
      cursor.setAttribute("x2", center(index));
      readout.textContent = describe(days[index]);
    });
  };
  responsive(figure, draw);
  return figure;
}
