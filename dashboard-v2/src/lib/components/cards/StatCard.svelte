<script lang="ts">
	let { value, label }: { value: string; label: string } = $props();
</script>

<div
	class="rounded-[12px] border border-border bg-surface p-7 text-center shadow"
>
	<div
		class="font-mono text-4xl font-bold text-primary [text-shadow:0_0_24px_rgba(0,212,170,0.25)]"
	>
		{value}
	</div>
	<div class="mt-1.5 text-[0.8125rem] text-text-muted">{label}</div>
</div>
