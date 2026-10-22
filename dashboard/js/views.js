// Renders the four tabs from the decrypted bundle (see src/dashboard/bundle.py for its shape).
import { countsChart, priceChart } from "./charts.js";
import {
  SCORE_LABELS,
  change,
  classInfo,
  daysSince,
  escapeHtml,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPct,
  formatRatio,
  formatYen,
  isNumber,
  median,
  stockCode,
} from "./format.js";

const SIGNAL_CLASSES = ["EARLY_CANDIDATE", "WATCH"];
const COUNT_CLASSES = [
  { key: "EARLY_CANDIDATE", label: "有力候補", modifier: "early" },
  { key: "WATCH", label: "様子見", modifier: "watch" },
  { key: "OVEREXTENDED", label: "上がりすぎ", modifier: "over" },
];
const STALE_AFTER_DAYS = 4; // a weekend plus a holiday is normal; more means the daily scan stopped

// Joins a template literal; values are inserted as-is, so callers escape data with escapeHtml.
const html = (strings, ...values) => strings.reduce((out, part, index) => out + part + (values[index] ?? ""), "");

function fragment(markup) {
  const template = document.createElement("template");
  template.innerHTML = markup.trim();
  return template.content;
}

function badge(classification) {
  const info = classInfo(classification);
  return `<span class="badge badge--${info.modifier}">${escapeHtml(info.label)}</span>`;
}

function markersFor(history) {
  const markers = new Map();
  for (const row of history ?? []) {
    if (SIGNAL_CLASSES.includes(row.classification)) markers.set(row.date, classInfo(row.classification).modifier);
  }
  return markers;
}

function externalLinks(ticker) {
  const code = encodeURIComponent(stockCode(ticker));
  return html`
    <a href="https://finance.yahoo.co.jp/quote/${code}.T" target="_blank" rel="noopener noreferrer">Yahoo!ファイナンス</a>
    <a href="https://kabutan.jp/stock/?code=${code}" target="_blank" rel="noopener noreferrer">株探（決算・ニュース）</a>`;
}

export function renderNotices(bundle, root) {
  const notices = [];
  const age = daysSince(bundle.latest_price_date);
  if (age > STALE_AFTER_DAYS) {
    notices.push([
      "warn",
      "更新が止まっています",
      `最新のデータは${formatDate(bundle.latest_price_date)}（${age}日前）です。GitHub Actions の日次スキャンを確認してください。`,
    ]);
  }
  const delay = bundle.data_policy?.jquants_data_delay_weeks;
  if (isNumber(delay) && delay > 0) {
    notices.push([
      "info",
      "財務データは遅れています",
      `いまのデータプラン（${escapeHtml(bundle.data_policy.jquants_plan ?? "-")}）では、決算などの財務情報が約${delay}週間遅れて反映されます。直近の決算は株探などで確認してください。`,
    ]);
  }
  const diagnostics = bundle.diagnostics ?? {};
  if (diagnostics.skipped_snapshots || diagnostics.missing_prices) {
    notices.push([
      "info",
      "一部のデータが欠けています",
      `読めなかった日次記録 ${diagnostics.skipped_snapshots ?? 0}件、株価を取得できなかった銘柄 ${diagnostics.missing_prices ?? 0}件。`,
    ]);
  }
  root.replaceChildren(
    ...notices.map(([kind, title, text]) =>
      fragment(`<p class="notice${kind === "warn" ? " notice--warn" : ""}"><strong>${title}</strong><span>${text}</span></p>`),
    ),
  );
}

function metrics(candidate) {
  const features = candidate.features ?? {};
  const items = [
    ["株価", isNumber(candidate.current_price) ? `${formatNumber(candidate.current_price, candidate.current_price < 100 ? 1 : 0)}円` : "-"],
    ["20日の値動き", change(candidate.return_20d_pct)],
    ["60日の値動き", change(candidate.return_60d_pct)],
    ["売買量の増え方", formatRatio(candidate.volume_ratio_20d)],
    ["高値からの距離", isNumber(features.distance_from_period_high_pct) ? formatPct(features.distance_from_period_high_pct) : "-"],
    ["売上の伸び（前年比）", change(features.revenue_growth_yoy_pct)],
    ["営業利益の伸び", change(features.operating_profit_growth_yoy_pct)],
    ["1日の売買代金", formatYen(candidate.avg_turnover_20d_jpy)],
  ];
  return `<dl class="metrics">${items
    .map(([label, value]) => `<div class="metrics__item"><dt>${label}</dt><dd>${value}</dd></div>`)
    .join("")}</dl>`;
}

