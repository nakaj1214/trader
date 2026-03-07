<script lang="ts">
	import { onMount } from 'svelte';
	import type { PredictionsData } from '$lib/types/prediction';
	import { loadJSON } from '$lib/data/loader';
	import { isTestTicker } from '$lib/utils/filter';
	import { formatPrice } from '$lib/utils/format';
	import SimChart from '$lib/components/charts/SimChart.svelte';

	interface WeeklyResult {
		date: string;
		pnl: number;
		cumPnl: number;
	}

	interface TickerPnlRow {
		ticker: string;
		pnl: number;
		pct: number;
		count: number;
	}

	let predictions = $state<PredictionsData['predictions']>([]);
	let amount = $state(10000);
	let error = $state<string | null>(null);
	let simError = $state(false);
	let loading = $state(true);

	let weeklyResults = $state<WeeklyResult[]>([]);
	let tickerRows = $state<TickerPnlRow[]>([]);
	let totalPnl = $state(0);
	let totalReturnPct = $state(0);
	let weekCount = $state(0);

	onMount(async () => {
		try {
			const data = await loadJSON<PredictionsData>('predictions.json');
			predictions = data.predictions ?? [];
			runSimulation();
		} catch {
			error = 'データを読み込めませんでした。';
		} finally {
			loading = false;
		}
	});

	function runSimulation() {
		if (typeof amount !== 'number' || !isFinite(amount) || amount <= 0) {
			simError = true;
			weeklyResults = [];
			return;
		}
		simError = false;

		const valid = predictions.filter(
			(p) => p.actual_price != null && p.current_price > 0 && !isTestTicker(p.ticker)
		);

		const weekMap: Record<string, typeof valid> = {};
		for (const p of valid) {
			if (!weekMap[p.date]) weekMap[p.date] = [];
			weekMap[p.date].push(p);
		}

		const weeks = Object.keys(weekMap).sort();
		if (weeks.length === 0) {
			weeklyResults = [];
			tickerRows = [];
			totalPnl = 0;
			totalReturnPct = 0;
			weekCount = 0;
			return;
		}

		const results: WeeklyResult[] = [];
		const pnlMap: Record<string, { pnl: number; count: number }> = {};
		let cumPnl = 0;

		for (const date of weeks) {
			const items = weekMap[date];
			const perStock = amount / items.length;
			let weekPnl = 0;

			for (const p of items) {
				const pnl = (perStock * ((p.actual_price ?? 0) - p.current_price)) / p.current_price;
				weekPnl += pnl;

				if (!pnlMap[p.ticker]) pnlMap[p.ticker] = { pnl: 0, count: 0 };
				pnlMap[p.ticker].pnl += pnl;
				pnlMap[p.ticker].count++;
			}

			cumPnl += weekPnl;
			results.push({ date, pnl: weekPnl, cumPnl });
		}

		weeklyResults = results;
		totalPnl = cumPnl;
		totalReturnPct = (cumPnl / amount) * 100;
		weekCount = weeks.length;

		tickerRows = Object.entries(pnlMap)
			.map(([ticker, t]) => ({
				ticker,
				pnl: t.pnl,
				pct: (t.pnl / amount) * 100,
				count: t.count
			}))
			.sort((a, b) => b.pnl - a.pnl);
	}

	const pnlClass = $derived(totalPnl >= 0 ? 'text-success' : 'text-danger');
	const pnlSign = $derived(totalPnl >= 0 ? '+' : '');
	const retSign = $derived(totalReturnPct >= 0 ? '+' : '');
</script>

<svelte:head>
	<title>投資シミュレータ - AI Stock Predictions</title>
</svelte:head>

