<script lang="ts">
	let { open = $bindable(false) } = $props();

	function close() {
		open = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') close();
	}

	function handleOverlayClick(e: MouseEvent) {
		if (e.target === e.currentTarget) close();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
		onclick={handleOverlayClick}
		role="dialog"
		aria-modal="true"
		aria-labelledby="help-modal-title"
	>
		<div
			class="flex max-h-[82vh] w-full max-w-[680px] flex-col rounded-[12px] border border-border bg-surface shadow-lg"
		>
			<div
				class="flex flex-shrink-0 items-center justify-between border-b border-border px-5 py-4"
			>
				<h2 id="help-modal-title" class="font-display text-base font-semibold">使い方ガイド</h2>
				<button
					class="rounded px-2 py-1 text-xl leading-none text-text-muted transition-all hover:bg-surface-alt hover:text-text"
					onclick={close}
					aria-label="閉じる"
				>
					&#x2715;
				</button>
			</div>

			<div class="flex-1 overflow-y-auto px-5 py-5">
				<h3
					class="mb-2 border-b border-border pb-1 font-display text-sm font-semibold text-primary"
				>
					このダッシュボードの使い方
				</h3>
				<p class="mb-1 text-[0.8125rem] leading-relaxed text-text">
					AIが「来週上がりそうな株」を毎週予測します。このサイトでは、その予測結果と過去の成績を確認できます。
				</p>

				<h3
					class="mb-2 mt-5 border-b border-border pb-1 font-display text-sm font-semibold text-primary"
				>
					各ページの説明
				</h3>
				<ul class="mb-2 list-disc pl-5 text-[0.8125rem] leading-relaxed text-text">
					<li><strong>サマリー</strong>: 今週の予測一覧。「買い候補」「様子見」がひと目でわかります</li>
					<li><strong>成績</strong>: 過去の予測がどれくらい当たったかの記録</li>
					<li><strong>銘柄詳細</strong>: 個別の株の予測履歴・株価チャート</li>
				</ul>

				<h3
					class="mb-2 mt-5 border-b border-border pb-1 font-display text-sm font-semibold text-primary"
				>
					カードの見方
				</h3>
				<ul class="mb-2 list-disc pl-5 text-[0.8125rem] leading-relaxed text-text">
					<li><strong>現在価格 → 予測価格</strong>: 今の株価と、来週AIが予測した株価</li>
					<li><strong>予測上昇率</strong>: 来週どれくらい上がる（下がる）と予測しているか</li>
					<li><strong>当たり / はずれ</strong>: 過去の予測が実際に当たったかどうか</li>
					<li><strong>値動き ○%</strong>: この株がどれくらい激しく動くか（大きいほどリスクが高い）</li>
					<li><strong>最大下落 ○%</strong>: 過去1年で最も大きく下がった幅</li>
				</ul>

				<h3
					class="mb-2 mt-5 border-b border-border pb-1 font-display text-sm font-semibold text-primary"
				>
					注意マークについて
				</h3>
				<ul class="mb-2 list-disc pl-5 text-[0.8125rem] leading-relaxed text-text">
					<li>
						<span
							class="mr-1 inline-block rounded bg-warning/10 px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-warning"
							>⚠ 注意</span
						> 予測の変動が大きく、精度が低い可能性があります
					</li>
					<li>
						<span
							class="mr-1 inline-block rounded bg-danger/10 px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-danger"
							>⚠ 不安定</span
						> 予測が極端すぎるため、表示値を調整しています
					</li>
				</ul>

				<p class="mt-1 text-xs italic text-text-muted">
					※ このシステムは投資判断の参考情報です。予測は将来の利益を保証しません。
				</p>
			</div>

			<div class="flex flex-shrink-0 justify-end border-t border-border px-5 py-3">
				<button
					class="rounded-sm bg-primary px-6 py-2 font-display text-[0.8125rem] font-semibold text-bg transition-all hover:bg-primary-strong hover:shadow-[0_0_12px_rgba(0,212,170,0.3)]"
					onclick={close}
				>
					閉じる
				</button>
			</div>
		</div>
	</div>
{/if}
