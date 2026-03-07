<script lang="ts">
	import { checkStaleness } from '$lib/utils/staleness';

	let { updatedAt }: { updatedAt: string | null } = $props();

	const staleness = $derived(updatedAt ? checkStaleness(updatedAt) : null);
</script>

{#if staleness?.isStale}
	<div
		class="mb-4 rounded-sm border border-warning/25 bg-warning/10 px-4 py-3 text-sm text-warning"
	>
		⚠ データが {staleness.daysSinceUpdate} 日間更新されていません。
	</div>
{/if}
