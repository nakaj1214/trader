<script lang="ts">
</script>

<svelte:head>
	<title>AI Stock Predictions Dashboard</title>
</svelte:head>

<header>
	<div class="mx-auto flex max-w-5xl items-center justify-between gap-4">
		<div>
			<h1 class="font-display text-xl font-bold text-text">AI Stock Predictions</h1>
			<div class="text-sm text-text-muted">市場を選択してください</div>
		</div>
	</div>
</header>

<main class="mx-auto max-w-5xl p-5">
	<section class="py-12 text-center">
		<h2 class="mb-10 font-display text-xl font-bold text-text">投資市場を選択</h2>
		<div class="flex flex-wrap justify-center gap-6">
			<a
				href="/us"
				class="group relative flex w-60 flex-col items-center overflow-hidden rounded-[12px] border border-border bg-surface p-10 shadow transition-all duration-300 hover:-translate-y-0.5 hover:border-border-highlight hover:shadow-lg hover:shadow-glow"
			>
				<div
					class="pointer-events-none absolute inset-0 rounded-[12px] bg-[radial-gradient(circle_at_50%_30%,rgba(0,212,170,0.12)_0%,transparent_70%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
				></div>
				<div class="relative mb-4 text-6xl leading-none">🇺🇸</div>
				<div class="relative font-display text-xl font-bold">米国株</div>
				<div class="relative text-sm text-text-muted">S&P500 ・ NASDAQ100</div>
			</a>
			<a
				href="/jp"
				class="group relative flex w-60 flex-col items-center overflow-hidden rounded-[12px] border border-border bg-surface p-10 shadow transition-all duration-300 hover:-translate-y-0.5 hover:border-border-highlight hover:shadow-lg hover:shadow-glow"
			>
				<div
					class="pointer-events-none absolute inset-0 rounded-[12px] bg-[radial-gradient(circle_at_50%_30%,rgba(0,212,170,0.12)_0%,transparent_70%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
				></div>
				<div class="relative mb-4 text-6xl leading-none">🇯🇵</div>
				<div class="relative font-display text-xl font-bold">日本株</div>
				<div class="relative text-sm text-text-muted">日経225（データ収集中）</div>
			</a>
		</div>
	</section>
</main>
