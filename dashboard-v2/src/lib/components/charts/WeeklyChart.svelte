<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Chart from 'chart.js/auto';
	import type { WeeklyStat } from '$lib/types/prediction';

	let { weekly }: { weekly: WeeklyStat[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	onMount(() => {
		if (!weekly || weekly.length === 0) return;

		const labels = weekly.map((w) => w.date);
		const hitRates = weekly.map((w) => w.hit_rate_pct);

		let cumHits = 0;
		let cumTotal = 0;
		const cumRates = weekly.map((w) => {
			cumHits += w.hits;
			cumTotal += w.total;
			return cumTotal > 0 ? Math.round((cumHits / cumTotal) * 1000) / 10 : 0;
		});

		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels,
				datasets: [
					{
						type: 'bar',
						label: '週の的中率 (%)',
						data: hitRates,
						backgroundColor: 'rgba(37, 99, 235, 0.6)',
						borderColor: 'rgba(37, 99, 235, 1)',
						borderWidth: 1,
						order: 2
					},
					{
						type: 'line',
						label: '全体の的中率 (%)',
						data: cumRates,
						borderColor: 'rgba(220, 38, 38, 1)',
						backgroundColor: 'transparent',
						borderWidth: 2,
						pointRadius: 3,
						order: 1
					}
				]
			},
			options: {
				responsive: true,
				scales: {
					y: { beginAtZero: true, max: 100, ticks: { callback: (v) => v + '%' } }
				}
			}
		});
	});

	onDestroy(() => chart?.destroy());
</script>

{#if weekly && weekly.length > 0}
	<div class="chart-container">
		<canvas bind:this={canvas}></canvas>
	</div>
{/if}
