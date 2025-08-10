import asyncio
import re
from collections import defaultdict
from datetime import datetime
import pytz
from alpaca.data.live.option import OptionDataStream
from alpaca.trading.client import TradingClient

# Credentials: Replace with your own API keys from Alpaca (paper trading recommended)
# Create a file 'alpaca_keys.txt' with format: YOUR_API_KEY YOUR_SECRET_KEY
try:
    with open('alpaca_keys.txt', 'r') as f:
        YOUR_API_KEY, YOUR_SECRET_KEY, *_ = f.read().strip().split()
except FileNotFoundError:
    YOUR_API_KEY = 'YOUR_API_KEY'  # Replace with your Alpaca paper trading API key
    YOUR_SECRET_KEY = 'YOUR_SECRET_KEY'  # Replace with your Alpaca paper trading secret key
    print("Error: 'alpaca_keys.txt' not found. Please create it with your API key and secret key or set YOUR_API_KEY and YOUR_SECRET_KEY manually.")

# Initialize clients for trading and real-time option data
trading_client = TradingClient(YOUR_API_KEY, YOUR_SECRET_KEY, paper=True)
stream = OptionDataStream(YOUR_API_KEY, YOUR_SECRET_KEY)

# Global stores for positions, quotes, and P/L tracking
positions = {}
latest_quotes = {}
previous_pl = {}

# Check if market is open (US options: Mon-Fri, 9:30 AM - 4:00 PM ET)
def is_market_open():
    try:
        clock = trading_client.get_clock()
        now = datetime.now(pytz.timezone('US/Eastern'))
        is_open = clock.is_open
        market_open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
        is_within_hours = market_open_time <= now <= market_close_time
        is_weekday = now.weekday() < 5  # Mon-Fri
        return is_open and is_within_hours and is_weekday
    except Exception as e:
        print(f"Error checking market hours: {e}")
        return False

# Parse option symbol: e.g., AMD250815C00172500 -> underlying='AMD', exp='250815', type='C', strike=172.5
def parse_option_symbol(symbol):
    try:
        match = re.match(r'([A-Z]+)(\d{6})([CP])(\d{8})', symbol)
        if match:
            underlying, exp, opt_type, strike_str = match.groups()
            strike = int(strike_str) / 1000
            return underlying, exp, opt_type, strike
        return None, None, None, None
    except Exception as e:
        print(f"Error parsing symbol {symbol}: {e}")
        return None, None, None, None

# Group positions into bull call spreads (long lower strike, short higher strike)
def find_spreads(all_positions):
    groups = defaultdict(list)
    for pos in all_positions:
        if 'option' in pos.asset_class.lower():
            underlying, exp, opt_type, strike = parse_option_symbol(pos.symbol)
            if underlying and opt_type == 'C':  # Focus on calls for this example
                key = (underlying, exp, opt_type)
                groups[key].append(pos)
    
    spreads = {}
    for key, group in groups.items():
        if len(group) >= 2:
            group.sort(key=lambda p: parse_option_symbol(p.symbol)[3])
            long_leg, short_leg = group[:2]
            if long_leg.side == 'long' and short_leg.side == 'short':
                spread_id = f"{key[0]}_{key[1]}_bull_call"
                spreads[spread_id] = {'long': long_leg, 'short': short_leg}
    return spreads

# Print all positions (stocks and options)
def print_positions(all_positions):
    print("\nCurrent Open Positions:")
    if not all_positions:
        print("  No open positions found.")
        return
    for pos in all_positions:
        print(f"\nSymbol: {pos.symbol}")
        print(f"  Qty: {pos.qty}")
        print(f"  Side: {'Long' if float(pos.qty) > 0 else 'Short'}")
        print(f"  Avg Entry Price: ${pos.avg_entry_price}")
        print(f"  Market Value: ${pos.market_value or 'N/A'}")
        print(f"  Unrealized P/L: ${pos.unrealized_pl or 'N/A'}")

# Print detected spreads
def print_spreads(spreads):
    print("\nDetected Call Spreads:")
    if not spreads:
        print("  No call spreads detected.")
        return
    for spread_id, spread in spreads.items():
        print(f"\nSpread: {spread_id}")
        print(f"  Long Leg ({spread['long'].symbol}):")
        print(f"    Qty: {spread['long'].qty}")
        print(f"    Side: {'Long' if float(spread['long'].qty) > 0 else 'Short'}")
        print(f"    Avg Entry Price: ${spread['long'].avg_entry_price}")
        print(f"    Market Value: ${spread['long'].market_value or 'N/A'}")
        print(f"  Short Leg ({spread['short'].symbol}):")
        print(f"    Qty: {spread['short'].qty}")
        print(f"    Side: {'Long' if float(spread['short'].qty) > 0 else 'Short'}")
        print(f"    Avg Entry Price: ${spread['short'].avg_entry_price}")
        print(f"    Market Value: ${spread['short'].market_value or 'N/A'}")