function scoreMeter(candidate, thresholds) {
  const score = isNumber(candidate.score) ? Math.max(0, Math.min(100, candidate.score)) : 0;
  const marks = [
    ["watch", thresholds?.watch_score, "様子見"],
    ["early", thresholds?.early_candidate_score, "有力候補"],
  ].filter(([, value]) => isNumber(value));
  return html`
    <div class="score" style="--score: ${score}">
      <div class="score__label"><span>点数</span><b>${formatNumber(candidate.score, 0)}</b><small>/ 100</small></div>
      <div class="score__track" aria-hidden="true">
        <span class="score__fill"></span>
        ${marks.map(([kind, value]) => `<span class="score__mark score__mark--${kind}" style="--at: ${value}"></span>`).join("")}
      </div>
      <p class="score__legend">縦線は基準（${marks.map(([, value, label]) => `${label} ${value}点`).join("・")}）</p>
    </div>`;
}

function timeline(candidate, days) {
  const byDate = new Map((candidate.history ?? []).map((row) => [row.date, row.classification]));
  const cells = days.map((day) => {
    const classification = byDate.get(day.date);
    const info = classification ? classInfo(classification) : null;
    const title = `${formatDate(day.date)} ${info ? info.label : "上位25社の外"}`;
    return `<li class="timeline__day${info ? ` timeline__day--${info.modifier}` : ""}" title="${escapeHtml(title)}"><span class="visually-hidden">${escapeHtml(title)}</span></li>`;
  });
  return `<ul class="timeline" aria-label="日ごとの判定">${cells.join("")}</ul>`;
}

function breakdown(candidate) {
  const rows = Object.entries(candidate.score_details ?? {}).filter(([, value]) => isNumber(value) && value !== 0);
  if (!rows.length) return '<p class="muted">点数の内訳はありません。</p>';
  return `<dl class="breakdown">${rows
    .map(([key, value]) => `<dt>${escapeHtml(SCORE_LABELS[key] ?? key)}</dt><dd>${value > 0 ? "+" : ""}${formatNumber(value, 0)}</dd>`)
    .join("")}</dl>`;
}

function candidateCard(candidate, bundle) {
  const info = classInfo(candidate.classification);
  const streak = candidate.streak >= 2 ? `<span class="badge badge--outline">${candidate.streak}日連続</span>` : "";
  const isNew = candidate.streak === 1 && (candidate.history ?? []).filter((row) => SIGNAL_CLASSES.includes(row.classification)).length === 1;
  const card = fragment(html`
    <article class="card card--${info.modifier}">
      <header class="card__header">
        <div>
          <h3 class="card__name">${escapeHtml(candidate.company_name ?? candidate.ticker)}</h3>
          <p class="card__meta">${escapeHtml(stockCode(candidate.ticker))} ・ ${escapeHtml(candidate.market ?? "-")} ・ ${escapeHtml(candidate.sector33_name ?? "-")}</p>
        </div>
        <div class="card__badges">${badge(candidate.classification)}${streak}${isNew ? '<span class="badge badge--outline">初登場</span>' : ""}</div>
      </header>
      <div class="card__body">
        <div class="card__chart"></div>
        <div class="card__info">
          ${scoreMeter(candidate, bundle.thresholds)}
          ${metrics(candidate)}
          ${candidate.reasons?.length ? `<ul class="chips" aria-label="選ばれた理由">${candidate.reasons.map((reason) => `<li class="chips__item">${escapeHtml(reason)}</li>`).join("")}</ul>` : ""}
        </div>
      </div>
      <details class="card__details">
        <summary>点数の内訳と、日ごとの判定</summary>
        <div class="card__details-body">
          <div><h4 class="muted">点数の内訳</h4>${breakdown(candidate)}</div>
          <div><h4 class="muted">直近${bundle.days.length}営業日の判定（色付き＝上位25社に入った日）</h4>${timeline(candidate, bundle.days)}</div>
        </div>
      </details>
      <footer class="card__links">${externalLinks(candidate.ticker)}</footer>
    </article>`);
  card.querySelector(".card__chart").append(
    priceChart(bundle.prices?.[candidate.ticker], { markers: markersFor(candidate.history), label: `${candidate.company_name}の株価` }),
  );
  return card;
}

