<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import type { Market } from '$lib/types/market';
	import type { PredictionsData, StockHistory, Prediction } from '$lib/types/prediction';
	import { loadJSON } from '$lib/data/loader';
	import { predictionsFile } from '$lib/data/loader';
	import { isTestTicker } from '$lib/utils/filter';
	import { formatPrice, formatPct, formatDate, hitLabel } from '$lib/utils/format';
	import PriceChart from '$lib/components/charts/PriceChart.svelte';

	let { data } = $props();
	const market: Market = data.market;

	let ticker = $state<string | null>(null);
	let tickerPredictions = $state<Prediction[]>([]);
	let tickerHistory = $state<Array<{ date: string; predicted_price: number; actual_price?: number | null }>>([]);
	let latestWithRisk = $state<Prediction | null>(null);
	let latestPred = $state<Prediction | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	onMount(async () => {
		ticker = $page.url.searchParams.get('ticker');
		if (!ticker) {
			error = 'ティッカーが指定されていません。';
			loading = false;
			return;
		}
		if (isTestTicker(ticker)) {
			error = 'テストデータは表示できません。';
			loading = false;
			return;
		}

		try {
			const [predData, histData] = await Promise.all([
				loadJSON<PredictionsData>(predictionsFile(market)),
				loadJSON<StockHistory>('stock_history.json')
			]);

			tickerPredictions = predData.predictions.filter((p) => p.ticker === ticker);
			tickerHistory = histData[ticker!] ?? [];

			if (tickerPredictions.length === 0 && tickerHistory.length === 0) {
				error = `「${ticker}」のデータが見つかりません。`;
				loading = false;
				return;
			}

			for (let i = tickerPredictions.length - 1; i >= 0; i--) {
				if (tickerPredictions[i].risk) {
					latestWithRisk = tickerPredictions[i];
					break;
				}
			}
			latestPred = tickerPredictions.length > 0 ? tickerPredictions[tickerPredictions.length - 1] : null;
		} catch {
			error = 'データを読み込めませんでした。';
		}
		loading = false;
	});

	const sortedPredictions = $derived(
		tickerPredictions.slice().sort((a, b) => b.date.localeCompare(a.date))
	);

	// Sanity banner
	const sanityFlags = $derived(latestPred?.sanity_flags ?? []);
	const isClipped = $derived(sanityFlags.includes('CLIPPED'));
	const isWarn = $derived(sanityFlags.includes('WARN_HIGH'));
	const showSanity = $derived(isClipped || isWarn);
</script>

<svelte:head>
	<title>{ticker ?? 'Stock'} - AI Stock Predictions</title>
</svelte:head>

