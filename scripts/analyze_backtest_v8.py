import argparse
import json
import pandas as pd
import sys
import os

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from config import Config

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
            'pattern': entry.get('pattern_candle', {}).get('pattern', entry['signal'].get('pattern_name')), # Prefer pattern_candle
            'confidence': entry.get('pattern_candle', {}).get('confidence', entry['signal'].get('confidence')),
            'signal_strength': entry['signal'].get('signal_strength', 'N/A'), 
            'rsi_filter_passed': entry['signal'].get('rsi_filter_passed', False),
            'rsi': entry['technical'].get('rsi_value'),
            'trend_score': entry['technical'].get('trend_score'),
            'trend_status': entry['technical'].get('trend_status'),
            'limit_entry_price': entry['strategy_data'].get('limit_entry_price', None),
            'candle_high': entry.get('pattern_candle', {}).get('high', entry['strategy_data'].get('candle_high')), # Prefer pattern_candle
            'candle_low': entry.get('pattern_candle', {}).get('low', entry['strategy_data'].get('candle_low')),    # Prefer pattern_candle
            'outcome_open': entry['outcome_candle'].get('open'),
            'outcome_high': entry['outcome_candle'].get('high'),
            'outcome_low': entry['outcome_candle'].get('low'),
            'outcome_close': entry['outcome_candle'].get('close'),
            'direction': entry['signal'].get('direction'), # Added missing direction
            'symbol': entry['metadata'].get('symbol'),
            'source': entry['metadata'].get('source', 'IQOPTION'),
            'algo_version': entry['metadata'].get('algo_version')
        }
        flattened_data.append(flat_entry)
        
    return pd.DataFrame(flattened_data)

def classify_rsi(rsi_value):
    """Classifies RSI into zones."""
    if pd.isna(rsi_value):
        return "UNKNOWN"
    if rsi_value >= Config.RSI_OVERBOUGHT: # Default 75
        return "OVERBOUGHT"
    if rsi_value <= Config.RSI_OVERSOLD: # Default 25
        return "OVERSOLD"
    return "NEUTRAL"

def simulate_trade(row):
    """
    Simulates the trade execution based on Limit Entry logic.
    Returns: 'WIN', 'LOSS', 'NO_FILL'
    """
    pattern = row['pattern']
    limit_price = row['limit_entry_price']
    high = row['outcome_high']
    low = row['outcome_low']
    close = row['outcome_close']
    
    # Determine Trade Direction
    if pattern in ["SHOOTING_STAR", "INVERTED_HAMMER"]:
        direction = "PUT"
    elif pattern in ["HAMMER", "HANGING_MAN"]:
        direction = "CALL"
    else:
        return "UNKNOWN" # Should not happen based on current logic
    
    # Check Entry (Fill)
    filled = False
    if direction == "PUT":
        if high >= limit_price:
            filled = True
    elif direction == "CALL":
        if low <= limit_price:
            filled = True
            
    if not filled:
        return "NO_FILL"
    
    # Check Outcome
    if direction == "PUT":
        if close < limit_price:
            return "WIN"
        elif close > limit_price:
            return "LOSS"
        else:
            return "TIE"
    else: # CALL
        if close > limit_price:
            return "WIN"
        elif close < limit_price:
            return "LOSS"
        else:
            return "TIE"

def calculate_pnl(row, payout=0.85):
    """Calculates PnL for a single trade."""
    result = row['trade_result']
    if result == 'WIN':
        return payout
    elif result == 'LOSS':
        return -1.0
    elif result == 'TIE':
        return 0.0 # Refund
    return 0.0

