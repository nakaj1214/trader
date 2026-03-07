import type { Market } from '$lib/types/market';

export function formatPrice(price: number | null | undefined, market: Market = 'us'): string {
	if (price == null) return '-';
	if (market === 'jp') {
		return '\u00a5' + Math.round(Number(price)).toLocaleString('ja-JP');
	}
	return '$' + Number(price).toFixed(2);
}

export function formatPct(pct: number | null | undefined): string {
	if (pct == null) return '-';
	return (pct >= 0 ? '+' : '') + Number(pct).toFixed(1) + '%';
}

export function formatDate(dateStr: string | null | undefined): string {
	if (!dateStr) return '-';
	return dateStr;
}

export function hitLabel(hit: string): { text: string; type: 'hit' | 'miss' | 'pending' } {
	if (hit === '的中') return { text: '当たり', type: 'hit' };
	if (hit === '外れ') return { text: 'はずれ', type: 'miss' };
	return { text: '結果待ち', type: 'pending' };
}

export function formatUnitInfo(price: number | null | undefined): string | null {
	if (!price) return null;
	const minInvestment = Math.round(Number(price)) * 100;
	return '1単元(100株)の最低投資額: \u00a5' + minInvestment.toLocaleString('ja-JP');
}
