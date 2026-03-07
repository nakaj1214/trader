<script lang="ts">
	import type { Market } from '$lib/types/market';
	import type { Prediction } from '$lib/types/prediction';

	let { predictions, market }: { predictions: Prediction[]; market: Market } = $props();

	const confirmed = $derived(predictions.filter((p) => p.hit === '的中' || p.hit === '外れ'));

	const ranking = $derived(() => {
		const stats: Record<string, { hits: number; total: number }> = {};
		for (const p of confirmed) {
			if (!stats[p.ticker]) stats[p.ticker] = { hits: 0, total: 0 };
			stats[p.ticker].total++;
			if (p.hit === '的中') stats[p.ticker].hits++;
		}
		return Object.entries(stats)
			.map(([ticker, s]) => ({
				ticker,
				hits: s.hits,
				total: s.total,
				rate: s.total > 0 ? Math.round((s.hits / s.total) * 1000) / 10 : 0
			}))
			.sort((a, b) => b.rate - a.rate || b.hits - a.hits);
	});
</script>

{#if confirmed.length === 0}
	<div class="py-12 text-center text-sm text-text-muted">
		まだ結果が確定した予測がありません。
	</div>
{:else}
	<div class="overflow-x-auto">
		<table
			class="w-full border-collapse overflow-hidden rounded-[12px] border border-border bg-surface text-[0.8125rem]"
		>
			<thead class="bg-surface-alt">
				<tr>
					<th
						class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
						>#</th
					>
					<th
						class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
						>銘柄</th
					>
					<th
						class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
						>当たった割合</th
					>
					<th
						class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
						>当たり/全体</th
					>
				</tr>
			</thead>
			<tbody>
				{#each ranking() as r, i}
					<tr class="transition-colors hover:bg-surface-alt">
						<td class="border-b border-border px-3 py-2 font-mono text-text">{i + 1}</td>
						<td class="border-b border-border px-3 py-2 font-mono text-text">
							<a href="/{market}/stock?ticker={encodeURIComponent(r.ticker)}" class="text-primary hover:underline">
								{r.ticker}
							</a>
						</td>
						<td class="border-b border-border px-3 py-2 font-mono text-text"
							>{r.rate.toFixed(1)}%</td
						>
						<td class="border-b border-border px-3 py-2 font-mono text-text"
							>{r.hits}/{r.total}</td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
