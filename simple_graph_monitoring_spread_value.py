import alpaca.trading.client as trading
import alpaca.data.requests as data_req
import alpaca.trading.requests as trading_req
import alpaca.trading.enums as enums
from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
import pandas as pd
from datetime import datetime, timedelta
import sys
import logging
import time
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

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
EXPIRATION = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')  # Try 30 days first
MA_PERIOD = 10  # Default MA(10)

spread_prices = []  # Stateful list for spread prices
ma_values = []  # Stateful list for MA(10)

def parse_strike(contract_symbol):
    """Parse strike price from option contract symbol (last 8 digits / 1000)."""
    if len(contract_symbol) < 9 or contract_symbol[-9] != 'C':  # Enforce calls only
        logging.warning(f"Skipping non-call contract: {contract_symbol}")
        return None
    try:
        strike_str = contract_symbol[-8:]
        return float(int(strike_str) / 1000)
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
        strikes = sorted(set(parse_strike(k) for k in chain.keys() if parse_strike(k) is not None))
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
    """Fetch stock snapshot."""
    try:
        snapshot = stock_data_client.get_stock_snapshot(
            data_req.StockSnapshotRequest(symbol_or_symbols=[symbol])
        )
        return snapshot[symbol]
    except Exception as e:
        logging.error(f"Error fetching stock snapshot: {e}")
        return None

def get_option_snapshot(symbol, contract_symbols, timestamp=None):
    """Fetch option snapshot for specific contracts at a given timestamp."""
    try:
        request = data_req.OptionSnapshotRequest(symbol_or_symbols=contract_symbols)
        if timestamp:
            request.start = timestamp
            request.end = timestamp + timedelta(minutes=1)
        snapshots = option_data_client.get_option_snapshot(request)
        return snapshots
    except Exception as e:
        logging.error(f"Error fetching option snapshot: {e}")
        return None

def find_initial_spread():
    """Find the initial ATM bull call spread contracts with fallback to soonest expiration."""
    stock_snapshot = get_stock_snapshot(SYMBOL)
    if not stock_snapshot:
        print("Failed to retrieve stock snapshot. Exiting.")
        sys.exit(1)
    stock_price = stock_snapshot.latest_trade.price
    
    # Try specified expiration first
    strike_min = stock_price - 10.0
    strike_max = stock_price + 10.0
    strikes = get_strikes(SYMBOL, EXPIRATION, OPTION_TYPE, strike_min, strike_max)
    
    # Fallback to all contracts if no strikes found
    if not strikes:
        print("Falling back to all expirations...")
        chain = get_option_chain(SYMBOL, OPTION_TYPE)
        if not chain:
            print("Failed to retrieve option chain. Exiting.")
            sys.exit(1)
        
        data = []
        for k, v in chain.items():
            strike = parse_strike(k)
            exp = parse_expiration(k)
            if strike is not None and exp is not None:
                data.append({
                    'symbol': k,
                    'strike': strike,
                    'expiration': exp
                })
        
        df = pd.DataFrame(data)
        if df.empty:
            print("No suitable contracts found.")
            sys.exit(1)
        
        # Group by expiration and find soonest with at least 2 contracts
        df = df.sort_values('expiration')
        grouped = df.groupby('expiration')
        soonest_exp = None
        for exp, group in grouped:
            if len(group) >= 2:
                soonest_exp = exp
                df_group = group
                break
        
        if soonest_exp is None:
            print("No expiration found with enough contracts. Exiting.")
            sys.exit(1)
        
        strikes = sorted(set(df_group['strike']))
        if not strikes:
            print("No suitable strikes found in fallback. Exiting.")
            sys.exit(1)
    
    long_strike, short_strike = find_nearest_strikes(strikes, stock_price)
    if not long_strike or not short_strike:
        print("No valid long/short strikes found. Exiting.")
        sys.exit(1)
    
    # Fetch chain for the chosen expiration (or fallback)
    chain = get_option_chain(SYMBOL, OPTION_TYPE, soonest_exp if 'soonest_exp' in locals() else datetime.strptime(EXPIRATION, '%Y-%m-%d'))
    if not chain:
        print("Failed to retrieve option chain. Exiting.")
        sys.exit(1)
    
    data = []
    for k, v in chain.items():
        strike = parse_strike(k)
        if strike is not None and v.latest_quote.bid_price > 0:  # Skip illiquid contracts
            data.append({
                'symbol': k,
                'strike': strike,
                'expiration': parse_expiration(k),
                'bid': v.latest_quote.bid_price,
                'ask': v.latest_quote.ask_price
            })
    
    df = pd.DataFrame(data)
    if df.empty:
        print("No suitable spread found.")
        sys.exit(1)
    
    long_row = df[df['strike'] == long_strike]
    short_row = df[df['strike'] == short_strike]
    
    if long_row.empty or short_row.empty:
        print("No contracts found for long/short strikes. Exiting.")
        sys.exit(1)
    
    long_contract = long_row.iloc[0]['symbol']
    short_contract = short_row.iloc[0]['symbol']
    
    # Verify same expiration
    long_exp = parse_expiration(long_contract)
    short_exp = parse_expiration(short_contract)
    if long_exp != short_exp:
        print(f"Error: Mismatched expirations ({long_exp} vs {short_exp}). Exiting.")
        sys.exit(1)
    
    print(f"Monitoring Bull Call Spread: Long {long_contract}, Short {short_contract}")
    return long_contract, short_contract