# Calculate P/L for a single leg
def calculate_pl(leg, quote):
    try:
        if not quote:
            return float(leg.unrealized_pl or 0)
        mid_price = (quote.bid_price + quote.ask_price) / 2 if quote.bid_price and quote.ask_price else 0
        market_value = float(leg.qty) * mid_price * 100 * (1 if leg.side == 'long' else -1)
        pl = market_value - float(leg.cost_basis)
        return pl
    except Exception as e:
        print(f"Error calculating P/L for {leg.symbol}: {e}")
        return float(leg.unrealized_pl or 0)

# Calculate total spread P/L
def calculate_spread_pl(spread, quotes):
    long_pl = calculate_pl(spread['long'], quotes.get(spread['long'].symbol))
    short_pl = calculate_pl(spread['short'], quotes.get(spread['short'].symbol))
    return long_pl + short_pl

# WebSocket handler for real-time quote updates
async def quote_handler(quote):
    try:
        symbol = quote.symbol
        latest_quotes[symbol] = quote
        
        updated = False
        for spread_id, spread in positions['spreads'].items():
            if symbol in [spread['long'].symbol, spread['short'].symbol]:
                new_pl = calculate_spread_pl(spread, latest_quotes)
                if spread_id not in previous_pl or abs(new_pl - previous_pl[spread_id]) > 0.01:
                    previous_pl[spread_id] = new_pl
                    updated = True
                    print(f"\n--- Dashboard Update: {spread_id} ---")
                    print(f"Long Leg ({spread['long'].symbol}):")
                    print(f"  Qty: {spread['long'].qty}")
                    print(f"  Side: {'Long' if float(spread['long'].qty) > 0 else 'Short'}")
                    print(f"  Avg Entry Price: ${spread['long'].avg_entry_price}")
                    print(f"  Market Value: ${spread['long'].market_value or 'N/A'}")
                    print(f"  Latest Quote: Bid ${quote.bid_price if symbol == spread['long'].symbol else latest_quotes.get(spread['long'].symbol, {'bid_price': 'N/A'}).get('bid_price'):.2f}, Ask ${quote.ask_price if symbol == spread['long'].symbol else latest_quotes.get(spread['long'].symbol, {'ask_price': 'N/A'}).get('ask_price'):.2f}")
                    print(f"Short Leg ({spread['short'].symbol}):")
                    print(f"  Qty: {spread['short'].qty}")
                    print(f"  Side: {'Long' if float(spread['short'].qty) > 0 else 'Short'}")
                    print(f"  Avg Entry Price: ${spread['short'].avg_entry_price}")
                    print(f"  Market Value: ${spread['short'].market_value or 'N/A'}")
                    print(f"  Latest Quote: Bid ${quote.bid_price if symbol == spread['short'].symbol else latest_quotes.get(spread['short'].symbol, {'bid_price': 'N/A'}).get('bid_price'):.2f}, Ask ${quote.ask_price if symbol == spread['short'].symbol else latest_quotes.get(spread['short'].symbol, {'ask_price': 'N/A'}).get('ask_price'):.2f}")
                    print(f"Spread Real-Time P/L: ${new_pl:.2f}")
                    print("-----------------------------")
        
        if not updated:
            print(f"Minor update for {symbol}: No significant P/L change.")
    except Exception as e:
        print(f"Error in quote handler for {symbol}: {e}")

# Main function
async def main():
    try:
        # Pull all open positions
        all_positions = trading_client.get_all_positions()
        positions['all'] = all_positions
        positions['spreads'] = find_spreads(all_positions)
        
        # Check market hours
        if not is_market_open():
            print("Market is closed (Options: Mon-Fri, 9:30 AM - 4:00 PM ET).")
            print_positions(all_positions)
            print_spreads(positions['spreads'])
            print("Waiting for market to open before subscribing to real-time quotes.")
            return
        
        if not all_positions:
            print("No open positions found. Open some positions or spreads (e.g., bull calls) in paper trading and retry.")
            return
        
        if not positions['spreads']:
            print("No call spreads detected. Listing all positions for reference:")
            print_positions(all_positions)
            print("\nOpen some bull call spreads and retry.")
            return
        
        print(f"Found {len(positions['spreads'])} call spreads. Subscribing to quotes...")
        symbols_to_subscribe = set()
        for spread in positions['spreads'].values():
            symbols_to_subscribe.add(spread['long'].symbol)
            symbols_to_subscribe.add(spread['short'].symbol)
        
        # Subscribe to WebSocket for real-time quotes
        for symbol in symbols_to_subscribe:
            stream.subscribe_quotes(quote_handler, symbol)
        
        print("Monitoring real-time P/L for detected spreads... (Updates during market hours)")
        await stream.run()
    except Exception as e:
        print(f"Error in main loop: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped monitoring. Ensure API keys are set in 'alpaca_keys.txt' before sharing code!")
    except Exception as e:
        print(f"Fatal error: {e}")