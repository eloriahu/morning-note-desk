# News timing by market

The default is `timing_mode: "market_close"`. Each market starts at its latest completed desk close and ends at the run's timezone-aware cutoff. Include releases timestamped exactly at the close. On a normal Monday morning this starts on Friday; at 16:00 Singapore time on Monday, Japan/Korea start that Monday at 14:30 and Australia at 14:15. Markets that have not yet closed keep the previous session's starting point. Explicit `--hours` selects a rolling window instead.

Default cutoffs are in `collector/market_windows.py`:

| Market code | Normal cutoff | Basis |
| --- | --- | --- |
| JP | 14:30 Singapore / 15:30 Tokyo | [JPX closing auction](https://www.jpx.co.jp/english/equities/trading/domestic/04.html) |
| KR | 14:30 Singapore / 15:30 Seoul | [KRX regular session](https://global.krx.co.kr/contents/GLB/06/0602/0602020204/GLB0602020204T1.jsp) |
| AU | 14:15 Singapore, fixed | User's desk convention. [ASX sessions](https://www.asx.com.au/markets/market-resources/trading-hours-calendar/cash-market-trading-hours) follow Sydney time, so this fixed SGT convention is not an automatic daylight-saving conversion of exchange hours. |
| HK | 16:10 Hong Kong/Singapore | End of [HKEX closing-auction range](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Trading-Hours/Securities-Market?sc_lang=en) |
| CH (CN alias) | 15:00 Shanghai/Singapore | [SSE stock session](https://english.sse.com.cn/start/trading/schedule/) |
| TT (TW alias) | 13:30 Taipei/Singapore | [TWSE regular session](https://www.twse.com.tw/en/products/system/day-trading.html) |
| NZ | 16:45 Auckland | Regular-session desk cutoff; timezone conversion follows Auckland daylight saving. Check [NZX session information](https://new.nzx.com/investing/nzx-trading-hours) for changes. |
| SP (SG alias) | 17:16 Singapore | End of [SGX trade-at-close phase](https://rulebook.sgx.com/rulebook/regulatory-notice-821-trading-hours-market-phases-application-market-phases-and-principles) |
| IN | 15:30 Kolkata / 18:00 Singapore | [NSE normal session](https://www.nseindia.com/resources/exchange-communication-holidays) |
| MK (MY alias) | 17:00 Kuala Lumpur/Singapore | Normal cash-equity desk cutoff; verify the current Bursa session for each special date. |

These defaults cover normal weekdays, not a maintained exchange holiday calendar. Before research, check holidays, shortened sessions and exceptional closures for the edition and preceding session. Save verified date overrides in `config.json`; a date maps to a local clock or `null` for a closed day. An explicit dated clock also allows a special weekend session. For example, using illustrative dates only:

```json
{
  "timing_mode": "market_close",
  "market_close_rules": {
    "JP": {"sessions": {"2026-01-01": null}},
    "HK": {"sessions": {"2026-12-24": "12:10"}}
  }
}
```

Do not infer the company's market solely from the publisher's location. Exchange codes and verified company tickers take priority; source scope is only a discovery hint. Review the full headline audit when identities are uncertain. A researched story may specify its primary `market`, especially for cross-listed companies. Otherwise the composer applies all ticker markets, using the latest starting point. Unresolved markets remain held. `GLOBAL` is reserved for genuinely regional macro context and uses the earliest market starting point; it must not be used to admit a stale company story.

Copy `timing_mode`, `market_windows` and the overall `window_start` envelope from collection into `research.json`, after verifying session dates. Every window ends at `as_of`. The composer tests each cited source against that story's market window, so a wide envelope cannot admit pre-close company news. Exact timestamps remain required. Display the market table in the editor review only; keep it outside the distribution email.