function compactList(candidates) {
  if (!candidates.length) return '<p class="muted">該当なし</p>';
  return `<ul class="compact-list">${candidates
    .map(
      (candidate) => html`
      <li class="compact-list__item">
        <span><b>${escapeHtml(candidate.company_name ?? candidate.ticker)}</b> <span class="muted">${escapeHtml(stockCode(candidate.ticker))} ・ ${escapeHtml(candidate.market ?? "-")}</span></span>
        <span class="nowrap">点数 ${formatNumber(candidate.score, 0)} ・ 20日 ${change(candidate.return_20d_pct)} ・ 60日 ${change(candidate.return_60d_pct)}</span>
      </li>`,
    )
    .join("")}</ul>`;
}

export function renderToday(bundle, root) {
  const latest = bundle.latest;
  const sorted = [...latest.candidates].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const of = (classification) => sorted.filter((candidate) => candidate.classification === classification);
  const early = of("EARLY_CANDIDATE");
  const watch = of("WATCH");
  const continuing = sorted.filter((candidate) => candidate.streak >= 2).length;
  root.replaceChildren(
    fragment(html`
      <div class="section__header">
        <h2>今日の候補</h2>
        <p>${formatDate(latest.date, { year: true })}の終値で判定 ・ 作成 ${formatDateTime(bundle.generated_at)}</p>
      </div>
      <p class="notice"><strong>大事なこと</strong><span>ここに出るのは「調べる価値がありそうな銘柄」で、買いの推奨ではありません。買う前に、決算の予定日・増資のお知らせ・ニュースを株探などで確認してください。</span></p>
      <p class="funnel">
        <span>上場 <b>${formatNumber(latest.universe_count)}</b>社</span><span aria-hidden="true">→</span>
        <span>売買が多い <b>${formatNumber(latest.liquid_candidate_count)}</b>社</span><span aria-hidden="true">→</span>
        <span>値動きの上位 <b>${formatNumber(latest.candidates.length)}</b>社を詳しく評価</span><span aria-hidden="true">→</span>
        <span>有力候補 <b>${early.length}</b>社・様子見 <b>${watch.length}</b>社</span>
      </p>
      <div class="stats">
        <div class="stat"><span class="stat__label">有力候補</span><span class="stat__value">${early.length}</span><span class="stat__note">いちばん注目する分類</span></div>
        <div class="stat"><span class="stat__label">様子見</span><span class="stat__value">${watch.length}</span><span class="stat__note">条件の一部が足りない</span></div>
        <div class="stat"><span class="stat__label">連続して候補</span><span class="stat__value">${continuing}</span><span class="stat__note">2営業日以上続けて候補</span></div>
        <div class="stat"><span class="stat__label">上がりすぎ</span><span class="stat__value">${of("OVEREXTENDED").length}</span><span class="stat__note">初動を過ぎたので対象外</span></div>
      </div>
      <section class="section" aria-labelledby="early-title">
        <div class="section__header"><h3 id="early-title">有力候補</h3><p>${escapeHtml(classInfo("EARLY_CANDIDATE").description)}</p></div>
        <div class="grid" id="early-cards">${early.length ? "" : '<p class="empty">今日は有力候補がありません。</p>'}</div>
      </section>
      <section class="section" aria-labelledby="watch-title">
        <div class="section__header"><h3 id="watch-title">様子見</h3><p>${escapeHtml(classInfo("WATCH").description)}</p></div>
        <div class="grid" id="watch-cards">${watch.length ? "" : '<p class="empty">今日は様子見の銘柄がありません。</p>'}</div>
      </section>
      <details class="disclosure">
        <summary>上がりすぎ（${of("OVEREXTENDED").length}社）</summary>
        <p class="muted">${escapeHtml(classInfo("OVEREXTENDED").description)}</p>
        ${compactList(of("OVEREXTENDED"))}
      </details>
      <details class="disclosure">
        <summary>基準未満（${of("NONE").length}社）</summary>
        <p class="muted">${escapeHtml(classInfo("NONE").description)}</p>
        ${compactList(of("NONE"))}
      </details>`),
  );
  root.querySelector("#early-cards").append(...early.map((candidate) => candidateCard(candidate, bundle)));
  root.querySelector("#watch-cards").append(...watch.map((candidate) => candidateCard(candidate, bundle)));
}

