# PHOENIX Narrative

## Purpose

PHOENIX is a safety-first Japanese-equity paper-trading and validation system. Its purpose is to build reproducible evidence for stable returns without manufacturing favorable results or bypassing risk controls.

## Capital and cost policy

- Initial operating capital: 300,000 yen.
- A further 200,000 yen may be added in the following week only after performance review; planned total is 500,000 yen.
- Profits may compound, while any living-cost distribution remains conditional on realized, cost-adjusted profit and the approved monthly policy.
- Evaluate results after commission, spread, slippage, tax reserve, and the current fixed operating cost of 7,000 yen per month.
- Minimize paid services, unnecessary downloads, repeated compute, and energy use.

## Safety policy

- Real trading remains disabled until the required evidence, read-only RSS validation, staged gate, and explicit human approval are complete.
- Historical walk-forward evidence supplements but does not impersonate distinct real paper-trading days.
- Risk limits, data-quality gates, and readiness requirements are never relaxed to obtain fills or profits.
- Start any future live pilot at deliberately limited exposure with manual approval; expansion is based on reviewed evidence, not elapsed time alone.

## Data strategy

- MarketSpeed II RSS through desktop Excel is the intended official source for real-time Japanese-equity prices and supported chart data.
- The first RSS integration is read-only. Order functions must not be installed or called by PHOENIX.
- Public market data is a temporary virtual-paper and fallback source, with caching, TLS verification, freshness checks, and provider-failure isolation.
- Future US-dollar assets and dividend-income strategies are valid research directions, but they must not dilute the current Japanese-equity validation scope.

## Human responsibility

AI organizes evidence, detects inconsistencies, drafts changes, and runs safe verification. The user retains final authority over capital contributions, living-cost distributions, broker connectivity, and any transition toward live trading.
