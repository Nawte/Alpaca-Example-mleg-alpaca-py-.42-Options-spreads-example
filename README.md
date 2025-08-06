# Alpaca-py 0.42 Multi-Leg Options Spreads Example

This repo provides a simple Python example using [alpaca-py](https://alpaca.markets/docs/python-sdk/) (version 0.42) to fetch option chains, stock snapshots, and calculate bull call spreads for stocks like BP. It's designed for educational purposes—perfect for beginners wanting to experiment with multi-leg (mleg) options orders.

## Features
- Fetches the latest stock ask price.
- Pulls call option chains for the soonest expiration.
- Finds the closest bull call spread (long lower strike, short higher strike).
- Prints bid/ask prices and net spread cost.
- Easily adaptable for bear spreads (shorts) or puts.

## Requirements
- Python 3.8+
- alpaca-py==0.42.0 (`pip install alpaca-py==0.42.0`)
- Requests and Pandas (`pip install requests pandas`)
- Alpaca API keys (paper trading recommended). Store in a file like `alpaca_keys.txt` with format:

- YOUR_PAPER_API_KEY
YOUR_PAPER_SECRET_KEY
YOUR_LIVE_API_KEY (optional)
YOUR_LIVE_SECRET_KEY (optional)

- Enable options trading (Level 3) in your Alpaca account: https://alpaca.markets/docs/trading/options/

## Usage
1. Clone the repo: `git clone https://github.com/Nawte/Alpaca-Example-mleg-alpaca-py-.42-Options-spreads-example.git`
2. Navigate to the folder: `cd Alpaca-Example-mleg-alpaca-py-.42-Options-spreads-example`
3. Run the script: `python bp_bull_call_spread.py`
- Output example:

- Bull Call Spread for BP:
Stock Price: $33.88
Buy Call (Long): BP250815C00035000
Bid: $1.50, Ask: $1.60
Sell Call (Short): BP250815C00037500
Bid: $0.50, Ask: $0.60
Spread Cost (per contract): $1.10
Total Cost (for 1 contract(s)): $110.00


## Customization
- **Change Stock**: Edit `SYMBOL = 'BP'` to any ticker (e.g., 'TSLA').
- **Tighter/Wider Spreads**: Adjust `STRIKE_SPREAD = 2.5` (e.g., 5.0 for wider).
- **Bear Call Spread (Short)**: In `find_closest_bull_spread`, swap logic: Start with higher strike for short sell, lower for long buy. Update sides in potential order submission.
- **Puts Instead of Calls**: Change `contract_type='call'` to `'put'` in `get_option_chain`. Replace 'C' with 'P' in contract validation.
- **Place Actual Order**: Uncomment/add a `LimitOrderRequest` block like this (for bull call spread):

- order = LimitOrderRequest(
symbol=SYMBOL,
qty=1,  # Number of spreads
side=OrderSide.BUY,
time_in_force=TimeInForce.DAY,
limit_price=spread_cost,
order_class=OrderClass.MLEG,
legs=[
OptionLegRequest(symbol=long_contract, side=OrderSide.BUY, ratio_qty=1),
OptionLegRequest(symbol=short_contract, side=OrderSide.SELL, ratio_qty=1)
]
)
response = alpaca_trading.submit_order(order)
print(f"Order submitted: {response.id}")

Warning: This places a real paper trade—test carefully!

## License
GNU General Public License v2 (see LICENSE file).

## Credits
Inspired by discussions on alpaca.markets and Grok AI. Contributions welcome—fork and PR!

Happy trading! 🚀
