import os
import requests
import logging
import argparse
from typing import Optional

# 🔐 Load credentials from environment variables for security
API_KEY = os.getenv('ALPACA_API_KEY', 'your_api_key_here')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY', 'your_secret_key_here')

# 📜 Setup logging
logging.basicConfig(
    filename='close_mleg_spread.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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

def close_mleg_spread(long_symbol: str, short_symbol: str, qty: int, min_credit: float):
    """Submit an order to close a mleg option spread via REST API."""
    try:
        # Fetch quotes to calculate net credit
        long_quote = get_option_quote(long_symbol)
        short_quote = get_option_quote(short_symbol)
        if not long_quote or not short_quote:
            print(f"Cannot calculate closing price: Missing quotes for {long_symbol} or {short_symbol}")
            logging.warning(f"Cannot calculate closing price: Missing quotes for {long_symbol} or {short_symbol}")
            return

        # Calculate net credit as median (midpoint) of bid/ask
        long_mid = (long_quote['bp'] + long_quote['ap']) / 2
        short_mid = (short_quote['bp'] + short_quote['ap']) / 2
        net_credit = round(long_mid - short_mid, 2)
        # Enforce minimum credit if specified (e.g., breakeven)
        if min_credit > 0:
            net_credit = max(net_credit, min_credit)
        if net_credit <= 0:
            print(f"Invalid net credit for closing: ${net_credit:.2f}")
            logging.warning(f"Invalid net credit for closing: ${net_credit:.2f}")
            return

        # Submit closing spread order via REST API
        url = 'https://paper-api.alpaca.markets/v2/orders'
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': SECRET_KEY
        }
        payload = {
            'order_class': 'mleg',
            'qty': qty,
            'type': 'limit',
            'limit_price': f"{net_credit:.2f}",
            'time_in_force': 'day',
            'side': 'sell',  # Sell the spread to close (receive credit)
            'legs': [
                {
                    'symbol': long_symbol,
                    'ratio_qty': 1,
                    'side': 'sell',
                    'position_intent': 'sell_to_close'  # Close the long leg
                },
                {
                    'symbol': short_symbol,
                    'ratio_qty': 1,
                    'side': 'buy',
                    'position_intent': 'buy_to_close'  # Close the short leg
                }
            ]
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        order_data = response.json()
        order_id = order_data.get('id')
        if not order_id:
            print(f"Closing order submission failed: No order ID returned: {order_data}")
            logging.error(f"Closing order submission failed: No order ID returned: {order_data}")
            return
        print(f"Submitted closing mleg spread: Sell {long_symbol} at ${long_mid:.2f}, Buy {short_symbol} at ${short_mid:.2f}, Net credit ${net_credit:.2f}, Order ID: {order_id}")
        logging.info(f"Submitted closing mleg spread: Sell {long_symbol} at ${long_mid:.2f}, Buy {short_symbol} at ${short_mid:.2f}, Net credit ${net_credit:.2f}, Order ID: {order_id}")

    except Exception as e:
        print(f"Error submitting closing order: {e}")
        logging.error(f"Error submitting closing order: {e}")

def main():
    """Main function to close a mleg option spread."""
    parser = argparse.ArgumentParser(description="Close a mleg option spread.")
    parser.add_argument("--option1", help="Long option symbol (e.g., NFLX250815C01205000)")
    parser.add_argument("--option2", help="Short option symbol (e.g., NFLX250815C01210000)")
    parser.add_argument("--qty", type=int, default=1, help="Number of spreads to close (default: 1)")
    parser.add_argument("--min-credit", type=float, default=0.0, help="Minimum net credit (default: 0.0)")
    args = parser.parse_args()

    # Prompt for inputs if not provided via args
    long_symbol = args.option1 or input("Enter long option symbol (e.g., NFLX250815C01205000): ")
    short_symbol = args.option2 or input("Enter short option symbol (e.g., NFLX250815C01210000): ")

    close_mleg_spread(
        long_symbol=long_symbol,
        short_symbol=short_symbol,
        qty=args.qty,
        min_credit=args.min-credit
    )

if __name__ == "__main__":
    main()