def get_spread_price(long_contract, short_contract, timestamp=None):
    """Fetch current or historical spread price (long ask - short bid)."""
    snapshots = get_option_snapshot(SYMBOL, [long_contract, short_contract], timestamp)
    if not snapshots:
        logging.warning("Failed to retrieve option snapshots.")
        return None
    
    long_data = snapshots.get(long_contract)
    short_data = snapshots.get(short_contract)
    
    if not long_data or not short_data:
        logging.warning("Incomplete option data.")
        return None
    
    spread_price = long_data.latest_quote.ask_price - short_data.latest_quote.bid_price
    logging.debug(f"Spread price: {spread_price} (Long ask: {long_data.latest_quote.ask_price}, Short bid: {short_data.latest_quote.bid_price})")
    return spread_price

def update_graph(frame):
    """Update the graph every minute with new spread price and MA(10)."""
    current_time = datetime.now()
    spread_price = get_spread_price(long_contract, short_contract)
    if spread_price is not None:
        spread_prices.append(spread_price)
        if len(spread_prices) >= MA_PERIOD:
            ma = pd.Series(spread_prices).rolling(window=MA_PERIOD).mean().iloc[-1]
            ma_values.append(ma)
        else:
            ma_values.append(None)  # No MA until 10 points
        logging.debug(f"Spread prices: {len(spread_prices)}, MA values: {len(ma_values)}")
    
    ax.clear()
    ax.plot(spread_prices, label='Spread Price', color='b')
    if ma_values and ma_values[-1] is not None:  # Only plot MA when calculated
        ax.plot(range(MA_PERIOD-1, len(ma_values) + MA_PERIOD - 1), ma_values, label='MA(10)', color='r', linestyle='--')
    ax.set_xlabel('Minutes')
    ax.set_ylabel('Spread Price ($)')
    ax.set_title(f'Live {SYMBOL} Bull Call Spread Monitor')
    ax.legend()
    ax.grid(True)

# Initial spread setup
long_contract, short_contract = find_initial_spread()

# Pre-populate with historical snapshots (last 10 minutes)
current_time = datetime.now()
for i in range(10, 0, -1):  # Back 10 minutes
    past_time = current_time - timedelta(minutes=i)
    spread_price = get_spread_price(long_contract, short_contract, past_time)
    if spread_price is not None:
        spread_prices.append(spread_price)

if len(spread_prices) >= MA_PERIOD:
    ma = pd.Series(spread_prices).rolling(window=MA_PERIOD).mean().iloc[-1]
    ma_values.extend([None] * (len(spread_prices) - MA_PERIOD) + [ma])
else:
    ma_values.extend([None] * len(spread_prices))

# Setup graph
fig, ax = plt.subplots()
ani = FuncAnimation(fig, update_graph, interval=60000, cache_frame_data=False)  # Update every 60 seconds (1 minute)

plt.show()