import os
import requests
import logging
from typing import Optional
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta

# 🔐 Load credentials from environment variables
API_KEY = os.getenv('ALPACA_API_KEY', 'your_api_key_here')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY', 'your_secret_key_here')

# 📜 Setup basic logging
logging.basicConfig(
    filename='option_spread.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 🧠 Initialize data client (for stock price)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

def get_current_price(symbol: str) -> float:
    """Fetch the latest closing price for the given symbol."""
    try:
        bar_request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Day,
            start=datetime.now() - timedelta(days=5),
            end=datetime.now()
        )
        bars = data_client.get_stock_bars(bar_request)
        if not bars[symbol]:
            raise ValueError(f"No price data for {symbol}")
        price = bars[symbol][-1].close
        logging.info(f"Current price for {symbol}: ${price:.2f}")
        return price
    except Exception as e:
        logging.error(f"Error fetching price for {symbol}: {e}")
        print(f"Error fetching price for {symbol}: {e}")
        return 0.0

def get_next_friday_expiration() -> str:
    """Calculate the next Friday's date for option expiration."""
    today = datetime.now()
    days_ahead = 4 - today.weekday()  # 4 is Friday
    if days_ahead <= 0:
        days_ahead += 7
    next_friday = today + timedelta(days=days_ahead)
    expiration = next_friday.strftime("%Y-%m-%d")
    logging.info(f"Using expiration: {expiration}")
    return expiration

def get_option_contracts(symbol: str, expiration: str, option_type: str, strike_min: float, strike_max: float) -> list:
    """Fetch option contracts via REST API."""
    try:
        url = 'https://paper-api.alpaca.markets/v2/options/contracts'
        params = {
            'underlying_symbols': symbol,
            'expiration_date': expiration,
            'type': option_type,
            'strike_price_gte': str(strike_min),
            'strike_price_lte': str(strike_max)
        }
        headers = {
            'accept': 'application/json',
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': SECRET_KEY
        }
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        contracts = data.get('option_contracts', [])
        logging.info(f"Raw contracts response for {symbol}: {len(contracts)} contracts")
        contracts = [c for c in contracts if c['underlying_symbol'] == symbol]
        if not contracts:
            logging.warning(f"No {option_type} contracts found for {symbol} on {expiration}")
            print(f"No {option_type} contracts found for {symbol} on {expiration}")
        return contracts
    except Exception as e:
        logging.error(f"Error fetching {option_type} contracts for {symbol}: {e}")
        print(f"Error fetching {option_type} contracts for {symbol}: {e}")
        return []

