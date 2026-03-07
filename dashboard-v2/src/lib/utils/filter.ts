import type { Prediction } from '$lib/types/prediction';

export function isTestTicker(ticker: string): boolean {
	return ticker === 'E2E_TEST';
}

export function filterPredictions(predictions: Prediction[]): Prediction[] {
	return predictions.filter((p) => !isTestTicker(p.ticker));
}

export function getLatestWeekDate(predictions: Prediction[]): string | null {
	if (predictions.length === 0) return null;
	const dates = predictions.map((p) => p.date);
	return dates.sort().reverse()[0];
}

export function deduplicateByTicker(predictions: Prediction[]): Prediction[] {
	const tickerMap = new Map<string, Prediction>();
	for (const p of predictions) {
		const existing = tickerMap.get(p.ticker);
		if (!existing || p.status === '予測済み') {
			tickerMap.set(p.ticker, p);
		}
	}
	return Array.from(tickerMap.values()).sort((a, b) => {
		const av = a.predicted_change_pct_clipped ?? a.predicted_change_pct;
		const bv = b.predicted_change_pct_clipped ?? b.predicted_change_pct;
		return bv - av;
	});
}