{#if loading}
	<div class="py-10 text-center text-sm text-text-muted">読み込み中...</div>
{:else if error}
	<div class="py-12 text-center text-sm text-text-muted">{error}</div>
{:else}
	<!-- Ticker title -->
	<h2 class="mb-4 font-mono text-2xl font-bold tracking-wide text-primary">{ticker}</h2>

	<!-- Sanity banner -->
	{#if showSanity && latestPred}
		<div class="mb-4 rounded-sm border border-warning/25 bg-warning/10 px-4 py-3 text-sm leading-relaxed text-warning">
			{#if isClipped}
				<strong>⚠ この予測は不安定です</strong><br />
				AIの予測が極端すぎるため、表示値を調整しています。
				表示値: {formatPct(latestPred.predicted_change_pct_clipped)}
				（元の予測値: {formatPct(latestPred.predicted_change_pct)}）
			{:else}
				<strong>⚠ 予測の変動が大きめです</strong><br />
				予測の変動が通常より大きくなっています（{formatPct(latestPred.predicted_change_pct)}）。参考程度にご確認ください。
			{/if}
		</div>
	{/if}

	<!-- Risk panel -->
	{#if latestWithRisk?.risk}
		<div class="mb-4 rounded-[12px] border border-border bg-surface p-[1.125rem] shadow">
			<h3 class="mb-3 font-display text-[0.9375rem] font-semibold text-text">リスク指標</h3>
			<div class="flex flex-wrap gap-6 font-mono text-sm">
				<span>値動きの大きさ: {(latestWithRisk.risk.vol_20d_ann * 100).toFixed(0)}%（年率）</span>
				<span>最大下落: {(latestWithRisk.risk.max_drawdown_1y * 100).toFixed(0)}%</span>
			</div>
			{#if latestWithRisk.events && latestWithRisk.events.length > 0}
				<div class="mt-2 flex flex-wrap gap-2">
					{#each latestWithRisk.events as ev}
						<span class="inline-block rounded-full border border-warning/25 bg-warning/10 px-2.5 py-0.5 text-[0.6875rem] font-semibold text-warning">
							{ev.type === 'earnings' ? `決算発表まで ${ev.days_to} 日` : `配当日まで ${ev.days_to} 日`}
						</span>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Sizing panel -->
	{#if latestWithRisk?.sizing}
		{@const s = latestWithRisk.sizing}
		<div class="mb-4 rounded-[12px] border border-border bg-surface p-[1.125rem] shadow">
			<h3 class="mb-3 font-display text-[0.9375rem] font-semibold text-text">売買ガイド</h3>
			<div class="flex flex-col gap-1">
				<div class="flex justify-between border-b border-border py-1 text-[0.8125rem]">
					<span class="text-text-muted">おすすめ投資比率</span>
					<span class="font-mono font-semibold text-text">{s.max_position_weight != null ? (s.max_position_weight * 100).toFixed(0) + '%' : '-'}</span>
				</div>
				<div class="flex justify-between border-b border-border py-1 text-[0.8125rem]">
					<span class="text-text-muted">損切りライン</span>
					<span class="font-mono font-semibold text-danger">{s.stop_loss_pct != null ? (s.stop_loss_pct * 100).toFixed(1) + '%' : '-'}</span>
				</div>
			</div>
			{#if s.stop_loss_pct != null && latestWithRisk.current_price}
				{@const stopPrice = latestWithRisk.current_price * (1 + s.stop_loss_pct)}
				<div class="mt-3 rounded-[12px] border-2 border-danger/40 bg-danger/[0.08] p-3">
					<div class="font-display text-[0.6875rem] font-bold uppercase tracking-wider text-danger">この価格を下回ったら売りを検討</div>
					<div class="font-mono text-2xl font-bold text-danger [text-shadow:0_0_16px_rgba(251,113,133,0.25)]">{formatPrice(stopPrice, market)}</div>
					<div class="text-[0.6875rem] text-danger/80">現在価格 {formatPrice(latestWithRisk.current_price, market)} から {(s.stop_loss_pct * 100).toFixed(1)}% 下落した水準</div>
				</div>
			{/if}
			{#if latestWithRisk.predicted_price}
				<div class="mt-2 flex items-center justify-between rounded-[12px] border border-success/20 bg-success/[0.08] px-3 py-2">
					<span class="font-display text-xs font-semibold text-success">AIの予測価格</span>
					<span class="font-mono text-lg font-bold text-success [text-shadow:0_0_12px_rgba(52,211,153,0.2)]">{formatPrice(latestWithRisk.predicted_price, market)}</span>
				</div>
			{/if}
			{#if s.stop_loss_rationale}
				<p class="mt-2 text-[0.6875rem] italic text-text-muted">※ {s.stop_loss_rationale}</p>
			{/if}
		</div>
	{/if}

	<!-- Evidence panel -->
	{#if latestWithRisk?.evidence}
		{@const ev = latestWithRisk.evidence}
		<div class="mb-4 rounded-[12px] border border-border bg-surface p-[1.125rem] shadow">
			<h3 class="mb-3 font-display text-[0.9375rem] font-semibold text-text">
				予測の根拠 <span class="text-[0.6875rem] font-normal text-text-muted">なぜこの銘柄が選ばれたか</span>
			</h3>
			{#each [
				{ label: '上昇の勢い', key: 'momentum_z' },
				{ label: '割安度', key: 'value_z' },
				{ label: '企業の稼ぐ力', key: 'quality_z' },
				{ label: '安定度', key: 'low_risk_z' }
			] as factor}
				{@const z = ev[factor.key as keyof typeof ev] as number | null}
				<div class="flex items-center gap-3 py-1 text-[0.8125rem]">
					<span class="min-w-20 font-medium text-text-muted">{factor.label}</span>
					{#if z == null}
						<span class="text-xs italic text-text-muted">データなし</span>
					{:else}
						{@const pct = Math.min(Math.abs(z) / 3 * 100, 100)}
						<div class="max-w-[200px] flex-1 overflow-hidden rounded-sm bg-border" style="height:6px">
							<div
								class="h-full rounded-sm transition-all duration-400"
								class:bg-gradient-to-r={true}
								class:from-success={z >= 0}
								class:to-green-300={z >= 0}
								class:from-danger={z < 0}
								class:to-red-300={z < 0}
								style="width:{pct}%"
							></div>
						</div>
						<span class="min-w-12 text-right font-mono text-xs text-text">{z >= 0 ? '+' : ''}{z.toFixed(2)}</span>
						<span class="text-xs {z >= 0 ? 'text-success' : 'text-danger'}">{z >= 0 ? '▲ プラス要因' : '▼ マイナス要因'}</span>
					{/if}
				</div>
			{/each}
			{#if ev.composite != null}
				<div class="mt-2.5 font-mono text-[0.9375rem] font-bold text-primary">
					総合スコア: {ev.composite} / 100
				</div>
			{/if}
		</div>
	{/if}

	<!-- Explanations panel -->
	{#if latestWithRisk?.explanations?.factors?.length}
		{@const expl = latestWithRisk.explanations}
		<div class="mb-4 rounded-[12px] border border-border bg-surface p-[1.125rem] shadow">
			<h3 class="mb-1 font-display text-[0.9375rem] font-semibold text-text">この銘柄が選ばれた理由</h3>
			<p class="mb-2 text-[0.8125rem] text-text-muted">AIがこの銘柄を推薦した理由:</p>
			{#each expl.factors as f, i}
				{@const nums = ['①', '②', '③']}
				<div class="py-1 text-sm text-text">
					{nums[i] ?? ''} {f.text} (+{f.impact.toFixed(3)})
				</div>
			{/each}
			<p class="mt-2 text-[0.6875rem] italic text-text-muted">{expl.note}</p>
		</div>
	{/if}

	<!-- Short interest panel -->
	{#if latestWithRisk?.short_interest}
		{@const si = latestWithRisk.short_interest}
		{@const signalMap = { high_short: '高（空売り圧力大）', moderate_short: '中程度', neutral: '低〜中（通常）' } as Record<string, string>}
		<div class="mb-4 rounded-[12px] border border-border bg-surface p-[1.125rem] shadow">
			<h3 class="mb-3 font-display text-[0.9375rem] font-semibold text-text">
				空売りの状況 <span class="text-[0.6875rem] font-normal text-text-muted">参考情報</span>
			</h3>
			<div class="flex flex-col gap-1.5">
				<div class="flex justify-between border-b border-border py-1 text-[0.8125rem]">
					<span class="text-text-muted">空売り日数</span>
					<span class="font-mono font-medium text-text">{si.short_ratio != null ? si.short_ratio.toFixed(1) + ' 日' : '-'}</span>
				</div>
				<div class="flex justify-between border-b border-border py-1 text-[0.8125rem]">
					<span class="text-text-muted">空売り比率</span>
					<span class="font-mono font-medium text-text">{si.short_pct_float != null ? (si.short_pct_float * 100).toFixed(1) + '%' : '-'}</span>
				</div>
				<div class="flex justify-between py-1 text-[0.8125rem]">
					<span class="text-text-muted">シグナル</span>
					<span class="font-mono font-medium text-text">{signalMap[si.signal] ?? si.signal}</span>
				</div>
			</div>
			{#if si.data_note}
				<p class="mt-2 text-[0.6875rem] text-text-muted">{si.data_note}</p>
			{/if}
		</div>
	{/if}

	<!-- Institutional panel -->
	{#if latestWithRisk?.institutional}
		{@const inst = latestWithRisk.institutional}
		<div class="mb-4 rounded-[12px] border border-border bg-surface p-[1.125rem] shadow">
			<h3 class="mb-3 font-display text-[0.9375rem] font-semibold text-text">
				大口投資家の保有状況 <span class="text-[0.6875rem] font-normal text-text-muted">参考情報</span>
			</h3>
			<div class="flex flex-col gap-1.5">
				<div class="flex justify-between border-b border-border py-1 text-[0.8125rem]">
					<span class="text-text-muted">大口投資家の保有率</span>
					<span class="font-mono font-medium text-text">{inst.institutional_pct != null ? (inst.institutional_pct * 100).toFixed(1) + '%' : '-'}</span>
				</div>
				<div class="flex justify-between py-1 text-[0.8125rem]">
					<span class="text-text-muted">主な保有者</span>
					<span class="font-mono font-medium text-text">{inst.top5_holders?.length ? inst.top5_holders.join('、') : '-'}</span>
				</div>
			</div>
			{#if inst.data_note}
				<p class="mt-2 text-[0.6875rem] text-text-muted">{inst.data_note}</p>
			{/if}
		</div>
	{/if}

	<!-- Price chart -->
	{#if ticker}
		<section class="mb-7">
			<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">株価チャート</h2>
			<PriceChart history={tickerHistory} {ticker} {market} />
		</section>
	{/if}

	<!-- History table -->
	<section class="mb-7">
		<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">予測履歴</h2>
		{#if sortedPredictions.length === 0}
			<div class="py-12 text-center text-sm text-text-muted">予測履歴がありません。</div>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full border-collapse overflow-hidden rounded-[12px] border border-border bg-surface text-[0.8125rem]">
					<thead class="bg-surface-alt">
						<tr>
							<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">日付</th>
							<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">AIの予測</th>
							<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">実際の価格</th>
							<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">予測変動</th>
							<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">結果</th>
						</tr>
					</thead>
					<tbody>
						{#each sortedPredictions as p}
							{@const dPct = p.predicted_change_pct_clipped ?? p.predicted_change_pct}
							{@const pFlags = p.sanity_flags ?? []}
							{@const pClipped = pFlags.includes('CLIPPED')}
							{@const pWarn = pFlags.includes('WARN_HIGH')}
							{@const h = hitLabel(p.hit)}
							{@const hClass = { hit: 'bg-success/15 text-success border-success/30', miss: 'bg-danger/15 text-danger border-danger/30', pending: 'bg-primary/10 text-primary border-primary/25' }[h.type]}
							<tr class="transition-colors hover:bg-surface-alt">
								<td class="border-b border-border px-3 py-2 font-mono text-text">{formatDate(p.date)}</td>
								<td class="border-b border-border px-3 py-2 font-mono text-text">{formatPrice(p.predicted_price, market)}</td>
								<td class="border-b border-border px-3 py-2 font-mono text-text">{formatPrice(p.actual_price, market)}</td>
								<td class="border-b border-border px-3 py-2 font-mono text-text">
									{formatPct(dPct)}
									{#if pClipped}
										<span class="ml-1 rounded bg-danger/10 px-1 py-0.5 text-[0.6875rem] font-semibold text-danger">⚠ 不安定</span>
									{:else if pWarn}
										<span class="ml-1 rounded bg-warning/10 px-1 py-0.5 text-[0.6875rem] font-semibold text-warning">⚠ 注意</span>
									{/if}
								</td>
								<td class="border-b border-border px-3 py-2">
									<span class="inline-block rounded-full border px-2 py-0.5 font-mono text-[0.6875rem] font-semibold {hClass}">{h.text}</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
{/if}
