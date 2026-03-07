<script lang="ts">
	import type { Snippet } from 'svelte';
	let { title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: Snippet } = $props();

	let open = $state(defaultOpen);
</script>

<section class="mb-7">
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<h2
		class="mb-3.5 flex cursor-pointer select-none items-center gap-2 font-display text-[1.0625rem] font-semibold tracking-tight text-text transition-colors hover:text-primary"
		onclick={() => (open = !open)}
	>
		{title}
		<span
			class="text-[0.625rem] text-text-muted transition-transform duration-200"
			class:rotate-90={open}
		>
			&#x25B6;
		</span>
	</h2>
	{#if open}
		<div class="animate-[fadeIn_0.2s_ease]">
			{@render children()}
		</div>
	{/if}
</section>
