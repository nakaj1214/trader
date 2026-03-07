<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Chart from 'chart.js/auto';
	import type { Market } from '$lib/types/market';

	let {
		history,
		ticker,
		market
	}: {
		history: Array<{ date: string; predicted_price: number; actual_price?: number | null }>;
		ticker: string;
		market: Market;
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	const currencyPrefix = $derived(market === 'jp' ? '\u00a5' : '$');

	onMount(() => {
		if (!history || history.length === 0) return;

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels: history.map((h) => h.date),
				datasets: [
					{
						label: 'AIの予測',
						data: history.map((h) => h.predicted_price),
						borderColor: 'rgba(37, 99, 235, 1)',
						backgroundColor: 'rgba(37, 99, 235, 0.1)',
						borderWidth: 2,
						fill: false,
						tension: 0.1
					},
					{
						label: '実際の株価',
						data: history.map((h) => h.actual_price ?? null),
						borderColor: 'rgba(22, 163, 74, 1)',
						backgroundColor: 'rgba(22, 163, 74, 0.1)',
						borderWidth: 2,
						fill: false,
						tension: 0.1,
						spanGaps: false
					}
				]
			},
			options: {
				responsive: true,
				plugins: { title: { display: true, text: `${ticker} 株価の動き` } },
				scales: { y: { ticks: { callback: (v) => currencyPrefix + v } } }
			}
		});
	});

	onDestroy(() => chart?.destroy());
</script>

{#if history && history.length > 0}
	<div class="chart-container">
		<canvas bind:this={canvas}></canvas>
	</div>
{/if}
