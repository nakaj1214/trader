<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Chart from 'chart.js/auto';

	let {
		weeklyResults
	}: {
		weeklyResults: Array<{ date: string; pnl: number; cumPnl: number }>;
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	onMount(() => {
		if (!weeklyResults || weeklyResults.length === 0) return;

		const labels = weeklyResults.map((w) => w.date);
		const weeklyPnl = weeklyResults.map((w) => Math.round(w.pnl * 100) / 100);
		const cumPnl = weeklyResults.map((w) => Math.round(w.cumPnl * 100) / 100);

		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels,
				datasets: [
					{
						type: 'bar',
						label: '週次損益 ($)',
						data: weeklyPnl,
						backgroundColor: weeklyPnl.map((v) =>
							v >= 0 ? 'rgba(22, 163, 74, 0.6)' : 'rgba(220, 38, 38, 0.6)'
						),
						borderColor: weeklyPnl.map((v) =>
							v >= 0 ? 'rgba(22, 163, 74, 1)' : 'rgba(220, 38, 38, 1)'
						),
						borderWidth: 1,
						order: 2
					},
					{
						type: 'line',
						label: '累計損益 ($)',
						data: cumPnl,
						borderColor: 'rgba(37, 99, 235, 1)',
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
					y: {
						ticks: {
							callback: (v) => '$' + Number(v).toLocaleString()
						}
					}
				}
			}
		});
	});

	onDestroy(() => chart?.destroy());
</script>

{#if weeklyResults && weeklyResults.length > 0}
	<div class="chart-container">
		<canvas bind:this={canvas}></canvas>
	</div>
{/if}
