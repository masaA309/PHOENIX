# PHOENIX v7 Step21

Step21 is an isolated virtual-market-feed paper simulation. It observes public
five-minute prices, models standard-unit and Rakuten Kabu Mini costs, and writes
a local trade-history notification preview. The preview lists every new virtual
fill in the run with its route, quantity, reference/fill price, commission,
spread, slippage reserve, realized P&L, and post-fill cash. It never submits an
order or sends a notification.

## Evidence boundary

- Contract: `PHOENIX_VIRTUAL_RSS_PAPER_V1`
- Evidence kind: `VIRTUAL_MARKET_FEED_SIMULATION`
- Quote source: `YFINANCE_PUBLIC_5M_UNADJUSTED`
- Real Rakuten RSS sessions credited: `0`
- Canonical paper days credited: `0`
- Audited live fills credited: `0`
- External orders and notifications: always `0`

Yahoo prices may be delayed and do not prove Rakuten bid/ask prices. Values may
be used for marking outside the market session, but fills require a current,
post-decision intraday observation during the JPX session. Missing bid/ask is
explicitly modeled and is not reported as measured slippage.

## Quote environment check

Run the network-free check before requesting prices:

```powershell
python -X utf8 virtual_rss_entry_v7.py --check-environment
```

Step21 validates `certifi`, `curl_cffi`, `yfinance`, and the TLS CA bundle. On
Windows it materializes the already-installed, validated CA bundle into a
temporary ASCII-path cache before calling curl. This avoids OneDrive placeholder
and non-ASCII path failures without disabling TLS verification. A failure is
reported with a stable code and remediation; it never falls back to unverified
HTTPS or advances the virtual ledger.

## Costs

- Standard unit: the existing 100-share sizing rules remain unchanged. Until
  the account fee course is evidenced, each virtual fill reserves 1,070 yen.
- Kabu Mini: 1--99 shares, commission 0 yen, realtime spread 0.22%, plus the
  existing adverse-slippage reserve. Buy prices round up and sell prices round
  down to whole yen.
- Monthly fixed operating cost: 7,000 yen.
- Profit tax reserve: 20.315%. It is a report reserve, not a fill cash debit.
- The conditional 200,000-yen contribution and living-fund distribution are
  never automatic.

Rakuten sources reviewed on 2026-07-23:

- <https://www.rakuten-sec.co.jp/web/domestic/ols/commission/>
- <https://www.rakuten-sec.co.jp/web/domestic/ols/rule/>
- <https://www.rakuten-sec.co.jp/web/domestic/ols/lineup/>
- <https://www.rakuten-sec.co.jp/web/domestic/ols/>

## One-time initialization

The isolated ledger must be initialized from the existing canonical paper
broker. This preserves its cash and positions and binds the source SHA-256.
Resetting an existing virtual ledger is intentionally forbidden.

```powershell
python -X utf8 virtual_rss_entry_v7.py --initialize-from-paper
```

## Kabu Mini eligibility

Rakuten states that only selected TSE securities are eligible and that the
latest list is available in Super Screener. Step21 therefore blocks Kabu Mini
fills until a reviewed export is supplied. The following is a schema example,
not eligibility evidence. Do not run the import command until the real reviewed
export exists. Save the reviewed CSV below
`runtime/v7_virtual_rss/`:

```csv
ticker,opening_buy_enabled,realtime_buy_enabled
1605.T,1,1
9501.T,1,1
```

Then import it. Evidence expires after seven days and cannot move backwards.

```powershell
python -X utf8 virtual_rss_entry_v7.py --import-kabumini-eligibility runtime/v7_virtual_rss/kabumini_eligibility.csv
```

## Runs and notification history

To refresh the full market-data lineage and rebuild `trade_signals.csv` without
running charts or any external notification, use the dedicated refresh first:

```powershell
python -X utf8 run_phoenix.py --refresh-only
python -X utf8 scheduled_entry_v7.py --force --dry-run
```

The normal 08:00 daily workflow now also runs `trade_engine.py` after the AI
judgement and before ranking/notification. All child data-fetch processes inherit
the same validated TLS CA bundle. A failed refresh stops the remaining required
tasks and cannot make an old candidate appear current.

```powershell
python -X utf8 virtual_rss_entry_v7.py --dry-run
python -X utf8 virtual_rss_entry_v7.py --paper-run
Get-Content reports/v7_virtual_trade_notification_preview.txt
```

`--dry-run` never changes either broker state or the virtual ledger. A paper run
may update only `state/v7_virtual_rss_paper.json` and Step21 reports. The
notification output is a preview file only; it does not read webhook variables
or import the legacy notification sender. Its text file is bound to the JSON
preview by an exact SHA-256. Reports are written before the ledger commit, so a
report or notification write failure cannot leave an unreported virtual fill.
The report records the expected post-run ledger SHA-256; rerunning identical
input is an idempotent no-op. Each BUY history event also seals the complete
eligible-candidate set, run quote universe, sizing policy, and candidate
controls. The exact candidate CSV bytes and full Kabu Mini eligibility evidence
are sealed as well. Ledger replay rebuilds every candidate, selects the highest
ranked fill-ready row, reruns position sizing, route selection, costs, evidence
freshness, cash reserve, and the one-BUY-per-day cap instead of trusting stored
totals.
