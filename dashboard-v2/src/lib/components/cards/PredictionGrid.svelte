<script lang="ts">
	import type { Market } from '$lib/types/market';
	import type { Prediction } from '$lib/types/prediction';
	import { filterPredictions, getLatestWeekDate, deduplicateByTicker } from '$lib/utils/filter';
	import PredictionCard from './PredictionCard.svelte';

	let { predictions, market }: { predictions: Prediction[]; market: Market } = $props();

	const filtered = $derived(filterPredictions(predictions));
	const latestDate = $derived(getLatestWeekDate(filtered));
	const latestPredictions = $derived(
		latestDate ? filtered.filter((p) => p.date === latestDate) : []
	);
	const deduped = $derived(deduplicateByTicker(latestPredictions));
</script>

<section>
	<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold text-text tracking-tight">
		今週の予測 (<span>{latestDate ?? '-'}</span>)
	</h2>

	{#if deduped.length === 0}
		<div class="py-12 text-center text-sm text-text-muted">
			{market === 'jp' ? '日本株の予測データがありません。データ収集をお待ちください。' : '予測データがありません。'}
		</div>
	{:else}
		<div class="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3.5">
			{#each deduped as prediction (prediction.ticker)}
				<PredictionCard {prediction} {market} />
			{/each}
		</div>
	{/if}
</section>
