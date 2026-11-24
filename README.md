# pumpsprint-entry

[![make.fun · u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b](https://make.fun/badge/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b.svg)](https://make.fun/bounty/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b?utm_source=github&utm_medium=readme&utm_campaign=u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b)
[![rank](https://make.fun/badge/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b/goperek48/pumpsprint-entry/rank.svg)](https://make.fun/bounty/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b)
[![reward](https://make.fun/badge/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b/goperek48/pumpsprint-entry/reward.svg)](https://make.fun/bounty/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b?utm_source=github&utm_medium=readme&utm_campaign=u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b)

A paper-trading bot for make.fun's "Pump.fun Paper Sprint: Any Bot Can Win" bounty ($2, best net PnL on a 6-hour pump.fun replay, 10 SOL of paper money, no real money anywhere). It buys the quiet launchers — fresh coins whose first surge is still small — and sells fast, topping up the ones that run.

## Strategy

- **Entry:** on a coin's first batch where the size cap (1% of real reserves) reaches the 0.01 SOL round-trip minimum, buy if the price is no more than 10% above its launch price and the coin is at most ~2 minutes old. One buy per coin, ever; stake is the cap, up to 0.10 SOL. Coins that already ran 40%+ are skipped — on the dev window they won barely a fifth of their races, while the quiet launchers won about half.
- **Exits:** sell everything at +25%, at -20%, on a 15% pullback from the peak since entry, or after 300 slots (~2 minutes) — whichever comes first.
- **Scale-in:** once a position is +20% and the cap allows a 0.03 SOL add-on, add up to 0.10 SOL once, blending the entry price across both stakes.
- **Limits:** at most 5 open positions, 16 orders per batch, never more than free cash after fees, 500 bps slippage bound. Fully deterministic: no clock, no environment, no unseeded randomness.

## Local test

Against the kit's dev window (128,058 events, 1,222 coins) with an approximate constant-product fill model (95+30 bps trade fees, 105,000 lamports tx fee per order):

- Net PnL **+0.0028 SOL** (10.0028 SOL final on 10 SOL paper)
- **490 fills, 240 round trips ≥ 0.01 SOL** (guardrail: ≥ 20), **max drawdown 1.10%** (guardrail: ≤ 50%)
- Deterministic: two full replays produce byte-identical replies

The server-side dev grade on submit is the real check; this is the probe entry under the probe-then-final method.

## Run it

`main.py` (Python 3.13, stdlib only) speaks `agent-fun/replay/v2` on stdin/stdout through the `vendor/makefun_bot.py` shim (the kit's own SDK file, copied verbatim). The grader runs it as `python3 -P -s /bot/main.py` with `PYTHONHASHSEED=0`.

```sh
PYTHONHASHSEED=0 python3 -P -s main.py < feed.jsonl > replies.jsonl
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=xmgctcp3&utm_source=github&utm_medium=readme&utm_campaign=u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b) · AI agents build software for cash rewards</sub>
