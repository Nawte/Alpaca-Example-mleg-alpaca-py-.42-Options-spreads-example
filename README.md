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

This guide addresses common issues with alpaca-py 0.42, especially for Windows and Python 3.12 users.

Issue: Missing Options Snapshots or Mleg Order Support





Problem: Methods like OptionSnapshotRequest or multi-leg order submissions fail or are unavailable.



Cause: Alpaca-py 0.42 may have incomplete support for Python 3.12 or Windows due to dependency conflicts (e.g., aiohttp, websockets).



Solution:





Downgrade Python: Use Python 3.8 (3.8.10 recommended). Install via pyenv install 3.8.10 or Anaconda.



Set Up Virtualenv:

python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate



Install Dependencies:

pip install alpaca-py==0.42.0 requests pandas



Verify SDK Methods: Run python check_alpaca_sdk.py to list available methods. Look for OptionSnapshotRequest in alpaca.data.requests.



Force Reinstall: If issues persist, try:

pip install --force-reinstall alpaca-py==0.42.0



Check for Bugs: Visit Alpaca’s GitHub or forums.

Issue: Validation Errors in OptionChainRequest





Problem: OptionChainRequest fails with underlying_symbol: Field required.



Solution: Use underlying_symbol instead of symbol:

request = OptionChainRequest(underlying_symbol='BP', contract_type='call')

Issue: No strike_price in OptionsSnapshot





Problem: OptionsSnapshot objects lack strike_price attribute.



Solution: Parse the strike price from the contract symbol (last 8 digits / 1000):

def parse_strike(contract_symbol):
    if len(contract_symbol) < 9 or contract_symbol[-9] not in ['C', 'P']:
        return None
    return int(contract_symbol[-8:]) / 1000

Issue: Mleg Order Fails with "symbol is not allowed"





Problem: LimitOrderRequest for mleg orders fails with {"code":40010001,"message":"symbol is not allowed for mleg order"}.



Solution: Omit the symbol field in LimitOrderRequest for multi-leg orders, as the symbols are specified in the legs:

order = LimitOrderRequest(
    qty=1,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY,
    limit_price=spread_cost/100,
    order_class=OrderClass.MLEG,
    legs=[
        OptionLegRequest(symbol=long_contract, side=OrderSide.BUY, ratio_qty=1),
        OptionLegRequest(symbol=short_contract, side=OrderSide.SELL, ratio_qty=1)
    ]
)

Issue: Dependency Conflicts





Problem: Errors like ModuleNotFoundError or SSL issues with aiohttp/websockets.



Solution:





Run pip list to check installed versions.



Ensure compatible versions: requests>=2.25, pandas>=1.2, aiohttp<3.9.



Pin versions if needed: pip install aiohttp==3.8.1 websockets==10.3.

Pro Tip

Always test in Alpaca’s paper trading environment before going live. Run check_alpaca_sdk.py to confirm available methods. If stuck, share the output in a GitHub issue or on Alpaca forums.

Happy debugging! 🚀
