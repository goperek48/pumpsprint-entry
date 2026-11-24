"""Pump.fun paper sprint bot: buy the quiet launches, take the spike, get out.

A new coin appears on its bonding curve and the market passes judgement in
minutes. Across the house dev window (128,058 events, 1,222 new coins) the
middle coin climbed roughly 30% above its launch price within four minutes,
one in four at least doubled, and only about one in twenty-five was still
25% up by the end of the day. The profit is in that first surge, not in
sticking around: coins left alone for an hour mostly slide back to where
they began.

So the bot steps in only while the first surge is still modest. The buy cap
(1% of real reserves) starts at zero and fattens as the coin trades, which
means the earliest batch that can fit a real buy is already a few trades
in. By then the sprinters have run 40-70% and are exhausted; the quiet
ones sit 8-10% above launch with headroom left. On the dev window the quiet
group won about half its races to +50% before -20%, the sprinters barely a
fifth. The bot therefore buys on the first batch where the cap covers the
0.01 SOL round-trip floor and the price is at most 10% above launch, one
buy per coin, staking the cap up to 0.10 SOL. A coin that has already shot
past the ceiling is not chased; it may still be picked up later if it dips
back inside the window.

Once in, the bot is impatient. It sells everything at +25%, or at -20%, or
when the price falls 15% from the best print since entry, or after 300
slots (about two minutes) whatever the price says. Winners earn one extra
stake: if a position sits 20% up and the cap has grown enough for a 0.03
SOL add, the bot adds up to 0.10 SOL, averaging the entry price across
both stakes. Extra size only ever rides on coins already in profit, and a
fatter order spreads the flat per-order chain fee across more lamports.
The house closes finished curves and flattens the book at the end of the
window by itself.

Rules the bot never breaks: five open positions at most, sixteen orders per
batch, never spending cash it does not hold after fees, and every order
carries a 500 bps slippage bound. No clock, no environment, no unseeded
dice: run the same tape twice and the replies come back byte for byte
identical.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bot  # noqa: E402  (after the sys.path line: -P leaves the script dir off sys.path)

# --- strategy knobs, kept together so a sweep can retune them ---
ENTRY_MIN_MULT = 1.00      # buy once the price is at least the launch price
ENTRY_MAX_MULT = 1.10      # ... but only while the first surge is still modest:
                           # a coin already 40% past launch when the size cap
                           # first fits a buy is running on empty (on the dev
                           # window that group wins ~20% of its races), while
                           # the quiet launchers near +8-10% win about half
                           # of their races to +50% before -20%
ENTRY_WINDOW_SLOTS = 300   # ... and the coin is no more than ~2 min old
MIN_STAKE_LAMPORTS = 10_000_000        # 0.01 SOL: the guardrail round-trip floor
MAX_STAKE_LAMPORTS = 100_000_000       # 0.10 SOL: the largest single stake
TAKE_PROFIT_MULT = 1.25    # bank the whole position at +25% over entry
STOP_LOSS_MULT = 0.80      # dump the whole position at -20% under entry
TRAIL_MULT = 0.85          # dump it when the price falls 15% off its peak
MAX_HOLD_SLOTS = 300       # hard clock: out after ~2 minutes regardless
# --- scale-in: add size only to the coins already proving themselves ---
SCALE_IN_MULT = 1.20       # add once the position is +20% over entry
SCALE_IN_MIN_CAP = 30_000_000   # ... and the cap has grown to allow a real add
SCALE_IN_MAX_LAMPORTS = 100_000_000  # never add more than 0.10 SOL to one coin
MAX_SLIPPAGE_BPS = 500     # a fill may land at most 5% worse than the quote


class Trade:
    """One live trade, as the bot remembers it."""

    __slots__ = ("entry", "peak", "opened", "size", "topped")

    def __init__(self, entry, opened, size):
        self.entry = entry          # quote per token paid on the first buy
        self.peak = entry           # best quote per token seen since entry
        self.opened = opened        # slot the first buy was decided on
        self.size = size            # lamports the first buy cost
        self.topped = False         # the one pyramid add is still unused


class Bot:
    """Buys each quiet launcher once, exits fast, never holds more than five."""

    def __init__(self):
        # mint -> launch price (quote per token on the CreateEvent)
        self.launch_price = {}
        # mint -> slot its CreateEvent landed in
        self.born = {}
        # mints bought once already (a dumped coin gets no second entry)
        self.done = set()
        # mint -> Trade for the positions still open
        self.live = {}

    def on_batch(self, state, batch):
        self._note_launches(batch)
        orders = []
        orders += self._close_out(state)
        orders += self._top_up(state)
        orders += self._open_new(state, batch)
        return orders

    def _note_launches(self, batch):
        """Record the launch price of every coin born in this batch."""
        for e in batch["events"]:
            if e["event"] != "CreateEvent":
                continue
            mint = e["mint"]
            # Take the launch price from the event itself: the curve in
            # state already includes every trade in this batch, so reading
            # it here would price the launch after the first trades of the
            # same slot, not at creation.
            vt = int(e.get("virtual_token_reserves") or 0)
            vq = int(e.get("virtual_quote_reserves") or 0)
            if vt > 0 and vq > 0:
                self.launch_price[mint] = vq / vt
                self.born[mint] = e["slot"]

    @staticmethod
    def _quote(curve):
        """A curve's current price in quote lamports per token, or None."""
        if curve.virtual_token_reserves <= 0:
            return None
        return curve.virtual_quote_reserves / curve.virtual_token_reserves

    def _close_out(self, state):
        """Sell every open trade whose exit rule has tripped."""
        orders = []
        for mint, trade in list(self.live.items()):
            holding = state.positions.get(mint)
            if holding is None or holding.token_amount <= 0:
                # Nothing left to sell (already closed by the house or
                # sold): drop it from the book.
                del self.live[mint]
                continue
            curve = state.curves.get(mint)
            if curve is None or curve.complete:
                # A finished curve refuses sell orders and the house
                # closes it on its own. Drop it from the book.
                if curve is not None and curve.complete:
                    del self.live[mint]
                continue
            price = self._quote(curve)
            if price is None:
                continue
            if price > trade.peak:
                trade.peak = price
            if (
                price >= trade.entry * TAKE_PROFIT_MULT
                or price <= trade.entry * STOP_LOSS_MULT
                or price <= trade.peak * TRAIL_MULT
                or state.slot - trade.opened >= MAX_HOLD_SLOTS
            ):
                orders.append(
                    {
                        "side": "sell",
                        "mint": mint,
                        "token_amount": holding.token_amount,
                        "max_slippage_bps": MAX_SLIPPAGE_BPS,
                    }
                )
                del self.live[mint]
        return orders

    def _top_up(self, state):
        """Top up the winners, once each. The add goes out only when the
        coin has already shown it can climb (+20%) and the cap has grown
        wide enough for a worthwhile top-up. The extra lamports ride only
        on coins already in the green, and a fatter order spreads the flat
        per-order chain fee across more lamports than the small first
        stake ever could."""
        orders = []
        caps = state.hello["caps"]
        tx = state.tx_fee_lamports()
        free = state.free_cash_lamports()
        for mint, trade in list(self.live.items()):
            if trade.topped:
                continue
            if len(orders) + len(state.pending) >= caps["max_orders_per_batch"]:
                break
            curve = state.curves.get(mint)
            if curve is None or curve.complete:
                continue
            price = self._quote(curve)
            if price is None or price < trade.entry * SCALE_IN_MULT:
                continue
            cap = state.max_buy_lamports(mint)
            if cap < SCALE_IN_MIN_CAP:
                continue
            add = min(cap, SCALE_IN_MAX_LAMPORTS)
            if free < add + tx:
                continue
            orders.append(
                {
                    "side": "buy",
                    "mint": mint,
                    "quote_lamports": add,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            )
            # Average the entry price across both stakes, so the exit
            # rules keep measuring the full position against what it
            # really cost.
            trade.entry = (trade.entry * trade.size + price * add) / (trade.size + add)
            trade.size += add
            trade.topped = True
            free -= add + tx
        return orders

    def _open_new(self, state, batch):
        """First buys on fresh coins whose opening surge is still modest."""
        orders = []
        caps = state.hello["caps"]
        tx = state.tx_fee_lamports()
        free = state.free_cash_lamports()
        room = caps["max_open_positions"] - state.committed_position_count()
        if room <= 0:
            return orders
        for e in batch["events"]:
            if len(orders) + len(state.pending) >= caps["max_orders_per_batch"]:
                break
            mint = e["mint"]
            if mint in self.done or mint in self.live:
                continue
            if mint not in self.launch_price:
                continue
            if state.slot - self.born.get(mint, state.slot) > ENTRY_WINDOW_SLOTS:
                continue
            curve = state.curves.get(mint)
            if curve is None or curve.complete:
                continue
            price = self._quote(curve)
            if price is None or price < self.launch_price[mint] * ENTRY_MIN_MULT:
                continue
            if price > self.launch_price[mint] * ENTRY_MAX_MULT:
                # Surge too far already: the move is exhausted. Wait for a
                # dip back inside the window instead of chasing the top.
                continue
            cap = state.max_buy_lamports(mint)
            if cap < MIN_STAKE_LAMPORTS:
                continue
            stake = min(cap, MAX_STAKE_LAMPORTS)
            if room <= 0 or free < stake + tx:
                continue
            orders.append(
                {
                    "side": "buy",
                    "mint": mint,
                    "quote_lamports": stake,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            )
            self.done.add(mint)
            self.live[mint] = Trade(price, state.slot, stake)
            free -= stake + tx
            room -= 1
        return orders


def main():
    bot = Bot()
    makefun_bot.run(bot.on_batch)


if __name__ == "__main__":
    main()
