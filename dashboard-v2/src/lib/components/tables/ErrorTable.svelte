<script lang="ts">
	import type { ErrorBin } from '$lib/types/prediction';
	import { formatPct } from '$lib/utils/format';

	let { bins }: { bins: ErrorBin[] } = $props();
</script>

{#if bins && bins.length > 0}
	<div class="mt-4 overflow-x-auto">
		<table
			class="w-full border-collapse overflow-hidden rounded-[12px] border border-border bg-surface text-[0.8125rem]"
		>
			<thead class="bg-surface-alt">
				<tr>
					<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">予測の範囲</th>
					<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">AIの予測</th>
					<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">実際の結果</th>
					<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">当たった割合</th>
					<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">件数</th>
				</tr>
			</thead>
			<tbody>
				{#each bins as b}
					<tr class="transition-colors hover:bg-surface-alt">
						<td class="border-b border-border px-3 py-2 font-mono text-text">{b.range}</td>
						<td class="border-b border-border px-3 py-2 font-mono text-text">{formatPct(b.avg_predicted_pct)}</td>
						<td class="border-b border-border px-3 py-2 font-mono text-text">{formatPct(b.avg_actual_pct)}</td>
						<td class="border-b border-border px-3 py-2 font-mono text-text">{b.hit_rate_pct.toFixed(1)}%</td>
						<td class="border-b border-border px-3 py-2 font-mono text-text">{b.count}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
