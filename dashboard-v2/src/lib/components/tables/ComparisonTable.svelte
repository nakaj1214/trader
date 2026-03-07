<script lang="ts">
	import type { StrategyInfo } from '$lib/types/prediction';

	let { strategies }: { strategies: Record<string, StrategyInfo> } = $props();

	function fmtCagr(v: number | null): string {
		if (v == null) return '-';
		return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
	}
	function fmtDd(v: number | null): string {
		return v != null ? (v * 100).toFixed(1) + '%' : '-';
	}
	function fmtSh(v: number | null): string {
		return v != null ? v.toFixed(2) : '-';
	}
</script>

<div class="mt-4 overflow-x-auto">
	<table
		class="w-full border-collapse overflow-hidden rounded-[12px] border border-border bg-surface text-[0.8125rem]"
	>
		<thead class="bg-surface-alt">
			<tr>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">投資手法</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">年間リターン</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">最大下落</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">効率</th>
			</tr>
		</thead>
		<tbody>
			{#each Object.values(strategies) as s}
				<tr class="transition-colors hover:bg-surface-alt">
					<td class="border-b border-border px-3 py-2 font-mono text-text">{s.label}</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{fmtCagr(s.cagr)}</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{fmtDd(s.max_drawdown)}</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{fmtSh(s.sharpe)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