<div class="mx-auto max-w-4xl px-4 py-8">
	<h1 class="mb-6 font-display text-2xl font-bold text-text">投資シミュレータ</h1>
	<p class="mb-6 text-sm text-text-muted">
		AIの予測に従って毎週投資した場合の損益をシミュレーションします。
	</p>

	{#if error}
		<div class="py-12 text-center text-sm text-text-muted">{error}</div>
	{:else if loading}
		<div class="py-10 text-center text-sm text-text-muted">読み込み中...</div>
	{:else}
		<!-- Input -->
		<div class="mb-6 flex items-end gap-4">
			<div>
				<label for="sim-amount" class="mb-1 block text-sm font-medium text-text-muted">
					週あたりの投資金額 ($)
				</label>
				<input
					id="sim-amount"
					type="number"
					bind:value={amount}
					min="1"
					class="w-40 rounded-lg border border-border bg-surface px-3 py-2 font-mono text-text focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				/>
			</div>
			<button
				onclick={runSimulation}
				class="rounded-lg bg-primary px-5 py-2 font-semibold text-bg transition-colors hover:bg-primary/80"
			>
				シミュレーション実行
			</button>
		</div>

		{#if simError}
			<div class="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
				有効な金額を入力してください。
			</div>
		{/if}

		{#if weeklyResults.length > 0}
			<!-- Summary cards -->
			<div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class="rounded-[12px] border border-border bg-surface p-4 text-center shadow">
					<div class="font-mono text-xl font-bold text-text">
						{formatPrice(amount, 'us')}
					</div>
					<div class="mt-1 text-xs text-text-muted">投資金額</div>
				</div>
				<div class="rounded-[12px] border border-border bg-surface p-4 text-center shadow">
					<div class="font-mono text-xl font-bold {pnlClass}">
						{pnlSign}{formatPrice(Math.abs(totalPnl), 'us')}
					</div>
					<div class="mt-1 text-xs text-text-muted">累計損益</div>
				</div>
				<div class="rounded-[12px] border border-border bg-surface p-4 text-center shadow">
					<div class="font-mono text-xl font-bold {pnlClass}">
						{retSign}{totalReturnPct.toFixed(1)}%
					</div>
					<div class="mt-1 text-xs text-text-muted">累計損益率</div>
				</div>
				<div class="rounded-[12px] border border-border bg-surface p-4 text-center shadow">
					<div class="font-mono text-xl font-bold text-text">
						{weekCount}週
					</div>
					<div class="mt-1 text-xs text-text-muted">対象期間</div>
				</div>
			</div>

			<!-- Chart -->
			<section class="mb-7">
				<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">
					週次損益チャート
				</h2>
				{#key weeklyResults}
					<SimChart {weeklyResults} />
				{/key}
			</section>

			<!-- Ticker P&L Table -->
			<section class="mb-7">
				<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">
					銘柄別損益
				</h2>
				<div class="overflow-x-auto">
					<table
						class="w-full border-collapse overflow-hidden rounded-[12px] border border-border bg-surface text-[0.8125rem]"
					>
						<thead class="bg-surface-alt">
							<tr>
								<th
									class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
								>
									ティッカー
								</th>
								<th
									class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
								>
									損益 ($)
								</th>
								<th
									class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
								>
									損益率
								</th>
								<th
									class="px-3 py-2 text-left font-display text-[0.6875rem] font-semibold uppercase tracking-wider text-text-muted"
								>
									回数
								</th>
							</tr>
						</thead>
						<tbody>
							{#each tickerRows as row}
								{@const rowPnlClass = row.pnl >= 0 ? 'text-success' : 'text-danger'}
								{@const rowSign = row.pnl >= 0 ? '+' : ''}
								<tr class="transition-colors hover:bg-surface-alt">
									<td class="border-b border-border px-3 py-2 font-mono text-primary">
										{row.ticker}
									</td>
									<td class="border-b border-border px-3 py-2 font-mono {rowPnlClass}">
										{rowSign}${Math.abs(row.pnl).toFixed(2)}
									</td>
									<td class="border-b border-border px-3 py-2 font-mono {rowPnlClass}">
										{rowSign}{row.pct.toFixed(1)}%
									</td>
									<td class="border-b border-border px-3 py-2 font-mono text-text">
										{row.count}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{:else if !simError}
			<div class="py-12 text-center text-sm text-text-muted">
				シミュレーション対象のデータがありません。
			</div>
		{/if}
	{/if}
</div>
