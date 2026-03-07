<script lang="ts">
	import { onMount } from 'svelte';
	import type { Market } from '$lib/types/market';
	import type {
		AccuracyData,
		PredictionsData,
		ComparisonData,
		AlphaSurveyData
	} from '$lib/types/prediction';
	import { loadJSON, loadJSONSafe, predictionsFile } from '$lib/data/loader';
	import { filterPredictions } from '$lib/utils/filter';
	import { formatPct } from '$lib/utils/format';
	import StatCard from '$lib/components/cards/StatCard.svelte';
	import WeeklyChart from '$lib/components/charts/WeeklyChart.svelte';
	import ErrorChart from '$lib/components/charts/ErrorChart.svelte';
	import CalibrationChart from '$lib/components/charts/CalibrationChart.svelte';
	import ComparisonChart from '$lib/components/charts/ComparisonChart.svelte';
	import CalibrationStats from '$lib/components/accuracy/CalibrationStats.svelte';
	import BacktestHygiene from '$lib/components/accuracy/BacktestHygiene.svelte';
	import CollapsibleSection from '$lib/components/accuracy/CollapsibleSection.svelte';
	import TickerRanking from '$lib/components/tables/TickerRanking.svelte';
	import ComparisonTable from '$lib/components/tables/ComparisonTable.svelte';
	import ErrorTable from '$lib/components/tables/ErrorTable.svelte';
	import AlphaSurveyTable from '$lib/components/tables/AlphaSurveyTable.svelte';

	let { data } = $props();
	const market: Market = data.market;

	let accuracy = $state<AccuracyData | null>(null);
	let predictions = $state<PredictionsData | null>(null);
	let comparison = $state<ComparisonData | null>(null);
	let alphaSurvey = $state<AlphaSurveyData | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const [acc, pred, comp, alpha] = await Promise.all([
				loadJSON<AccuracyData>('accuracy.json'),
				loadJSON<PredictionsData>(predictionsFile(market)),
				loadJSONSafe<ComparisonData>('comparison.json'),
				loadJSONSafe<AlphaSurveyData>('alpha_survey.json')
			]);
			accuracy = acc;
			predictions = pred;
			comparison = comp;
			alphaSurvey = alpha;
		} catch (e) {
			error = 'データを読み込めませんでした。';
		}
	});

	const filtered = $derived(predictions ? filterPredictions(predictions.predictions) : []);
	const showCalibration = $derived(
		accuracy?.calibration?.overall?.n_calibrated != null &&
			accuracy.calibration.overall.n_calibrated >= 30
	);
	const showComparison = $derived(
		comparison?.strategies != null && Object.keys(comparison.strategies).length > 0
	);
	const showHygiene = $derived(comparison?.backtest_hygiene != null);
	const showAlpha = $derived(
		alphaSurvey?.anomalies != null && alphaSurvey.anomalies.length > 0
	);
	const hasErrorAnalysis = $derived(accuracy?.error_analysis?.mae_pct != null);
</script>

<svelte:head>
	<title>成績 - {market === 'jp' ? '日本株' : '米国株'} AI Stock Predictions</title>
</svelte:head>

{#if error}
	<div class="py-12 text-center text-sm text-text-muted">{error}</div>
{:else if accuracy}
	<!-- Cumulative stat -->
	<section class="mb-7">
		<StatCard
			value="{accuracy.cumulative.hit_rate_pct.toFixed(1)}%"
			label="{accuracy.cumulative.hits}/{accuracy.cumulative.total} 当たり"
		/>
	</section>

	<!-- Weekly chart -->
	<section class="mb-7">
		<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">
			週ごとの的中率
		</h2>
		<WeeklyChart weekly={accuracy.weekly} />
	</section>

	<!-- Error analysis -->
	{#if hasErrorAnalysis}
		<section class="mb-7">
			<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">
				予測誤差分析
			</h2>
			<div class="mb-4 rounded-[12px] border border-border bg-surface p-7 text-center shadow">
				<div class="font-mono text-4xl font-bold text-primary [text-shadow:0_0_24px_rgba(0,212,170,0.25)]">
					{accuracy.error_analysis.mae_pct?.toFixed(1)}%
				</div>
				<div class="mt-1.5 text-[0.8125rem] text-text-muted">平均誤差 (MAE)</div>
			</div>
			<ErrorChart bins={accuracy.error_analysis.bins} />
			<ErrorTable bins={accuracy.error_analysis.bins} />
		</section>
	{/if}

	<!-- Calibration -->
	{#if showCalibration}
		<CollapsibleSection title="確率予測の信頼度（校正）">
			<CalibrationStats
				overall={accuracy.calibration.overall}
				recent={accuracy.calibration.recent_n_weeks}
			/>
			<CalibrationChart calibration={accuracy.calibration.overall} />
			<p class="mt-3 text-center text-xs text-text-muted">
				件数30以上で表示されます。棒グラフ（実際）と折れ線（予測）が近いほど精度が高いです。
			</p>
		</CollapsibleSection>
	{/if}

	<!-- Backtest Hygiene -->
	{#if showHygiene && comparison?.backtest_hygiene}
		<CollapsibleSection title="バックテスト品質">
			<BacktestHygiene hygiene={comparison.backtest_hygiene} />
		</CollapsibleSection>
	{/if}

	<!-- Comparison -->
	{#if showComparison && comparison}
		<section class="mb-7">
			<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">
				投資手法の比較
			</h2>
			<p class="mb-3 text-xs italic text-text-muted">
				AI予測に基づく投資戦略と他の手法を比較します。
			</p>
			<ComparisonChart strategies={comparison.strategies} />
			<ComparisonTable strategies={comparison.strategies} />
		</section>
	{/if}

	<!-- Ticker ranking -->
	<section class="mb-7">
		<h2 class="mb-3.5 font-display text-[1.0625rem] font-semibold tracking-tight text-text">
			銘柄別ランキング
		</h2>
		<TickerRanking predictions={filtered} {market} />
	</section>

	<!-- Alpha survey -->
	{#if showAlpha && alphaSurvey}
		<CollapsibleSection title="市場パターン検証（アルファサーベイ）">
			<AlphaSurveyTable survey={alphaSurvey} />
		</CollapsibleSection>
	{/if}
{:else}
	<div class="py-10 text-center text-sm text-text-muted">読み込み中...</div>
{/if}
