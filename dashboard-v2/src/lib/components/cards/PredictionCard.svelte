<script lang="ts">
	import type { Market } from '$lib/types/market';
	import type { Prediction } from '$lib/types/prediction';
	import { formatPrice, formatPct, formatUnitInfo, hitLabel } from '$lib/utils/format';

	let { prediction, market }: { prediction: Prediction; market: Market } = $props();

	const displayPct = $derived(
		prediction.predicted_change_pct_clipped ?? prediction.predicted_change_pct
	);
	const flags = $derived(prediction.sanity_flags ?? []);
	const isClipped = $derived(flags.includes('CLIPPED'));
	const isWarn = $derived(flags.includes('WARN_HIGH'));
	const changeClass = $derived(displayPct >= 0 ? 'text-success' : 'text-danger');
	const hit = $derived(hitLabel(prediction.hit));
	const badgeClass = $derived({
		hit: 'bg-success/15 text-success border-success/30',
		miss: 'bg-danger/15 text-danger border-danger/30',
		pending: 'bg-primary/10 text-primary border-primary/25'
	}[hit.type]);

	const unitInfo = $derived(market === 'jp' ? formatUnitInfo(prediction.current_price) : null);
</script>

<div
	class="rounded-[12px] border border-border bg-surface p-[1.125rem] shadow transition-all duration-200 hover:border-border-highlight hover:shadow-glow"
>
	<!-- Ticker -->
	<div class="font-mono text-[1.0625rem] font-bold tracking-wide text-primary">
		<a href="/{market}/stock?ticker={encodeURIComponent(prediction.ticker)}" class="hover:underline">
			{prediction.ticker}
		</a>
		{#if isClipped}
			<span
				class="ml-1 rounded bg-danger/10 px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-danger border border-danger/30"
			>⚠ 不安定</span>
		{/if}
		{#if isWarn}
			<span
				class="ml-1 rounded bg-warning/10 px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-warning border border-warning/30"
			>⚠ 注意</span>
		{/if}
	</div>

	<!-- Prices -->
	<div class="mt-2 flex items-center justify-between">
		<span class="font-mono text-[0.9375rem] text-text">
			{formatPrice(prediction.current_price, market)} → {formatPrice(prediction.predicted_price, market)}
		</span>
		<span class="font-mono text-[0.9375rem] font-semibold {changeClass}">
			{formatPct(displayPct)}
			{#if isClipped}
				<span class="ml-1 font-mono text-[0.6875rem] font-normal text-text-muted">
					(元値: {formatPct(prediction.predicted_change_pct)})
				</span>
			{/if}
		</span>
	</div>

	<!-- Actual -->
	<div class="mt-1 flex items-center justify-between">
		<span class="font-mono text-[0.9375rem] text-text">
			実績: {formatPrice(prediction.actual_price, market)}
		</span>
		<span
			class="inline-block rounded-full border px-2 py-0.5 font-mono text-[0.6875rem] font-semibold {badgeClass}"
		>
			{hit.text}
		</span>
	</div>

	<!-- JP unit info -->
	{#if unitInfo}
		<div class="mt-2 rounded-md bg-surface-alt px-2.5 py-1 font-mono text-xs text-text-muted">
			{unitInfo}
		</div>
	{/if}

	<!-- JP sector / fundamentals -->
	{#if prediction.jp_listed_info}
		{@const li = prediction.jp_listed_info}
		{@const sectorText = [li.sector_17, li.market_section].filter(Boolean).join(' | ')}
		{#if sectorText}
			<div class="mt-1 rounded-md bg-surface-alt px-2.5 py-1 text-xs text-text-muted">
				{sectorText}
			</div>
		{/if}
	{/if}

	{#if prediction.jp_fundamentals}
		{@const f = prediction.jp_fundamentals}
		{@const parts = [
			f.eps != null ? `EPS \u00a5${Math.round(f.eps).toLocaleString('ja-JP')}` : null,
			f.forecast_eps != null ? `予想EPS \u00a5${Math.round(f.forecast_eps).toLocaleString('ja-JP')}` : null,
			f.dividend_annual != null ? `配当 \u00a5${Math.round(f.dividend_annual).toLocaleString('ja-JP')}/年` : null,
			f.payout_ratio != null ? `配当性向 ${(f.payout_ratio * 100).toFixed(0)}%` : null,
			f.operating_margin != null ? `営業利益率 ${(f.operating_margin * 100).toFixed(1)}%` : null
		].filter(Boolean)}
		{#if parts.length > 0}
			<div class="mt-1 rounded-md bg-surface-alt px-2.5 py-1 text-xs text-text-muted">
				{parts.join(' | ')}
			</div>
		{/if}
	{/if}

	<!-- Risk -->
	{#if prediction.risk}
		<div class="mt-2 rounded-md bg-surface-alt px-2.5 py-1 font-mono text-xs text-text-muted">
			値動き {(prediction.risk.vol_20d_ann * 100).toFixed(0)}% | 最大下落 {(prediction.risk.max_drawdown_1y * 100).toFixed(0)}%
			{#if prediction.sizing?.max_position_weight != null}
				| 推奨投資比率 {(prediction.sizing.max_position_weight * 100).toFixed(0)}%
			{/if}
		</div>
	{/if}

	<!-- Events -->
	{#if prediction.events && prediction.events.length > 0}
		<div class="mt-2 flex flex-wrap gap-2">
			{#each prediction.events as ev}
				<span
					class="inline-block rounded-full border border-warning/25 bg-warning/10 px-2.5 py-0.5 text-[0.6875rem] font-semibold text-warning"
				>
					{ev.type === 'earnings' ? `決算発表 ${ev.days_to}日後` : `配当日 ${ev.days_to}日後`}
				</span>
			{/each}
		</div>
	{/if}

	<!-- Action row -->
	{#if prediction.status === '予測済み'}
		{#if displayPct > 0}
			<div
				class="mt-2 rounded-sm border border-success/20 bg-success/[0.08] px-2.5 py-1.5 text-xs font-semibold text-success"
			>
				▲ 買い候補（来週 {formatPct(displayPct)}）
			</div>
		{:else}
			<div
				class="mt-2 rounded-sm border border-border bg-surface-alt px-2.5 py-1.5 text-xs text-text-muted"
			>
				– 様子見（来週 {formatPct(displayPct)}）
			</div>
		{/if}
		{#if prediction.sizing?.stop_loss_pct != null && prediction.current_price}
			<div class="mt-1 px-2.5 font-mono text-[0.6875rem] text-danger">
				売るべき価格: {formatPrice(prediction.current_price * (1 + prediction.sizing.stop_loss_pct), market)} を下回ったら売ることを検討
			</div>
		{/if}
	{/if}
</div>
