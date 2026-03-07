<script lang="ts">
	import type { BacktestHygiene as HygieneType } from '$lib/types/prediction';

	let { hygiene }: { hygiene: HygieneType } = $props();

	const STATUS_LABELS: Record<string, string> = {
		insufficient_trials: 'データ収集中',
		computed: '検証済み',
		partial: '一部検証済み'
	};

	const statusClass: Record<string, string> = {
		insufficient_trials: 'bg-warning/10 text-warning',
		computed: 'bg-success/10 text-success',
		partial: 'bg-primary/10 text-primary'
	};

	function fmt(v: unknown): string {
		return v != null ? String(v) : '-';
	}
</script>

<div class="rounded-[12px] border border-border bg-surface p-[1.125rem] shadow">
	<div
		class="mb-3 inline-block rounded-full px-3 py-1 font-mono text-xs font-semibold {statusClass[hygiene.hygiene_status] ?? ''}"
	>
		ステータス: {STATUS_LABELS[hygiene.hygiene_status] ?? hygiene.hygiene_status}
	</div>

	<div class="mb-3 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-x-4 gap-y-1">
		{#each [
			['テストした予測ルール数', fmt(hygiene.num_rules_tested)],
			['調整した設定数', fmt(hygiene.num_parameters_tuned)],
			['テスト開始日', fmt(hygiene.oos_start)],
			['検証した週数', `${fmt(hygiene.data_coverage_weeks)} 週`],
			['統計的な信頼度', fmt(hygiene.reality_check_pvalue)],
			['過学習リスク', fmt(hygiene.pbo)],
			['調整済み効率', fmt(hygiene.deflated_sharpe)]
		] as [label, value]}
			<div class="flex justify-between border-b border-border py-1 text-[0.8125rem]">
				<span class="text-text-muted">{label}</span>
				<span class="font-mono font-semibold text-text">{value}</span>
			</div>
		{/each}
	</div>

	<p class="mt-2 text-xs leading-relaxed text-text-muted">
		{hygiene.transaction_cost_note}<br />{hygiene.survivorship_bias_note}
	</p>
	{#if hygiene.hygiene_note}
		<p class="mt-1 text-xs italic text-warning">{hygiene.hygiene_note}</p>
	{/if}
</div>
