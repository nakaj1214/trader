<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Chart from 'chart.js/auto';
	import type { CalibrationGroup } from '$lib/types/prediction';

	let { calibration }: { calibration: CalibrationGroup } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	onMount(() => {
		const bins = calibration?.reliability_bins;
		if (!bins || bins.length === 0) return;

		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: bins.map((b) => b.p_bin),
				datasets: [
					{
						type: 'bar',
						label: '実際に上がった割合',
						data: bins.map((b) => b.empirical),
						backgroundColor: 'rgba(37, 99, 235, 0.6)',
						borderColor: 'rgba(37, 99, 235, 1)',
						borderWidth: 1,
						order: 2
					},
					{
						type: 'line',
						label: 'AIの予測確率',
						data: bins.map((b) => b.mean_pred),
						borderColor: 'rgba(220, 38, 38, 1)',
						backgroundColor: 'transparent',
						borderWidth: 2,
						pointRadius: 5,
						order: 1
					}
				]
			},
			options: {
				responsive: true,
				plugins: {
					title: { display: true, text: '予測の信頼度チェック' },
					tooltip: {
						callbacks: {
							label: (ctx) =>
								ctx.dataset.label + ': ' + ((ctx.parsed.y as number) * 100).toFixed(1) + '%'
						}
					}
				},
				scales: {
					y: {
						beginAtZero: true,
						max: 1.0,
						ticks: { callback: (v) => ((v as number) * 100).toFixed(0) + '%' }
					}
				}
			}
		});
	});

	onDestroy(() => chart?.destroy());
</script>

{#if calibration?.reliability_bins?.length}
	<div class="chart-container">
		<canvas bind:this={canvas}></canvas>
	</div>
{/if}
