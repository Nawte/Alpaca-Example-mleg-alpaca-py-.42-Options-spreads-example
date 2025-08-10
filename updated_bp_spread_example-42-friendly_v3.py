import alpaca.trading.client as trading
import alpaca.data.requests as data_req
import alpaca.trading.requests as trading_req
import alpaca.trading.enums as enums
from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
import pandas as pd
from datetime import datetime, timedelta
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Alpaca API keys (replace with your paper trading keys)
Alpaca_Key = 'Your-Alpaca-Key'
Alpaca_Secret = 'Your-Alpaca-Secret'

# Initialize Alpaca clients
try:
    trading_client = trading.TradingClient(Alpaca_Key, Alpaca_Secret, paper=True)
    stock_data_client = StockHistoricalDataClient(Alpaca_Key, Alpaca_Secret)
    option_data_client = OptionHistoricalDataClient(Alpaca_Key, Alpaca_Secret)
except Exception as e:
    logging.error(f"Error initializing Alpaca clients: {e}")
    sys.exit(1)

SYMBOL = 'BP'
OPTION_TYPE = 'call'
EXPIRATION = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')  # Nearest expiration within 30 days

def parse_expiration(contract_symbol):
    """Parse expiration date from option contract symbol (first 6 digits: YYMMDD)."""
    if len(contract_symbol) < 15:
        logging.warning(f"Invalid contract symbol: {contract_symbol}")
        return None
    try:
        exp_str = contract_symbol[2:8]  # Skip symbol, e.g., '250815' for BP250815C...
        return datetime.strptime(exp_str, '%y%m%d').date()
    except ValueError:
        logging.warning(f"Failed to parse expiration from {contract_symbol}")
        return None

def get_strikes(symbol: str, expiration: str, option_type: str, strike_min: float, strike_max: float) -> list:
    """Fetch option strikes using OptionChainRequest within strike range."""
    try:
        request = data_req.OptionChainRequest(
            underlying_symbol=symbol,
            contract_type=option_type,
            expiration_date=expiration,
            strike_price_gte=strike_min,
            strike_price_lte=strike_max
        )
        chain = option_data_client.get_option_chain(request)
        strikes = sorted(set(float(v.strike_price) for k, v in chain.items() if v.strike_price is not None))
        if not strikes:
            logging.warning(f"No {option_type} strikes found for {symbol} on {expiration} between {strike_min} and {strike_max}")
            print(f"No {option_type} strikes found for {symbol} on {expiration} between {strike_min} and {strike_max}")
        return strikes
    except Exception as e:
        logging.error(f"Error fetching option chain: {e}")
        return []

def find_nearest_strikes(strikes: list, price: float) -> tuple:
    """Find the nearest strikes below and above the given price."""
    below = max([s for s in strikes if s < price], default=None)
    above = min([s for s in strikes if s > price], default=None)
    return below, above

def get_option_chain(symbol, contract_type, expiration_date=None):
    """Fetch option chain for given symbol and contract type."""
    try:
        if expiration_date:
            expiration_date = expiration_date.strftime('%Y-%m-%d')
        request = data_req.OptionChainRequest(
            underlying_symbol=symbol,
            contract_type=contract_type,
            expiration_date=expiration_date
        )
        chain = option_data_client.get_option_chain(request)
        return chain
    except Exception as e:
        logging.error(f"Error fetching option chain: {e}")
        return None

def get_stock_snapshot(symbol):
    """Fetch stock snapshot as fallback."""
    try:
        snapshot = stock_data_client.get_stock_snapshot(
            data_req.StockSnapshotRequest(symbol_or_symbols=[symbol])
        )
        return snapshot[symbol]
    except Exception as e:
        logging.error(f"Error fetching stock snapshot: {e}")
        return None

def get_option_snapshot(symbol, contract_symbols):
    """Fetch option snapshots for specific contracts."""
    try:
        request = data_req.OptionSnapshotRequest(symbol_or_symbols=contract_symbols)
        snapshots = option_data_client.get_option_snapshot(request)
        return snapshots
    except Exception as e:
        logging.error(f"Error fetching option snapshots: {e}")
        return None