const RESULT_FILTERS = [
  ["all", "すべて", () => true],
  ["early", "有力候補になった銘柄", (signal) => signal.ever_early],
  ["watch", "様子見だけの銘柄", (signal) => !signal.ever_early],
];

const RESULT_COLUMNS = [
  ["first_signal_date", "候補になった日", (signal) => signal.first_signal_date],
  ["name", "銘柄", (signal) => signal.company_name ?? signal.ticker],
  ["sessions", "経過", (signal) => signal.performance?.sessions],
  ["return_pct", "今の損益", (signal) => signal.performance?.return_pct],
  ["max_return_pct", "途中の最高", (signal) => signal.performance?.max_return_pct],
  ["min_return_pct", "途中の最低", (signal) => signal.performance?.min_return_pct],
  ["benchmark", "TOPIX", (signal) => signal.performance?.benchmark_return_pct],
  ["excess", "TOPIXとの差", (signal) => excess(signal)],
];

function excess(signal) {
  const performance = signal.performance ?? {};
  return isNumber(performance.return_pct) && isNumber(performance.benchmark_return_pct)
    ? performance.return_pct - performance.benchmark_return_pct
    : null;
}

function resultStats(signals) {
  const done = signals.filter((signal) => signal.performance?.status === "ok");
  const returns = done.map((signal) => signal.performance.return_pct);
  const excesses = done.map(excess).filter(isNumber);
  const share = (count, total) => (total ? `${Math.round((count / total) * 100)}%` : "-");
  return html`
    <div class="stats">
      <div class="stat"><span class="stat__label">集計できた銘柄</span><span class="stat__value">${done.length}</span><span class="stat__note">全${signals.length}銘柄（翌営業日待ちを除く）</span></div>
      <div class="stat"><span class="stat__label">いま上がっている割合</span><span class="stat__value">${share(returns.filter((value) => value > 0).length, returns.length)}</span><span class="stat__note">買ったと仮定した値段より上</span></div>
      <div class="stat"><span class="stat__label">損益の真ん中の値</span><span class="stat__value">${change(median(returns))}</span><span class="stat__note">中央値（極端な1銘柄に左右されにくい）</span></div>
      <div class="stat"><span class="stat__label">TOPIXより良かった割合</span><span class="stat__value">${share(excesses.filter((value) => value > 0).length, excesses.length)}</span><span class="stat__note">同じ期間の市場全体と比べて</span></div>
    </div>`;
}

function resultRows(signals) {
  if (!signals.length) return `<tr><td colspan="${RESULT_COLUMNS.length}" class="muted">該当なし</td></tr>`;
  return signals
    .map((signal) => {
      const performance = signal.performance ?? {};
      const waiting = performance.status !== "ok";
      const note = performance.status === "waiting" ? "翌営業日から集計" : "株価なし";
      return html`
        <tr>
          <td>${formatDate(signal.first_signal_date)}</td>
          <td><span class="table__name"><span>${escapeHtml(signal.company_name ?? signal.ticker)} ${badge(signal.ever_early ? "EARLY_CANDIDATE" : "WATCH")}</span><small>${escapeHtml(stockCode(signal.ticker))} ・ 候補${signal.signal_days}日</small></span></td>
          ${waiting
            ? `<td colspan="${RESULT_COLUMNS.length - 2}" class="muted">${note}</td>`
            : html`<td class="table__num">${performance.sessions}営業日</td>
              <td class="table__num">${change(performance.return_pct)}</td>
              <td class="table__num">${change(performance.max_return_pct)}</td>
              <td class="table__num">${change(performance.min_return_pct)}</td>
              <td class="table__num">${change(performance.benchmark_return_pct)}</td>
              <td class="table__num">${change(excess(signal))}</td>`}
        </tr>`;
    })
    .join("");
}

