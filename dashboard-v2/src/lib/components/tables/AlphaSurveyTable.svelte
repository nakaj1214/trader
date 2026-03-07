<script lang="ts">
	import type { AlphaSurveyData } from '$lib/types/prediction';

	let { survey }: { survey: AlphaSurveyData } = $props();
</script>

<div class="overflow-x-auto">
	<table
		class="w-full border-collapse overflow-hidden rounded-[12px] border border-border bg-surface text-[0.8125rem]"
	>
		<thead class="bg-surface-alt">
			<tr>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">市場パターン</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">データ数</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">信頼度</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">確からしさ</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">効率</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">状態</th>
				<th class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted">予測に使用</th>
			</tr>
		</thead>
		<tbody>
			{#each survey.anomalies as a}
				{@const isInsufficient = a.status === 'insufficient_data' || a.n_observations < 52}
				<tr class="transition-colors hover:bg-surface-alt">
					<td class="border-b border-border px-3 py-2 text-text">
						{a.label || a.name}
						{#if a.note}
							<br /><small class="text-text-muted">{a.note}</small>
						{/if}
					</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{a.n_observations}</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{a.t_stat != null ? a.t_stat.toFixed(2) : '-'}</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{a.p_value != null ? a.p_value.toFixed(3) : '-'}</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{a.sharpe != null ? a.sharpe.toFixed(2) : '-'}</td>
					<td class="border-b border-border px-3 py-2 font-mono text-text">{isInsufficient ? 'データ収集中' : a.status}</td>
					<td class="border-b border-border px-3 py-2">
						{#if a.score_included}
							<span class="rounded bg-success/15 px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-success">使用中</span>
						{:else}
							<span class="rounded bg-text-muted/20 px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-text-muted">未使用</span>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{#if survey.as_of_utc}
	<p class="mt-2 text-[0.6875rem] text-text-muted">
		更新: {survey.as_of_utc.replace('T', ' ').slice(0, 16)} UTC
	</p>
{/if}