def main():
    parser = argparse.ArgumentParser(description="Analyze Backtesting Results V8")
    parser.add_argument("--file", type=str, default="data/trading_signals_dataset_v8.jsonl", help="Path to input JSONL file")
    parser.add_argument("--symbol", type=str, help="Filter by Symbol (e.g., EURUSD)")
    parser.add_argument("--source", type=str, help="Filter by Source (e.g., IQOPTION)")
    parser.add_argument("--min_score", type=float, help="Filter by Min Trend Score")
    parser.add_argument("--entry_pct", type=float, default=0.5, help="Entry Price Percentage (0.5 = 50% Retracement)")
    
    args = parser.parse_args()
    
    print(f"Loading data from {args.file}...")
    df = load_data(args.file)
    
    # Recalculate Limit Entry Price based on requested percentage
    # Formula:
    # PUT: Low + (High - Low) * pct
    # CALL: High - (High - Low) * pct
    
    def recalculate_entry(row, pct):
        high = row.get('candle_high')
        low = row.get('candle_low')
        
        # Fallback for old datasets (should not happen if regenerated)
        if pd.isna(high) or pd.isna(low):
            # Try to get limit_entry_price if it exists (legacy)
            legacy_price = row.get('limit_entry_price')
            if not pd.isna(legacy_price):
                return legacy_price
            return 0.0 # Should not happen
            
        rng = high - low
        if row['direction'] == 'PUT':
            return low + (rng * pct)
        else: # CALL
            return high - (rng * pct)

    df['limit_entry_price'] = df.apply(lambda row: recalculate_entry(row, args.entry_pct), axis=1)
    
    print(f"Using Entry Percentage: {args.entry_pct*100}%")
    
    # Apply Filters
    if args.symbol:
        df = df[df['symbol'] == args.symbol]
    if args.source:
        df = df[df['source'] == args.source]
    if args.min_score is not None:
        df = df[df['trend_score'].abs() >= args.min_score]
        
    # Filter out NONE signal strength (User Request)
    df = df[df['signal_strength'] != 'NONE']
        
    if df.empty:
        print("No records found after filtering.")
        return

    print(f"Analyzing {len(df)} signals...")

    # 1. Classify RSI
    df['rsi_zone'] = df['rsi'].apply(classify_rsi)
    
    # 2. Simulate Trades
    df['trade_result'] = df.apply(simulate_trade, axis=1)
    
    # 3. Determine Trade Direction for Reporting
    def get_direction(pattern):
        if pattern in ["SHOOTING_STAR", "INVERTED_HAMMER"]: return "PUT"
        if pattern in ["HAMMER", "HANGING_MAN"]: return "CALL"
        return "UNKNOWN"
    
    df['direction'] = df['pattern'].apply(get_direction)
    
    # Round trend score for grouping
    df['score_rounded'] = df['trend_score'].round(1)

    # Filter out NONE signal strength (User Request)
    df_filtered = df[df['signal_strength'] != 'NONE']

    def generate_report(dataframe, title_suffix):
        print("\n" + "#"*80)
        print(f"REPORT: {title_suffix}")
        print("#"*80)
        
        if dataframe.empty:
            print("No data for this report.")
            return

        # =================================================================================
        # TABLE 1: GRANULAR ANALYSIS
        # =================================================================================
        group_cols = ['pattern', 'signal_strength', 'score_rounded', 'rsi_zone', 'direction']
        
        summary1 = dataframe.groupby(group_cols).agg(
            total_signals=('timestamp', 'count'),
            fills=('trade_result', lambda x: x.isin(['WIN', 'LOSS', 'TIE']).sum()),
            wins=('trade_result', lambda x: (x == 'WIN').sum()),
            losses=('trade_result', lambda x: (x == 'LOSS').sum()),
            ties=('trade_result', lambda x: (x == 'TIE').sum())
        ).reset_index()
        
        summary1['fill_rate_pct'] = (summary1['fills'] / summary1['total_signals'] * 100).round(1)
        summary1['tie_rate_pct'] = (summary1['ties'] / summary1['fills'] * 100).fillna(0).round(1)
        summary1['win_rate_pct'] = (summary1['wins'] / summary1['fills'] * 100).fillna(0).round(1)
        
        payout = 0.87
        summary1['est_pnl'] = (summary1['wins'] * payout) - summary1['losses']
        
        print("\n" + "="*80)
        print("TABLE 1: GRANULAR ANALYSIS (Pattern + Score + RSI)")
        print("="*80)
        summary1_sorted = summary1.sort_values(by=['win_rate_pct', 'fills'], ascending=False)
        
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(summary1_sorted.to_string(index=False))

        # =================================================================================
        # TABLE 2: STRATEGY SUMMARY
        # =================================================================================
        group_cols_2 = ['pattern', 'signal_strength', 'rsi_zone']
        
        summary2 = dataframe.groupby(group_cols_2).agg(
            total_entries=('trade_result', lambda x: x.isin(['WIN', 'LOSS', 'TIE']).sum()),
            wins=('trade_result', lambda x: (x == 'WIN').sum()),
            losses=('trade_result', lambda x: (x == 'LOSS').sum()),
            ties=('trade_result', lambda x: (x == 'TIE').sum())
        ).reset_index()
        
        summary2['tie_rate_pct'] = (summary2['ties'] / summary2['total_entries'] * 100).fillna(0).round(1)
        summary2['win_rate_pct'] = (summary2['wins'] / summary2['total_entries'] * 100).fillna(0).round(1)
        summary2['est_pnl'] = (summary2['wins'] * payout) - summary2['losses']
        
        summary2 = summary2[summary2['total_entries'] > 0]
        
        print("\n" + "="*80)
        print("TABLE 2: STRATEGY SUMMARY (Aggregated by Pattern & RSI)")
        print("="*80)
        summary2_sorted = summary2.sort_values(by=['win_rate_pct', 'total_entries'], ascending=False)
        print(summary2_sorted.to_string(index=False))
        
        # Global Stats
        total_fills = len(dataframe[dataframe['trade_result'].isin(['WIN', 'LOSS', 'TIE'])])
        total_wins = len(dataframe[dataframe['trade_result'] == 'WIN'])
        total_ties = len(dataframe[dataframe['trade_result'] == 'TIE'])
        global_wr = (total_wins / total_fills * 100) if total_fills > 0 else 0
        
        print("\n" + "="*80)
        print(f"GLOBAL STATS: {total_wins}/{total_fills} Wins ({global_wr:.2f}%) | Ties: {total_ties}")
        print("="*80)

    # REPORT 1: ALL SIGNALS (No RSI Filter)
    print("\n" + "="*80)
    print(" >>> REPORT 1: ALL SIGNALS (IGNORING RSI FILTER) <<<")
    print("="*80)
    generate_report(df_filtered, "ALL SIGNALS (No RSI Filter)")
    
    # REPORT 2: RSI FILTERED ONLY
    print("\n" + "="*80)
    print(" >>> REPORT 2: RSI FILTERED SIGNALS ONLY (Strategy Default) <<<")
    print("="*80)
    
    # Filter by rsi_filter_passed
    # Note: If the dataset was generated with the OLD script, this field might be missing or False.
    # But we updated load_data to default to False.
    # Wait, if we use old data, 'rsi_filter_passed' will be False (default) but they actually PASSED (because old script filtered).
    # However, we are regenerating data, so it's fine.
    
    df_rsi = df_filtered[df_filtered['rsi_filter_passed'] == True]
    generate_report(df_rsi, "RSI FILTERED SIGNALS")


if __name__ == "__main__":
    main()
