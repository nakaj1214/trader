const STALE_THRESHOLD_DAYS = 10;

export function checkStaleness(updatedAt: string): { isStale: boolean; daysSinceUpdate: number } {
	const updatedDate = new Date(updatedAt);
	const now = new Date();
	const diffDays = (now.getTime() - updatedDate.getTime()) / (1000 * 60 * 60 * 24);
	return {
		isStale: diffDays > STALE_THRESHOLD_DAYS,
		daysSinceUpdate: Math.floor(diffDays)
	};
}
