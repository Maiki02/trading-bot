import argparse
import json
import pandas as pd
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def load_data(file_path):
    """Loads JSONL data into a Pandas DataFrame."""
    data = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        sys.exit(1)
    
    if not data:
        print("Error: No data found in file.")
        sys.exit(1)
        
    # Flatten the nested structure
    flattened_data = []
    for entry in data:
        flat_entry = {
            'timestamp': entry['metadata'].get('timestamp'),
            'datetime': entry['metadata'].get('datetime'),
            'pattern': entry['signal'].get('pattern_name'),
            'signal_strength': entry['signal'].get('signal_strength', 'N/A'),
            'rsi': entry['technical'].get('rsi_value'),
            'rsi_filter_passed': entry['signal'].get('rsi_filter_passed', False),
            'limit_entry_price': entry['strategy_data'].get('limit_entry_price'),
            'outcome_close': entry['outcome_candle'].get('close'),
            'outcome_high': entry['outcome_candle'].get('high'),
            'outcome_low': entry['outcome_candle'].get('low'),
            'direction': entry['signal'].get('direction')
        }
        flattened_data.append(flat_entry)
        
    return pd.DataFrame(flattened_data)

def main():
    parser = argparse.ArgumentParser(description="Find Pattern Occurrences")
    parser.add_argument("--file", type=str, default="data/trading_signals_dataset_v8.jsonl", help="Path to input JSONL file")
    parser.add_argument("--pattern", type=str, required=True, help="Pattern Name (e.g., HANGING_MAN)")
    parser.add_argument("--strength", type=str, required=True, help="Signal Strength (e.g., LOW, MEDIUM, HIGH)")
    
    args = parser.parse_args()
    
    print(f"Searching for {args.pattern} with strength {args.strength} in {args.file}...")
    
    df = load_data(args.file)
    
    # Filter
    filtered_df = df[
        (df['pattern'] == args.pattern) & 
        (df['signal_strength'] == args.strength)
    ]
    
    if filtered_df.empty:
        print("No matches found.")
        return
        
    print(f"\nFound {len(filtered_df)} matches:")
    print("="*100)
    print(f"{'DATETIME':<25} | {'RSI':<8} | {'RSI OK?':<8} | {'FILLED?':<8} | {'RESULT':<8} | {'ENTRY':<8} | {'CLOSE':<8}")
    print("-" * 100)
    
    for _, row in filtered_df.iterrows():
        # Check Fill
        filled = False
        limit_price = row['limit_entry_price']
        outcome_close = row['outcome_close']
        
        # We need outcome high/low to check fill, but load_data didn't load them.
        # Wait, load_data needs to be updated to load outcome_high and outcome_low.
        # Let's assume we update load_data first.
        outcome_high = row.get('outcome_high', 0)
        outcome_low = row.get('outcome_low', 0)
        
        if row['direction'] == 'PUT':
            if outcome_high >= limit_price: filled = True
        else: # CALL
            if outcome_low <= limit_price: filled = True
            
        # Estimate Result
        if not filled:
            result = "NO FILL"
        else:
            result = "TIE"
            if row['direction'] == 'PUT':
                if outcome_close < limit_price: result = "WIN"
                elif outcome_close > limit_price: result = "LOSS"
            else: # CALL
                if outcome_close > limit_price: result = "WIN"
                elif outcome_close < limit_price: result = "LOSS"
            
        print(f"{row['datetime']:<25} | {row['rsi']:<8.2f} | {str(row['rsi_filter_passed']):<8} | {str(filled):<8} | {result:<8} | {limit_price:<8.5f} | {outcome_close:<8.5f}")
        
    print("="*80)

if __name__ == "__main__":
    main()
