<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<svelte:head>
	<title>AI Stock Predictions Dashboard</title>
</svelte:head>

{@render children()}