export function renderResults(bundle, root) {
  const state = { filter: "all", sort: "first_signal_date", direction: -1 };
  root.replaceChildren(
    fragment(html`
      <div class="section__header">
        <h2>過去の候補のその後</h2>
        <p>直近${bundle.days.length}営業日に候補になった銘柄</p>
      </div>
      <p class="notice"><strong>計算の前提</strong><span>初めて候補（有力候補か様子見）になった日の<b>翌営業日の始値で買った</b>と仮定し、最新の終値までの値動きを出しています。手数料・税金は含みません。同じ期間の TOPIX 連動ETF（1306）と比べます。件数が少ないうちは偶然の影響が大きいので、傾向は数か月分たまってから判断してください。</span></p>
      <div class="filters" role="group" aria-label="絞り込み">
        ${RESULT_FILTERS.map(([key, label]) => `<button class="button filters__option" type="button" data-filter="${key}" aria-pressed="${key === state.filter}">${label}</button>`).join("")}
      </div>
      <div id="result-stats"></div>
      <div class="table-wrap">
        <table class="table">
          <caption class="visually-hidden">候補になった銘柄のその後の値動き</caption>
          <thead><tr>${RESULT_COLUMNS.map(([key, label], index) => `<th scope="col" class="${index >= 2 ? "table__num" : ""}"><button class="table__sort" type="button" data-sort="${key}">${label}</button></th>`).join("")}</tr></thead>
          <tbody id="result-rows"></tbody>
        </table>
      </div>`),
  );

  const update = () => {
    const filter = RESULT_FILTERS.find(([key]) => key === state.filter)[2];
    const column = RESULT_COLUMNS.find(([key]) => key === state.sort);
    const value = column[2];
    const signals = bundle.signals.filter(filter).sort((a, b) => {
      const left = value(a);
      const right = value(b);
      if (left === right) return 0;
      if (left === null || left === undefined) return 1; // missing values always last
      if (right === null || right === undefined) return -1;
      return (left > right ? 1 : -1) * state.direction;
    });
    root.querySelector("#result-stats").replaceChildren(fragment(resultStats(signals)));
    root.querySelector("#result-rows").innerHTML = resultRows(signals);
    for (const button of root.querySelectorAll("[data-filter]")) {
      button.setAttribute("aria-pressed", String(button.dataset.filter === state.filter));
    }
    for (const button of root.querySelectorAll("[data-sort]")) {
      const active = button.dataset.sort === state.sort;
      if (active) button.setAttribute("aria-sort", state.direction > 0 ? "ascending" : "descending");
      else button.removeAttribute("aria-sort");
    }
  };
  root.addEventListener("click", (event) => {
    const filter = event.target.closest("[data-filter]");
    const sort = event.target.closest("[data-sort]");
    if (filter) state.filter = filter.dataset.filter;
    if (sort) {
      state.direction = state.sort === sort.dataset.sort ? -state.direction : -1;
      state.sort = sort.dataset.sort;
    }
    if (filter || sort) update();
  });
  update();
}

export function renderTrend(bundle, root) {
  const recent = [...bundle.days].reverse().slice(0, 10);
  root.replaceChildren(
    fragment(html`
      <div class="section__header"><h2>推移</h2><p>直近${bundle.days.length}営業日</p></div>
      <div class="panel" id="counts-panel">
        <h3>日ごとの候補数</h3>
        <ul class="legend">${COUNT_CLASSES.map((item) => `<li><span class="legend__swatch" style="--swatch: var(--chart-${item.modifier})"></span>${item.label}</li>`).join("")}</ul>
      </div>
      <div class="panel" id="market-panel">
        <h3>市場全体の流れ（TOPIX連動ETF・1306）</h3>
        <p class="muted">市場全体が下がっている時期は、候補の銘柄も下がりやすくなります。</p>
      </div>
      <div class="table-wrap">
        <table class="table">
          <caption class="visually-hidden">直近10営業日の候補数</caption>
          <thead><tr><th scope="col">日付</th>${COUNT_CLASSES.map((item) => `<th scope="col" class="table__num">${item.label}</th>`).join("")}<th scope="col" class="table__num">売買が多い会社</th></tr></thead>
          <tbody>${recent
            .map((day) => `<tr><td>${formatDate(day.date, { year: true })}</td>${COUNT_CLASSES.map((item) => `<td class="table__num">${day.counts?.[item.key] ?? 0}</td>`).join("")}<td class="table__num">${formatNumber(day.liquid_candidate_count)}</td></tr>`)
            .join("")}</tbody>
        </table>
      </div>`),
  );
  root.querySelector("#counts-panel").append(countsChart(bundle.days, COUNT_CLASSES));
  root.querySelector("#market-panel").append(
    priceChart(bundle.benchmark?.series, { volume: false, height: 180, label: "TOPIX連動ETFの値動き" }),
  );
}

