export type Market = 'us' | 'jp';

export const VALID_MARKETS: Market[] = ['us', 'jp'];

export function isValidMarket(value: string): value is Market {
	return VALID_MARKETS.includes(value as Market);
}
