import type { Market } from '$lib/types/market';

const DATA_BASE = '/data/';

export function predictionsFile(market: Market): string {
	if (market === 'jp') return 'predictions_jp.json';
	return 'predictions_us.json';
}

export async function loadJSON<T>(filename: string): Promise<T> {
	const resp = await fetch(`${DATA_BASE}${filename}`);
	if (!resp.ok) {
		throw new Error(`Failed to load ${filename}: ${resp.status}`);
	}
	return resp.json() as Promise<T>;
}

export async function loadJSONSafe<T>(filename: string): Promise<T | null> {
	try {
		return await loadJSON<T>(filename);
	} catch {
		return null;
	}
}