export function renderGuide(bundle, root) {
  const early = bundle.thresholds?.early_candidate_score ?? "-";
  const watch = bundle.thresholds?.watch_score ?? "-";
  root.replaceChildren(
    fragment(html`
      <div class="section__header"><h2>見方</h2><p>株の知識がなくても読めるように、用語と使い方をまとめています。</p></div>
      <div class="guide">
        <article class="guide__item">
          <h3>このシステムがしていること</h3>
          <ol>
            <li>毎営業日の夕方（16:40ごろ）に、東証に上場する約3,800社の株価と売買量を集めます。</li>
            <li>売買が少なすぎる会社を除き、最近の値動きが良い上位25社を選びます。</li>
            <li>その25社の業績（売上・利益の伸びなど）と値動きを点数にして、分類します。</li>
            <li>結果を Slack に送り、このページに記録します。<b>売買は自動では行いません。</b></li>
          </ol>
        </article>
        <article class="guide__item">
          <h3>分類の意味</h3>
          <dl class="glossary">
            <dt>${badge("EARLY_CANDIDATE")}</dt><dd>点数${early}点以上、20日で上昇、売買量が以前の1.25倍以上。いちばん注目する分類です。</dd>
            <dt>${badge("WATCH")}</dt><dd>点数${watch}点以上で、有力候補の条件のどれかが足りない銘柄。</dd>
            <dt>${badge("OVEREXTENDED")}</dt><dd>${escapeHtml(classInfo("OVEREXTENDED").description)}</dd>
            <dt>${badge("NONE")}</dt><dd>${escapeHtml(classInfo("NONE").description)}</dd>
          </dl>
        </article>
        <article class="guide__item">
          <h3>数字の読み方</h3>
          <dl class="glossary">
            <dt>20日・60日の値動き</dt><dd>約1か月・約3か月前と比べて株価が何%動いたか。▲は上昇、▼は下落です。</dd>
            <dt>売買量の増え方</dt><dd>直近20日の売買された株数の平均が、その前の20日の何倍か。注目が集まり始めると増えます。</dd>
            <dt>高値からの距離</dt><dd>取得できた期間の最高値から何%下にいるか。0%に近いほど高値を更新しそうな位置です。</dd>
            <dt>1日の売買代金</dt><dd>1日に売買された金額の平均。少ない銘柄は、買いたい・売りたい値段で取引できないことがあります。</dd>
            <dt>点数</dt><dd>業績（売上・利益の伸び、上方修正など）と値動き（上昇・売買量・高値圏）を合計し、100点満点に直したものです。</dd>
          </dl>
        </article>
        <article class="guide__item">
          <h3>買う前に確認すること</h3>
          <ul>
            <li>決算発表の予定日が近くないか（発表の前後は大きく動きます）。</li>
            <li>増資・新株予約権（MSワラントなど）のお知らせがないか（株価が下がりやすくなります）。</li>
            <li>1日の売買代金が少なすぎないか。</li>
            <li>「過去の候補のその後」で、このシステムの最近の成績がどうか。</li>
            <li>いくらまで下がったら売るかを、買う前に決めておくこと。</li>
          </ul>
        </article>
        <article class="guide__item">
          <h3>売るタイミングの通知</h3>
          <p>買った銘柄を Google スプレッドシートの「保有銘柄」に登録すると、平日に4回、買ってからの最高値より一定の割合（初期値15%）下がっていないかを確認し、下がったら Slack に通知します。売るかどうかは、通知を見てご自身で判断してください。</p>
        </article>
        <article class="guide__item">
          <h3>このページのデータ</h3>
          <p>候補は暗号化して GitHub に保存しており、このページはあなたの端末の中でだけ復号します。データは日次スキャンのあとに自動で更新されます（最新: ${formatDate(bundle.latest_price_date, { year: true })}）。</p>
        </article>
      </div>`),
  );
}
