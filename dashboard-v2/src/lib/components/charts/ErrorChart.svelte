<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Chart from 'chart.js/auto';
	import type { ErrorBin } from '$lib/types/prediction';

	let { bins }: { bins: ErrorBin[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	onMount(() => {
		if (!bins || bins.length === 0) return;

		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: bins.map((b) => b.range),
				datasets: [
					{
						label: 'AIの予測 (%)',
						data: bins.map((b) => b.avg_predicted_pct),
						backgroundColor: 'rgba(37, 99, 235, 0.6)',
						borderColor: 'rgba(37, 99, 235, 1)',
						borderWidth: 1
					},
					{
						label: '実際の結果 (%)',
						data: bins.map((b) => b.avg_actual_pct),
						backgroundColor: 'rgba(22, 163, 74, 0.6)',
						borderColor: 'rgba(22, 163, 74, 1)',
						borderWidth: 1
					}
				]
			},
			options: {
				responsive: true,
				plugins: { title: { display: true, text: 'AIの予測 vs 実際の結果' } },
				scales: { y: { ticks: { callback: (v) => v + '%' } } }
			}
		});
	});

	onDestroy(() => chart?.destroy());
</script>

{#if bins && bins.length > 0}
	<div class="chart-container">
		<canvas bind:this={canvas}></canvas>
	</div>
{/if}
