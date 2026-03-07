<script lang="ts">
	import { onMount } from 'svelte';
	import type { Market } from '$lib/types/market';
	import type { PredictionsData, MacroData } from '$lib/types/prediction';
	import { loadJSON, loadJSONSafe, predictionsFile } from '$lib/data/loader';
	import PredictionGrid from '$lib/components/cards/PredictionGrid.svelte';
	import MacroBanner from '$lib/components/panels/MacroBanner.svelte';
	import TimingGuide from '$lib/components/panels/TimingGuide.svelte';

	let { data } = $props();
	const market: Market = data.market;

	let predictions = $state<PredictionsData | null>(null);
	let macro = $state<MacroData | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			predictions = await loadJSON<PredictionsData>(predictionsFile(market));
			if (market === 'us') {
				macro = await loadJSONSafe<MacroData>('macro.json');
			}
		} catch (e) {
			error = market === 'jp'
				? '日本株データを読み込めませんでした。まだデータ収集中の可能性があります。'
				: 'データを読み込めませんでした。';
		}
	});
</script>

<svelte:head>
	<title>{market === 'jp' ? '日本株' : '米国株'} AI Stock Predictions</title>
</svelte:head>

{#if market === 'us'}
	<MacroBanner {macro} />
{/if}

{#if market === 'jp'}
	<div
		class="mb-4 rounded-[12px] border border-border bg-surface p-4 text-sm text-text-muted shadow"
	>
		<strong class="text-text">日本株（日経225）</strong> — 価格は円で表示しています。1単元＝100株の最低投資額も表示されます。
	</div>
{/if}

<TimingGuide />

{#if error}
	<div class="py-12 text-center text-sm text-text-muted">{error}</div>
{:else if predictions}
	<PredictionGrid predictions={predictions.predictions} {market} />
{:else}
	<div class="py-10 text-center text-sm text-text-muted">読み込み中...</div>
{/if}
