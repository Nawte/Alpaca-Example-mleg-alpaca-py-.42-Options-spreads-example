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

# Load API keys (using lines 0 and 1 for paper key/secret)
def read_api_keys():
    try:
        with open('H:\\mnt\\alpaca_keys.txt', 'r') as f:
            lines = f.readlines()
            return lines[0].strip(), lines[1].strip()
    except Exception as e:
        logging.error(f"Error reading API keys: {e}")
        sys.exit(1)

# Initialize Alpaca clients
PAPER_API_KEY, PAPER_SECRET_KEY = read_api_keys()
trading_client = trading.TradingClient(PAPER_API_KEY, PAPER_SECRET_KEY, paper=True)
stock_data_client = StockHistoricalDataClient(PAPER_API_KEY, PAPER_SECRET_KEY)
option_data_client = OptionHistoricalDataClient(PAPER_API_KEY, PAPER_SECRET_KEY)

SYMBOL = 'BP'
STRIKE_SPREAD = 2.5  # Desired difference between strikes
CONTRACT_TYPE = 'call'

def parse_strike(contract_symbol):
    """Parse strike price from option contract symbol (last 8 digits / 1000)."""
    if len(contract_symbol) < 9 or contract_symbol[-9] != 'C':  # Enforce calls only
        logging.warning(f"Skipping non-call contract: {contract_symbol}")
        return None
    try:
        strike_str = contract_symbol[-8:]
        return int(strike_str) / 1000
    except ValueError:
        logging.warning(f"Failed to parse strike from {contract_symbol}")
        return None

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

def find_closest_bull_spread(stock_price, chain, strike_spread):
    """Find the closest bull call spread in the soonest expiration with contracts."""
    if not chain:
        return None, None, None
    
    data = []
    for k, v in chain.items():
        strike = parse_strike(k)
        exp = parse_expiration(k)
        if strike is not None and exp is not None:
            data.append({
                'symbol': k,
                'strike': strike,
                'expiration': exp,
                'bid': v.latest_quote.bid_price,
                'ask': v.latest_quote.ask_price
            })
    
    df = pd.DataFrame(data)
    if df.empty:
        return None, None, None
    
    # Group by expiration and find the soonest with at least 2 contracts
    df = df.sort_values('expiration')
    grouped = df.groupby('expiration')
    soonest_exp = None
    for exp, group in grouped:
        if len(group) >= 2:
            soonest_exp = exp
            df_group = group
            break
    
    if soonest_exp is None:
        logging.warning("No expiration found with enough contracts.")
        return None, None, None
    
    # Find closest strike to stock price in this group
    df_group['strike_diff'] = abs(df_group['strike'] - stock_price)
    long_strike = df_group.loc[df_group['strike_diff'].idxmin()]
    
    # Find corresponding short strike (higher by STRIKE_SPREAD)
    short_candidates = df_group[df_group['strike'] >= long_strike['strike'] + strike_spread]
    if short_candidates.empty:
        logging.warning(f"No short strike found for spread of {strike_spread}.")
        return None, None, None
    
    short_strike = short_candidates.iloc[
        abs(short_candidates['strike'] - (long_strike['strike'] + strike_spread)).argmin()
    ]
    
    spread_cost = (long_strike['ask'] - short_strike['bid']) * 100  # Per contract
    return long_strike['symbol'], short_strike['symbol'], spread_cost

def main():
    print(f"Bull Call Spread for {SYMBOL}:")
    
    # Try option chain first
    chain = None
    stock_price = None
    expiration = (datetime.now() + timedelta(days=30)).date()  # Nearest expiration within 30 days
    
    try:
        chain = get_option_chain(SYMBOL, CONTRACT_TYPE, expiration)
        if chain and len(chain) > 0:
            stock_snapshot = get_stock_snapshot(SYMBOL)
            stock_price = stock_snapshot.latest_trade.price if stock_snapshot else None
    except Exception as e:
        logging.error(f"Primary method failed: {e}")
    
    # Fallback to stock snapshot method
    if not chain or not stock_price:
        print("Falling back to stock snapshot method...")
        stock_snapshot = get_stock_snapshot(SYMBOL)
        if not stock_snapshot:
            print("Failed to retrieve stock snapshot. Exiting.")
            return
        
        stock_price = stock_snapshot.latest_trade.price
        chain = get_option_chain(SYMBOL, CONTRACT_TYPE)
        if not chain:
            print("Failed to retrieve option chain. Exiting.")
            return
    
    long_contract, short_contract, spread_cost = find_closest_bull_spread(
        stock_price, chain, STRIKE_SPREAD
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
    
    # Verify same expiration for mleg order
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
    
    # Submit paper trade
    order = trading_req.LimitOrderRequest(
        qty=1,
        side=enums.OrderSide.BUY,
        time_in_force=enums.TimeInForce.DAY,
        limit_price=spread_cost/100,
        order_class=enums.OrderClass.MLEG,
        legs=[
            trading_req.OptionLegRequest(symbol=long_contract, side=enums.OrderSide.BUY, ratio_qty=1),
            trading_req.OptionLegRequest(symbol=short_contract, side=enums.OrderSide.SELL, ratio_qty=1)
        ]
    )
    try:
        response = trading_client.submit_order(order)
        print(f"Order submitted: {response.id}")
        logging.info(f"Order details: {response}")
    except Exception as e:
        logging.error(f"Order submission failed: {e}")

if __name__ == "__main__":
    main()