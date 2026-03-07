import { isValidMarket } from '$lib/types/market';
import { error } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = ({ params }) => {
	if (!isValidMarket(params.market)) {
		error(404, 'Invalid market');
	}
	return { market: params.market };
};
