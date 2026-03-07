<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Chart from 'chart.js/auto';
	import type { StrategyInfo } from '$lib/types/prediction';

	let { strategies }: { strategies: Record<string, StrategyInfo> } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	const COLORS: Record<string, { border: string; bg: string }> = {
		ai: { border: 'rgba(37, 99, 235, 1)', bg: 'rgba(37, 99, 235, 0.1)' },
		momentum_12_1: { border: 'rgba(22, 163, 74, 1)', bg: 'rgba(22, 163, 74, 0.1)' },
		benchmark_spy: { border: 'rgba(156, 163, 175, 1)', bg: 'rgba(156, 163, 175, 0.1)' }
	};

	onMount(() => {
		const keys = Object.keys(strategies);
		if (keys.length === 0) return;

		const datasets = keys
			.filter((k) => strategies[k].equity_curve?.length > 0)
			.map((key) => {
				const s = strategies[key];
				const c = COLORS[key] ?? { border: 'rgba(100,100,100,1)', bg: 'rgba(100,100,100,0.1)' };
				return {
					label: s.label,
					data: s.equity_curve.map((pt) => pt.equity),
					borderColor: c.border,
					backgroundColor: c.bg,
					borderWidth: 2,
					fill: false,
					tension: 0.1,
					pointRadius: 0
				};
			});

		if (datasets.length === 0) return;

		const labelSource = strategies['ai'] ?? strategies[keys[0]];
		const labels = labelSource.equity_curve.map((pt) => pt.date);

		chart = new Chart(canvas, {
			type: 'line',
			data: { labels, datasets },
			options: {
				responsive: true,
				plugins: {
					title: { display: true, text: '投資成果の比較（1万円が何円になったか）' },
					legend: { position: 'top' }
				},
				scales: { y: { ticks: { callback: (v) => (v as number).toFixed(2) } } }
			}
		});
	});

	onDestroy(() => chart?.destroy());
</script>

{#if Object.keys(strategies).length > 0}
	<div class="chart-container">
		<canvas bind:this={canvas}></canvas>
	</div>
{/if}
