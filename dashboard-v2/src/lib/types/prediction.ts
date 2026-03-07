export interface Prediction {
	date: string;
	ticker: string;
	current_price: number;
	predicted_price: number;
	predicted_change_pct: number;
	predicted_change_pct_clipped: number | null;
	ci_pct: number;
	actual_price: number | null;
	status: string;
	hit: string;
	sanity_flags: string[];
	prob_up: number | null;
	prob_up_calibrated: number | null;
	risk?: RiskInfo;
	sizing?: SizingInfo;
	events?: EventInfo[];
	evidence?: EvidenceInfo;
	explanations?: ExplanationsInfo;
	short_interest?: ShortInterestInfo;
	institutional?: InstitutionalInfo;
	jp_listed_info?: JpListedInfo;
	jp_fundamentals?: JpFundamentals;
}

export interface RiskInfo {
	vol_20d_ann: number;
	max_drawdown_1y: number;
}

export interface SizingInfo {
	max_position_weight: number | null;
	stop_loss_pct: number | null;
	stop_loss_rationale?: string;
}

export interface EventInfo {
	type: 'earnings' | 'dividend';
	days_to: number;
}

export interface EvidenceInfo {
	momentum_z: number | null;
	value_z: number | null;
	quality_z: number | null;
	low_risk_z: number | null;
	composite: number | null;
}

export interface ExplanationsInfo {
	factors: Array<{ text: string; impact: number }>;
	note: string;
}

export interface ShortInterestInfo {
	short_ratio: number | null;
	short_pct_float: number | null;
	signal: string;
	data_note?: string;
}

export interface InstitutionalInfo {
	institutional_pct: number | null;
	top5_holders: string[];
	data_note?: string;
}

export interface JpListedInfo {
	sector_17?: string;
	market_section?: string;
}

export interface JpFundamentals {
	eps?: number;
	forecast_eps?: number;
	dividend_annual?: number;
	payout_ratio?: number;
	operating_margin?: number;
}

export interface PredictionsData {
	as_of_utc: string;
	data_coverage_weeks: number;
	predictions: Prediction[];
}

export interface AccuracyData {
	updated_at: string;
	as_of_utc: string;
	data_coverage_weeks: number;
	cumulative: { hit_rate_pct: number; hits: number; total: number };
	weekly: WeeklyStat[];
	error_analysis: ErrorAnalysis;
	calibration: CalibrationData;
}

export interface WeeklyStat {
	date: string;
	hit_rate_pct: number;
	hits: number;
	total: number;
}

export interface ErrorAnalysis {
	mae_pct: number | null;
	bins: ErrorBin[];
	notes: string;
}

export interface ErrorBin {
	range: string;
	avg_predicted_pct: number;
	avg_actual_pct: number;
	hit_rate_pct: number;
	count: number;
}

export interface CalibrationData {
	overall: CalibrationGroup;
	recent_n_weeks: CalibrationGroup & { n_weeks?: number };
}

export interface CalibrationGroup {
	brier_score: number | null;
	log_loss: number | null;
	ece: number | null;
	n_calibrated: number;
	reliability_bins: ReliabilityBin[];
}

export interface ReliabilityBin {
	p_bin: string;
	empirical: number;
	mean_pred: number;
	n: number;
}

export interface ComparisonData {
	updated_at: string;
	strategies: Record<string, StrategyInfo>;
	backtest_hygiene?: BacktestHygiene;
}

export interface StrategyInfo {
	label: string;
	cagr: number | null;
	max_drawdown: number | null;
	sharpe: number | null;
	equity_curve: Array<{ date: string; equity: number }>;
}

export interface BacktestHygiene {
	hygiene_status: string;
	num_rules_tested: number | null;
	num_parameters_tuned: number | null;
	oos_start: string | null;
	data_coverage_weeks: number | null;
	reality_check_pvalue: number | null;
	pbo: number | null;
	deflated_sharpe: number | null;
	transaction_cost_note: string;
	survivorship_bias_note: string;
	hygiene_note?: string;
}

export interface StockHistory {
	[ticker: string]: Array<{
		date: string;
		predicted_price: number;
		actual_price?: number | null;
	}>;
}

export interface MacroData {
	as_of_utc: string;
	data_as_of_utc?: string;
	series: Record<string, { latest_value: number; unit: string }>;
	regime: { is_risk_off: boolean; note?: string };
}

export interface AlphaSurveyData {
	as_of_utc: string;
	anomalies: AnomalyResult[];
}

export interface AnomalyResult {
	name: string;
	label: string;
	n_observations: number;
	t_stat: number | null;
	p_value: number | null;
	sharpe: number | null;
	status: string;
	score_included: boolean;
	note?: string;
}