def get_option_quote(symbol: str) -> Optional[dict]:
    """Fetch the latest quote for an option contract via REST API."""
    try:
        url = f'https://data.alpaca.markets/v1beta1/options/snapshots?symbols={symbol}&feed=opra'
        headers = {
            'accept': 'application/json',
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': SECRET_KEY
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        snapshot = data.get('snapshots', {}).get(symbol)
        if not snapshot:
            raise ValueError(f"No snapshot found for {symbol}")
        logging.info(f"Snapshot for {symbol}: {snapshot['latestQuote']}")
        return snapshot['latestQuote']
    except Exception as e:
        logging.error(f"Error fetching snapshot for {symbol}: {e}")
        print(f"Error fetching snapshot for {symbol}: {e}")
        return None

def get_strikes(symbol: str, expiration: str, option_type: str, strike_min: float, strike_max: float) -> list:
    """Fetch option strikes using REST API."""
    contracts = get_option_contracts(symbol, expiration, option_type, strike_min, strike_max)
    strikes = sorted(set(float(c['strike_price']) for c in contracts))
    if not strikes:
        logging.warning(f"No {option_type} strikes found for {symbol} on {expiration}")
        print(f"No {option_type} strikes found for {symbol} on {expiration}")
    return strikes

def find_nearest_strikes(strikes: list, price: float) -> tuple:
    """Find the nearest strikes below and above the given price."""
    below = max([s for s in strikes if s < price], default=None)
    above = min([s for s in strikes if s > price], default=None)
    return below, above

def place_spread_order(symbol: str, buy_strike: float, sell_strike: float, expiration: str, option_type: str):
    """Place a vertical call spread order (buy lower strike, sell higher strike) via REST API."""
    try:
        # Fetch contracts
        contracts = get_option_contracts(symbol, expiration, option_type, buy_strike, buy_strike)
        buy_contract = next((c for c in contracts if float(c['strike_price']) == buy_strike), None)
        contracts = get_option_contracts(symbol, expiration, option_type, sell_strike, sell_strike)
        sell_contract = next((c for c in contracts if float(c['strike_price']) == sell_strike), None)
        if not buy_contract or not sell_contract:
            print(f"Cannot place spread: Invalid contract(s) for strikes {buy_strike}/{sell_strike}")
            logging.warning(f"Cannot place spread: Invalid contract(s) for strikes {buy_strike}/{sell_strike}")
            return

        buy_symbol = buy_contract['symbol']
        sell_symbol = sell_contract['symbol']

        # Fetch quotes to calculate spread price
        buy_quote = get_option_quote(buy_symbol)
        sell_quote = get_option_quote(sell_symbol)
        if not buy_quote or not sell_quote:
            print(f"Cannot calculate spread price: Missing quotes for {buy_symbol} or {sell_symbol}")
            logging.warning(f"Cannot calculate spread price: Missing quotes for {buy_symbol} or {sell_symbol}")
            return

        # Calculate spread price (net debit)
        buy_price = buy_quote['ap']  # Ask price for buy
        sell_price = sell_quote['bp']  # Bid price for sell
        spread_price = round(buy_price - sell_price, 2)
        if spread_price <= 0:
            print(f"Invalid spread price: ${spread_price:.2f}")
            logging.warning(f"Invalid spread price: ${spread_price:.2f}")
            return

        # Submit spread order via REST API
        url = 'https://paper-api.alpaca.markets/v2/orders'
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': SECRET_KEY
        }
        payload = {
            'order_class': 'mleg',
            'qty': 1,
            'type': 'limit',
            'limit_price': f"{spread_price:.2f}",
            'time_in_force': 'day',
            'legs': [
                {
                    'symbol': buy_symbol,
                    'ratio_qty': 1,
                    'side': 'buy',
                    'position_intent': 'buy_to_open'
                },
                {
                    'symbol': sell_symbol,
                    'ratio_qty': 1,
                    'side': 'sell',
                    'position_intent': 'sell_to_open'
                }
            ]
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        order_data = response.json()
        order_id = order_data.get('id')
        if not order_id:
            print(f"Order submission failed for {symbol}: No order ID returned: {order_data}")
            logging.error(f"Order submission failed for {symbol}: No order ID returned: {order_data}")
            return
        print(f"Placed vertical {option_type} spread: Buy {buy_symbol} at ${buy_price:.2f}, Sell {sell_symbol} at ${sell_price:.2f}, Net debit ${spread_price:.2f}, Order ID: {order_id}")
        logging.info(f"Placed vertical {option_type} spread: Buy {buy_symbol} at ${buy_price:.2f}, Sell {sell_symbol} at ${sell_price:.2f}, Net debit ${spread_price:.2f}, Order ID: {order_id}")

    except Exception as e:
        print(f"Error placing spread order for {symbol}: {e}")
        logging.error(f"Error placing spread order for {symbol}: {e}")

def main(symbol: str = "TSLA"):
    """Main function to fetch option strikes and place a vertical call spread."""
    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        return
    print(f"\nApproximate current price: {current_price}")
    
    # Get next Friday's expiration
    expiration = get_next_friday_expiration()
    print(f"Using expiration: {expiration}")
    
    # Calculate strike range
    base_strike = round(current_price / 5) * 5
    strike_min = base_strike - 50
    strike_max = base_strike + 50
    
    # Get call strikes
    call_strikes = get_strikes(symbol, expiration, "call", strike_min, strike_max)
    if not call_strikes:
        return
    print(f"All call strikes returned: {call_strikes}")
    
    # Find nearest strikes
    below, above = find_nearest_strikes(call_strikes, current_price)
    print(f"Call strikes near {current_price}:\n  Just below: {below}\n  Just above: {above}")
    
    # Place a vertical call spread (buy strike just above, sell next higher strike)
    if above and len([s for s in call_strikes if s > above]) > 0:
        sell_strike = min([s for s in call_strikes if s > above], default=None)
        if sell_strike:
            place_spread_order(symbol, above, sell_strike, expiration, "call")

if __name__ == "__main__":
    main()