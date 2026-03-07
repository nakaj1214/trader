<script lang="ts">
	import type { CalibrationGroup } from '$lib/types/prediction';

	let { overall, recent }: { overall: CalibrationGroup; recent: CalibrationGroup & { n_weeks?: number } } = $props();

	function fmt(v: number | null, decimals = 4): string {
		return v != null ? v.toFixed(decimals) : '-';
	}
</script>

<div class="mb-4 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3.5">
	<!-- Overall -->
	<div class="rounded-[12px] border border-border bg-surface p-4 shadow">
		<h3
			class="mb-3 font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
		>
			全期間
		</h3>
		<div class="mb-1 flex justify-between text-[0.8125rem]">
			<span class="text-text-muted">予測の正確さ（低いほど良い）</span>
			<span class="font-mono font-semibold text-text">{fmt(overall.brier_score)}</span>
		</div>
		<div class="mb-1 flex justify-between text-[0.8125rem]">
			<span class="text-text-muted">確率予測の精度（低いほど良い）</span>
			<span class="font-mono font-semibold text-text">{fmt(overall.log_loss)}</span>
		</div>
		<div class="mb-1 flex justify-between text-[0.8125rem]">
			<span class="text-text-muted">確率のズレ（0に近いほど良い）</span>
			<span class="font-mono font-semibold text-text">{fmt(overall.ece)}</span>
		</div>
		<div class="flex justify-between text-[0.8125rem]">
			<span class="text-text-muted">件数</span>
			<span class="font-mono font-semibold text-text">{overall.n_calibrated}</span>
		</div>
	</div>

	<!-- Recent -->
	{#if recent}
		<div class="rounded-[12px] border border-border bg-surface p-4 shadow">
			<h3
				class="mb-3 font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
			>
				直近 {recent.n_weeks ?? 12} 週
			</h3>
			<div class="mb-1 flex justify-between text-[0.8125rem]">
				<span class="text-text-muted">予測の正確さ</span>
				<span class="font-mono font-semibold text-text">{fmt(recent.brier_score)}</span>
			</div>
			<div class="mb-1 flex justify-between text-[0.8125rem]">
				<span class="text-text-muted">確率予測の精度</span>
				<span class="font-mono font-semibold text-text">{fmt(recent.log_loss)}</span>
			</div>
			<div class="mb-1 flex justify-between text-[0.8125rem]">
				<span class="text-text-muted">確率のズレ</span>
				<span class="font-mono font-semibold text-text">{fmt(recent.ece)}</span>
			</div>
			<div class="flex justify-between text-[0.8125rem]">
				<span class="text-text-muted">件数</span>
				<span class="font-mono font-semibold text-text">{recent.n_calibrated}</span>
			</div>
		</div>
	{/if}
</div>
