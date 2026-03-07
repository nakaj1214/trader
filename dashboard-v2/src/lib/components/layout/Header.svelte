<script lang="ts">
	import type { Market } from '$lib/types/market';
	import type { AccuracyData } from '$lib/types/prediction';
	import HelpModal from './HelpModal.svelte';

	let { market, accuracy = null }: { market: Market; accuracy: AccuracyData | null } = $props();

	let helpOpen = $state(false);

	const marketLabel = $derived(market === 'jp' ? '🇯🇵 日本株' : '🇺🇸 米国株');
	const hitRate = $derived(accuracy?.cumulative?.hit_rate_pct?.toFixed(1) ?? '-');
	const hitDetail = $derived(
		accuracy?.cumulative
			? `${accuracy.cumulative.hits}/${accuracy.cumulative.total} 当たり`
			: '予測の当たった割合'
	);
	const lastUpdated = $derived(
		accuracy?.updated_at
			? '最終更新: ' + new Date(accuracy.updated_at).toLocaleString('ja-JP')
			: ''
	);

	const currentPath = $derived(typeof window !== 'undefined' ? window.location.pathname : '');
	const isActive = (path: string) => currentPath === path;
</script>

<header>
	<div class="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4">
		<div>
			<h1 class="font-display text-xl font-bold text-text">
				AI Stock Predictions <span class="ml-2 font-mono text-sm font-medium text-text-muted"
					>{marketLabel}</span
				>
			</h1>
			{#if lastUpdated}
				<div class="font-mono text-xs text-text-muted">{lastUpdated}</div>
			{/if}
		</div>
		<div class="flex items-center gap-6">
			<div class="text-center">
				<div
					class="font-mono text-3xl font-bold text-primary [text-shadow:0_0_16px_rgba(0,212,170,0.3)]"
				>
					{hitRate}%
				</div>
				<div class="text-[0.6875rem] uppercase tracking-wider text-text-muted">{hitDetail}</div>
			</div>
			<nav class="flex gap-1">
				<a
					href="/{market}"
					class="rounded-sm border border-transparent px-3.5 py-1.5 font-body text-[0.8125rem] font-medium text-text-muted transition-all hover:border-border hover:bg-surface-alt hover:text-text"
					class:active-nav={isActive(`/${market}`)}
				>
					サマリー
				</a>
				<a
					href="/{market}/accuracy"
					class="rounded-sm border border-transparent px-3.5 py-1.5 font-body text-[0.8125rem] font-medium text-text-muted transition-all hover:border-border hover:bg-surface-alt hover:text-text"
					class:active-nav={isActive(`/${market}/accuracy`)}
				>
					成績
				</a>
				{#if market === 'us'}
					<a
						href="/simulator"
						class="rounded-sm border border-transparent px-3.5 py-1.5 font-body text-[0.8125rem] font-medium text-text-muted transition-all hover:border-border hover:bg-surface-alt hover:text-text"
					>
						シミュレータ
					</a>
				{/if}
				<a
					href="/"
					class="rounded-sm border border-transparent px-3.5 py-1.5 font-body text-[0.8125rem] font-medium text-text-muted transition-all hover:border-border hover:bg-surface-alt hover:text-text"
				>
					← 市場選択
				</a>
			</nav>
			<button
				class="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border-[1.5px] border-border text-[0.8125rem] font-bold text-text-muted transition-all hover:border-primary hover:text-primary hover:shadow-[0_0_12px_rgba(0,212,170,0.12)]"
				onclick={() => (helpOpen = true)}
				title="ヘルプを表示"
			>
				?
			</button>
		</div>
	</div>
</header>

<HelpModal bind:open={helpOpen} />

<style>
	.active-nav {
		background: rgba(0, 212, 170, 0.12);
		color: #00d4aa;
		border-color: rgba(0, 212, 170, 0.25);
	}
</style>