def find_closest_bull_spread(stock_price, chain, long_strike, short_strike):
    """Find the bull call spread for given long and short strikes."""
    if not chain:
        return None, None, None
    
    data = []
    for k, v in chain.items():
        strike = v.strike_price
        if strike is not None:
            data.append({
                'symbol': k,
                'strike': float(strike),
                'expiration': parse_expiration(k),
                'bid': v.latest_quote.bid_price,
                'ask': v.latest_quote.ask_price
            })
    
    df = pd.DataFrame(data)
    if df.empty:
        return None, None, None
    
    # Filter for exact long and short strikes
    long_row = df[df['strike'] == long_strike]
    short_row = df[df['strike'] == short_strike]
    
    if long_row.empty or short_row.empty:
        logging.warning(f"No contracts found for long strike {long_strike} or short strike {short_strike}")
        return None, None, None
    
    long_strike = long_row.iloc[0]
    short_strike = short_row.iloc[0]
    
    # Verify same expiration
    if long_strike['expiration'] != short_strike['expiration']:
        logging.warning(f"Mismatched expirations: {long_strike['expiration']} vs {short_strike['expiration']}")
        return None, None, None
    
    spread_cost = (long_strike['ask'] - short_strike['bid']) * 100  # Per contract
    return long_strike['symbol'], short_strike['symbol'], spread_cost

def main():
    print(f"Bull Call Spread for {SYMBOL}:")
    
    # Get stock price
    stock_snapshot = get_stock_snapshot(SYMBOL)
    if not stock_snapshot:
        print("Failed to retrieve stock snapshot. Exiting.")
        return
    stock_price = stock_snapshot.latest_trade.price
    
    # Get strikes within a range around stock price
    strike_min = stock_price - 10.0
    strike_max = stock_price + 10.0
    strikes = get_strikes(SYMBOL, EXPIRATION, OPTION_TYPE, strike_min, strike_max)
    
    if not strikes:
        print("No suitable strikes found. Exiting.")
        return
    
    # Find nearest strikes
    long_strike, short_strike = find_nearest_strikes(strikes, stock_price)
    if not long_strike or not short_strike:
        print("No valid long/short strikes found. Exiting.")
        return
    
    # Fetch option chain for the specific expiration
    chain = get_option_chain(SYMBOL, OPTION_TYPE, datetime.strptime(EXPIRATION, '%Y-%m-%d'))
    if not chain:
        print("Failed to retrieve option chain. Exiting.")
        return
    
    long_contract, short_contract, spread_cost = find_closest_bull_spread(
        stock_price, chain, long_strike, short_strike
    )
    
    if not long_contract or not short_contract:
        print("No suitable spread found.")
        return
    
    # Fetch snapshots for exact contract details
    snapshots = get_option_snapshot(SYMBOL, [long_contract, short_contract])
    
    if not snapshots:
        print("Failed to retrieve option snapshots.")
        return
    
    long_data = snapshots.get(long_contract)
    short_data = snapshots.get(short_contract)
    
    if not long_data or not short_data:
        print("Incomplete option data.")
        return
    
    # Verify same expiration
    long_exp = parse_expiration(long_contract)
    short_exp = parse_expiration(short_contract)
    if long_exp != short_exp:
        print(f"Error: Mismatched expirations ({long_exp} vs {short_exp}). Cannot place mleg order.")
        return
    
    print(f"Stock Price: ${stock_price:.2f}")
    print(f"Buy Call (Long): {long_contract} Bid: ${long_data.latest_quote.bid_price:.2f}, Ask: ${long_data.latest_quote.ask_price:.2f}")
    print(f"Sell Call (Short): {short_contract} Bid: ${short_data.latest_quote.bid_price:.2f}, Ask: ${short_data.latest_quote.ask_price:.2f}")
    print(f"Spread Cost (per contract): ${spread_cost/100:.2f}")
    print(f"Total Cost (for 1 contract(s)): ${spread_cost:.2f}")
    
    # Uncomment to place a paper trade (TEST CAREFULLY!)
    # order = trading_req.LimitOrderRequest(
    #     qty=1,
    #     side=enums.OrderSide.BUY,
    #     time_in_force=enums.TimeInForce.DAY,
    #     limit_price=spread_cost/100,
    #     order_class=enums.OrderClass.MLEG,
    #     legs=[
    #         trading_req.OptionLegRequest(symbol=long_contract, side=enums.OrderSide.BUY, ratio_qty=1),
    #         trading_req.OptionLegRequest(symbol=short_contract, side=enums.OrderSide.SELL, ratio_qty=1)
    #     ]
    # )
    # try:
    #     response = trading_client.submit_order(order)
    #     print(f"Order submitted: {response.id}")
    #     logging.info(f"Order details: {response}")
    # except Exception as e:
    #     logging.error(f"Order submission failed: {e}")

if __name__ == "__main__":
    main()