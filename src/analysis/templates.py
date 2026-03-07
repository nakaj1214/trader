"""Prompt templates for 12 financial analysis types.

Each template consists of a system prompt (role) and a user prompt
(analysis instructions with data placeholders).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisTemplate:
    """A financial analysis prompt template."""

    name: str
    system_prompt: str
    user_prompt: str


DISCLAIMER = (
    "\n\n---\n"
    "DISCLAIMER: This analysis is AI-generated and is NOT investment advice. "
    "All projections are based on provided data and assumptions that may not "
    "reflect actual market conditions. Consult a qualified financial advisor "
    "before making investment decisions."
)

DCF = AnalysisTemplate(
    name="dcf",
    system_prompt=(
        "You are a Senior Analyst at Goldman Sachs specializing in DCF valuations. "
        "Provide rigorous, data-driven analysis based on the financial data provided. "
        "Use the actual data given — do not fabricate numbers."
    ),
    user_prompt=(
        "Perform a complete DCF (Discounted Cash Flow) valuation for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Free Cash Flow Projections\n"
        "Next 5 years with growth assumptions based on historical data.\n\n"
        "## WACC\n"
        "Cost of equity + cost of debt breakdown with justification.\n\n"
        "## Terminal Value\n"
        "Both perpetuity growth method and exit multiple method.\n\n"
        "## Sensitivity Analysis\n"
        "How value changes with different WACC and growth assumptions.\n\n"
        "## Valuation Range\n"
        "Bull case, base case, and bear case scenarios with implied share price."
        + DISCLAIMER
    ),
)

THREE_STATEMENT = AnalysisTemplate(
    name="financial_statement",
    system_prompt=(
        "You are a VP at Morgan Stanley specializing in financial modeling. "
        "Build models based strictly on provided financial data."
    ),
    user_prompt=(
        "Build a complete three-statement financial model for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Income Statement\n"
        "Revenue, costs, EBITDA, net income projections (5 years).\n\n"
        "## Balance Sheet\n"
        "Assets, liabilities, equity projections (5 years).\n\n"
        "## Cash Flow Statement\n"
        "Operating, investing, financing activities (5 years).\n\n"
        "## Key Assumptions\n"
        "Revenue growth, margins, capex as % of sales.\n\n"
        "## Link Formulas\n"
        "How the three statements connect."
        + DISCLAIMER
    ),
)

MA_ANALYSIS = AnalysisTemplate(
    name="ma",
    system_prompt=(
        "You are a Managing Director at JP Morgan specializing in M&A advisory. "
        "Analyze based on provided data only."
    ),
    user_prompt=(
        "Perform an M&A accretion/dilution analysis for the following company "
        "as a potential acquisition target.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Deal Structure\n"
        "Hypothetical cash vs. stock mix and total consideration.\n\n"
        "## Pro Forma Income Statement\n"
        "Combined company earnings analysis.\n\n"
        "## EPS Impact\n"
        "Accretion or dilution analysis.\n\n"
        "## Synergies\n"
        "Cost savings and revenue opportunities.\n\n"
        "## Break-even Analysis\n"
        "What synergies are needed to be accretive."
        + DISCLAIMER
    ),
)

LBO = AnalysisTemplate(
    name="lbo",
    system_prompt=(
        "You are a Private Equity Associate at KKR specializing in LBO modeling. "
        "Use provided data for all calculations."
    ),
    user_prompt=(
        "Build a complete LBO model for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Sources and Uses\n"
        "How the deal would be funded (debt, equity, fees).\n\n"
        "## Debt Structure\n"
        "Senior debt, mezzanine, interest rates, covenants.\n\n"
        "## Cash Flow Sweep\n"
        "How excess cash pays down debt over the hold period.\n\n"
        "## Exit Scenarios\n"
        "Strategic sale vs. IPO in year 5.\n\n"
        "## Returns Analysis\n"
        "IRR calculation and cash-on-cash multiple."
        + DISCLAIMER
    ),
)

COMPS = AnalysisTemplate(
    name="comps",
    system_prompt=(
        "You are an Equity Research Analyst at Citi specializing in comparable "
        "company analysis. Base your analysis on real market data."
    ),
    user_prompt=(
        "Perform a trading comparable company analysis for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Peer Group\n"
        "10-15 public companies in the same industry with rationale.\n\n"
        "## Trading Multiples\n"
        "EV/EBITDA, EV/Revenue, P/E for each peer.\n\n"
        "## Valuation Range\n"
        "25th percentile, median, 75th percentile multiples.\n\n"
        "## Implied Valuation\n"
        "What the company is worth at each multiple.\n\n"
        "## Premium/Discount Analysis\n"
        "Why the company deserves premium or discount vs. peers."
        + DISCLAIMER
    ),
)

PRECEDENT = AnalysisTemplate(
    name="precedent",
    system_prompt=(
        "You are an M&A Banker at Lazard specializing in precedent transaction analysis. "
        "Provide analysis based on actual historical deal data."
    ),
    user_prompt=(
        "Perform a precedent transaction analysis for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Transaction Universe\n"
        "15-20 relevant M&A deals in the past 5 years.\n\n"
        "## Deal Multiples\n"
        "EV/EBITDA, EV/Revenue paid in each transaction.\n\n"
        "## Premium Analysis\n"
        "Control premium paid over trading price.\n\n"
        "## Implied Valuation\n"
        "What the company is worth based on precedent multiples."
        + DISCLAIMER
    ),
)

IPO = AnalysisTemplate(
    name="ipo",
    system_prompt=(
        "You are a Capital Markets Banker at Barclays specializing in IPO pricing. "
        "Analyze based on provided data."
    ),
    user_prompt=(
        "Perform an IPO valuation and pricing analysis for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Offering Structure\n"
        "Primary vs. secondary shares, total raise estimate.\n\n"
        "## Valuation Range\n"
        "Low, mid, high price per share scenarios.\n\n"
        "## Comparable IPOs\n"
        "Recent deals in the same sector with pricing multiples.\n\n"
        "## Dilution Analysis\n"
        "How much existing owners would get diluted."
        + DISCLAIMER
    ),
)

CREDIT = AnalysisTemplate(
    name="credit",
    system_prompt=(
        "You are a Leveraged Finance Banker specializing in credit analysis. "
        "Use provided financial data for all calculations."
    ),
    user_prompt=(
        "Perform a credit analysis and debt capacity assessment for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## EBITDA Analysis\n"
        "Last 3 years and next 3 years projected.\n\n"
        "## Leverage Ratios\n"
        "Total Debt/EBITDA vs. industry standards.\n\n"
        "## Interest Coverage\n"
        "EBITDA/Interest expense and minimum thresholds.\n\n"
        "## Maximum Debt Capacity\n"
        "How much the company can borrow responsibly.\n\n"
        "## Debt Structure Recommendation\n"
        "Senior secured, unsecured, subordinated layers."
        + DISCLAIMER
    ),
)

SOTP = AnalysisTemplate(
    name="sotp",
    system_prompt=(
        "You are a Restructuring Advisor at Evercore specializing in SOTP valuations. "
        "Analyze based on provided data."
    ),
    user_prompt=(
        "Perform a sum-of-the-parts valuation for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Business Segments\n"
        "Break the company into distinct operating divisions.\n\n"
        "## Segment Financials\n"
        "Revenue, EBITDA, margins for each division.\n\n"
        "## Segment Valuations\n"
        "Individual valuation for each business unit.\n\n"
        "## Total Value\n"
        "Sum of all parts minus debt plus cash."
        + DISCLAIMER
    ),
)

OPERATING_MODEL = AnalysisTemplate(
    name="operating_model",
    system_prompt=(
        "You are a Growth Equity Investor at General Atlantic specializing in "
        "operating models and unit economics. Use provided data."
    ),
    user_prompt=(
        "Build a detailed operating model for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Revenue Build\n"
        "Bottom-up forecast by segment or geography.\n\n"
        "## Unit Economics\n"
        "Key metrics: CAC, LTV, payback period, gross margin per unit.\n\n"
        "## Key Drivers\n"
        "What makes revenue and costs move.\n\n"
        "## Scenario Planning\n"
        "Upside, base, and downside case assumptions.\n\n"
        "## Breakeven Analysis\n"
        "When the company becomes cash flow positive."
        + DISCLAIMER
    ),
)

SENSITIVITY = AnalysisTemplate(
    name="sensitivity",
    system_prompt=(
        "You are a Risk Management VP at UBS specializing in sensitivity "
        "and scenario analysis. Base all analysis on provided data."
    ),
    user_prompt=(
        "Perform sensitivity and scenario analysis for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## One-way Sensitivity\n"
        "How value changes with one variable (revenue growth, margin, WACC).\n\n"
        "## Two-way Sensitivity\n"
        "How value changes with two variables simultaneously.\n\n"
        "## Scenario Analysis\n"
        "Best case, base case, worst case with assumptions.\n\n"
        "## Risk Factors\n"
        "Top 5 assumptions with biggest impact on value.\n\n"
        "## Hedging Strategies\n"
        "How to protect against key risks."
        + DISCLAIMER
    ),
)

IC_MEMO = AnalysisTemplate(
    name="ic_memo",
    system_prompt=(
        "You are a Partner at Blackstone preparing an investment committee memo. "
        "Use provided data for all analysis."
    ),
    user_prompt=(
        "Write a complete investment committee memo for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Executive Summary\n"
        "3-paragraph overview (investment thesis, returns, risks).\n\n"
        "## Company Analysis\n"
        "Business model, competitive position, financial performance.\n\n"
        "## Investment Thesis\n"
        "Why this investment makes money (3-5 key points).\n\n"
        "## Valuation Summary\n"
        "Multiple methodologies with range.\n\n"
        "## Risk Assessment\n"
        "Top 5 risks and mitigation strategies.\n\n"
        "## Recommendation\n"
        "Invest or pass with clear reasoning."
        + DISCLAIMER
    ),
)

# --- Retail investor analysis templates ---

STOCK_ANALYSIS = AnalysisTemplate(
    name="stock_analysis",
    system_prompt=(
        "You are a senior Wall Street analyst providing comprehensive stock analysis. "
        "Analyze based on the provided financial data — do not fabricate numbers. "
        "Give a clear Buy, Hold, or Sell recommendation with detailed reasoning."
    ),
    user_prompt=(
        "Perform a full stock analysis for the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Revenue Growth\n"
        "Historical and projected revenue growth trajectory.\n\n"
        "## Profit Margins\n"
        "Operating, net, and gross margin analysis.\n\n"
        "## Debt Levels\n"
        "Debt-to-equity, interest coverage, and financial health.\n\n"
        "## Competitive Position\n"
        "Market position, moat, and competitive advantages.\n\n"
        "## Valuation\n"
        "Current valuation vs. historical and peer multiples.\n\n"
        "## Recommendation\n"
        "Clear **Buy**, **Hold**, or **Sell** recommendation with reasoning."
        + DISCLAIMER
    ),
)

STOCK_SCREENER = AnalysisTemplate(
    name="stock_screener",
    system_prompt=(
        "You are a quantitative investment strategist specializing in stock screening. "
        "Provide specific, actionable screening criteria with exact financial metrics "
        "and thresholds."
    ),
    user_prompt=(
        "Create stock screening criteria for finding high-quality {style} stocks "
        "in the {sector} sector within the {market} market.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Primary Screening Criteria\n"
        "Exact financial metrics, ratios, and thresholds to filter by.\n\n"
        "## Secondary Quality Filters\n"
        "Additional qualitative and quantitative filters.\n\n"
        "## Red Flags to Exclude\n"
        "Conditions that should disqualify a stock.\n\n"
        "## Example Stocks\n"
        "Stocks that currently meet these criteria."
        + DISCLAIMER
    ),
)

EARNINGS_REPORT = AnalysisTemplate(
    name="earnings_report",
    system_prompt=(
        "You are a senior equity research analyst specializing in earnings analysis. "
        "Break down earnings reports in clear, actionable language based on provided data."
    ),
    user_prompt=(
        "Break down the latest earnings data for the following company in plain language.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Key Results\n"
        "Revenue, EPS, and major line items vs. expectations.\n\n"
        "## Beats and Misses\n"
        "What beat or missed expectations and by how much.\n\n"
        "## Forward Guidance\n"
        "What management signaled about the future.\n\n"
        "## Investment Case Impact\n"
        "Whether these results change the investment thesis."
        + DISCLAIMER
    ),
)

RISK_ASSESSMENT = AnalysisTemplate(
    name="risk_assessment",
    system_prompt=(
        "You are a risk management specialist analyzing downside risk for investors. "
        "Provide honest, thorough risk assessment based on provided data."
    ),
    user_prompt=(
        "Analyze the downside risk of investing in the following company.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Industry Threats\n"
        "Sector-level risks and disruption potential.\n\n"
        "## Competitive Risks\n"
        "Threats from competitors and market share erosion.\n\n"
        "## Balance Sheet Vulnerabilities\n"
        "Debt levels, liquidity concerns, and financial fragility.\n\n"
        "## Macro Exposure\n"
        "Sensitivity to interest rates, recession, and geopolitical events.\n\n"
        "## Worst-Case Scenario\n"
        "Realistic worst-case scenario and potential downside percentage."
        + DISCLAIMER
    ),
)

STOCK_COMPARISON = AnalysisTemplate(
    name="stock_comparison",
    system_prompt=(
        "You are a portfolio strategist comparing two investments head to head. "
        "Provide objective, data-driven comparison based on provided financials."
    ),
    user_prompt=(
        "Compare the following two companies for a {style} investor "
        "with a {timeframe} horizon.\n\n"
        "### Company A\n{financials_summary}\n\n"
        "### Company B\n{comparison_summary}\n\n"
        "Provide the following sections:\n"
        "## Valuation Comparison\n"
        "P/E, EV/EBITDA, and other multiples side by side.\n\n"
        "## Growth Trajectory\n"
        "Revenue and earnings growth comparison.\n\n"
        "## Financial Health\n"
        "Debt, margins, and cash flow comparison.\n\n"
        "## Competitive Moat\n"
        "Sustainability of competitive advantages.\n\n"
        "## Verdict\n"
        "Which is the stronger buy and why."
        + DISCLAIMER
    ),
)

PORTFOLIO_BUILDER = AnalysisTemplate(
    name="portfolio_builder",
    system_prompt=(
        "You are a certified financial planner building diversified stock portfolios. "
        "Provide specific, actionable portfolio recommendations."
    ),
    user_prompt=(
        "Build a diversified portfolio of {num_stocks} stocks with "
        "${amount} to invest using a {style} strategy "
        "with a {timeframe} investment horizon.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Portfolio Allocation\n"
        "Each stock with allocation percentage and dollar amount.\n\n"
        "## Investment Thesis\n"
        "Brief thesis behind each pick (2-3 sentences).\n\n"
        "## Sector Diversification\n"
        "How the portfolio is distributed across sectors.\n\n"
        "## Risk Profile\n"
        "Overall portfolio risk level and expected return range."
        + DISCLAIMER
    ),
)

ENTRY_TIMING = AnalysisTemplate(
    name="entry_timing",
    system_prompt=(
        "You are a technical analysis expert specializing in entry point optimization. "
        "Provide specific price targets and timing guidance based on provided data."
    ),
    user_prompt=(
        "Analyze the optimal entry point for the following stock.\n\n"
        "{financials_summary}\n\n"
        "Provide the following sections:\n"
        "## Current Valuation\n"
        "Whether the stock is overvalued, fairly valued, or undervalued.\n\n"
        "## Recent Price Action\n"
        "Key trends, momentum, and volume analysis.\n\n"
        "## Support Levels\n"
        "Key support and resistance levels to watch.\n\n"
        "## Entry Recommendation\n"
        "Buy now, wait for a pullback, or set a specific target entry price."
        + DISCLAIMER
    ),
)

TEMPLATES: dict[str, AnalysisTemplate] = {
    # Investment banking analyses
    "dcf": DCF,
    "financial_statement": THREE_STATEMENT,
    "ma": MA_ANALYSIS,
    "lbo": LBO,
    "comps": COMPS,
    "precedent": PRECEDENT,
    "ipo": IPO,
    "credit": CREDIT,
    "sotp": SOTP,
    "operating_model": OPERATING_MODEL,
    "sensitivity": SENSITIVITY,
    "ic_memo": IC_MEMO,
    # Retail investor analyses
    "stock_analysis": STOCK_ANALYSIS,
    "stock_screener": STOCK_SCREENER,
    "earnings_report": EARNINGS_REPORT,
    "risk_assessment": RISK_ASSESSMENT,
    "stock_comparison": STOCK_COMPARISON,
    "portfolio_builder": PORTFOLIO_BUILDER,
    "entry_timing": ENTRY_TIMING,
}
