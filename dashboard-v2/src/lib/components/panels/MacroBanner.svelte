<script lang="ts">
	import type { MacroData } from '$lib/types/prediction';

	let { macro }: { macro: MacroData | null } = $props();

	const isRiskOff = $derived(macro?.regime?.is_risk_off === true);

	const seriesText = $derived(() => {
		if (!macro?.series) return '';
		const parts: string[] = [];
		const ff = macro.series['FEDFUNDS'];
		if (ff?.latest_value != null) parts.push(`米国金利: ${ff.latest_value.toFixed(2)}${ff.unit}`);
		const ty = macro.series['T10Y2Y'];
		if (ty?.latest_value != null) {
			const spread = ty.latest_value;
			parts.push(`金利差: ${spread >= 0 ? '+' : ''}${spread.toFixed(2)}${ty.unit}`);
		}
		const vix = macro.series['VIXCLS'];
		if (vix?.latest_value != null) parts.push(`VIX: ${vix.latest_value.toFixed(1)}`);
		return parts.join(' | ');
	});

	const asOfText = $derived(
		macro?.data_as_of_utc ? `データ日: ${macro.data_as_of_utc.slice(0, 10)}` : ''
	);
</script>

{#if macro}
	<div
		class="mb-4 rounded-[12px] border px-4 py-2.5 text-[0.8125rem] {isRiskOff ? 'border-danger/30 bg-danger/10' : 'border-border-highlight bg-primary/5'}"
	>
		<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
			<span
				class="whitespace-nowrap font-display font-bold"
				class:text-primary={!isRiskOff}
				class:text-danger={isRiskOff}
			>
				{isRiskOff ? '⚠ 市場が不安定です' : '市場の状況'}
			</span>
			<span class="font-mono text-[0.8125rem] text-text">{seriesText()}</span>
			{#if macro.regime.note}
				<span class="text-xs italic text-text-muted">{macro.regime.note}</span>
			{/if}
			{#if asOfText}
				<span class="ml-auto font-mono text-[0.6875rem] text-text-muted">{asOfText}</span>
			{/if}
		</div>
	</div>
{/if}
