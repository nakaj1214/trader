<script lang="ts">
	import Header from '$lib/components/layout/Header.svelte';
	import StaleAlert from '$lib/components/layout/StaleAlert.svelte';
	import type { Market } from '$lib/types/market';
	import type { AccuracyData } from '$lib/types/prediction';
	import { loadJSONSafe } from '$lib/data/loader';
	import { onMount } from 'svelte';

	let { data, children } = $props();
	const market: Market = data.market;

	let accuracy = $state<AccuracyData | null>(null);

	onMount(async () => {
		accuracy = await loadJSONSafe<AccuracyData>('accuracy.json');
	});
</script>

<Header {market} {accuracy} />

<main class="mx-auto max-w-5xl p-5">
	<StaleAlert updatedAt={accuracy?.updated_at ?? null} />
	{@render children()}
</main>
