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
            'timestamp': entry.get('timestamp'),
            'pattern': entry['signal'].get('pattern'),
            'confidence': entry['signal'].get('confidence'),
            'signal_strength': entry['signal'].get('signal_strength'),
            'rsi': entry['technical'].get('rsi'),
            'trend_score': entry['technical'].get('trend_score'),
            'trend_status': entry['technical'].get('trend_status'),
            'limit_entry_price': entry['strategy_data'].get('limit_entry_price'),
            'outcome_open': entry['outcome_candle'].get('open'),
            'outcome_high': entry['outcome_candle'].get('high'),
            'outcome_low': entry['outcome_candle'].get('low'),
            'outcome_close': entry['outcome_candle'].get('close'),
            'outcome_direction': entry['outcome_candle'].get('direction'),
            'symbol': entry['metadata'].get('symbol'),
            'source': entry['metadata'].get('source'),
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
        return "WIN" if close < limit_price else "LOSS"
    else: # CALL
        return "WIN" if close > limit_price else "LOSS"

def main():
    parser = argparse.ArgumentParser(description="Analyze Backtesting Results V8")
    parser.add_argument("--file", type=str, default="data/trading_signals_dataset_v8.jsonl", help="Path to input JSONL file")
    parser.add_argument("--symbol", type=str, help="Filter by Symbol (e.g., EURUSD)")
    parser.add_argument("--source", type=str, help="Filter by Source (e.g., IQOPTION)")
    parser.add_argument("--min_score", type=float, help="Filter by Min Trend Score")
    
    args = parser.parse_args()
    
    print(f"Loading data from {args.file}...")
    df = load_data(args.file)
    
    # Apply Filters
    if args.symbol:
        df = df[df['symbol'] == args.symbol]
    if args.source:
        df = df[df['source'] == args.source]
    if args.min_score is not None:
        df = df[df['trend_score'].abs() >= args.min_score]
        
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
    
    # =================================================================================
    # TABLE 1: GRANULAR ANALYSIS
    # Group by: Pattern, Signal Strength, Trend Score (rounded), RSI Zone
    # =================================================================================
    
    # Round trend score for grouping
    df['score_rounded'] = df['trend_score'].round(1)
    
    group_cols = ['pattern', 'signal_strength', 'score_rounded', 'rsi_zone', 'direction']
    
    # Aggregation
    summary1 = df.groupby(group_cols).agg(
        total_signals=('timestamp', 'count'),
        fills=('trade_result', lambda x: x.isin(['WIN', 'LOSS']).sum()),
        wins=('trade_result', lambda x: (x == 'WIN').sum())
    ).reset_index()
    
    # Metrics
    summary1['fill_rate_pct'] = (summary1['fills'] / summary1['total_signals'] * 100).round(1)
    summary1['win_rate_pct'] = (summary1['wins'] / summary1['fills'] * 100).fillna(0).round(1)
    
    # Filter out rows with 0 fills for cleaner view (optional, but requested detailed)
    # summary1 = summary1[summary1['fills'] > 0]
    
    print("\n" + "="*80)
    print("TABLE 1: GRANULAR ANALYSIS (Pattern + Score + RSI)")
    print("="*80)
    # Sort by Win Rate desc
    summary1_sorted = summary1.sort_values(by=['win_rate_pct', 'fills'], ascending=False)
    
    # Format for display
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(summary1_sorted.to_string(index=False))


    # =================================================================================
    # TABLE 2: STRATEGY SUMMARY
    # Group by: Pattern, Signal Strength, RSI Zone (Ignore Score)
    # =================================================================================
    
    group_cols_2 = ['pattern', 'signal_strength', 'rsi_zone']
    
    summary2 = df.groupby(group_cols_2).agg(
        total_entries=('trade_result', lambda x: x.isin(['WIN', 'LOSS']).sum()),
        wins=('trade_result', lambda x: (x == 'WIN').sum())
    ).reset_index()
    
    summary2['win_rate_pct'] = (summary2['wins'] / summary2['total_entries'] * 100).fillna(0).round(1)
    
    # Only show rows with entries
    summary2 = summary2[summary2['total_entries'] > 0]
    
    print("\n" + "="*80)
    print("TABLE 2: STRATEGY SUMMARY (Aggregated by Pattern & RSI)")
    print("="*80)
    summary2_sorted = summary2.sort_values(by=['win_rate_pct', 'total_entries'], ascending=False)
    print(summary2_sorted.to_string(index=False))
    
    # Global Stats
    total_fills = len(df[df['trade_result'].isin(['WIN', 'LOSS'])])
    total_wins = len(df[df['trade_result'] == 'WIN'])
    global_wr = (total_wins / total_fills * 100) if total_fills > 0 else 0
    
    print("\n" + "="*80)
    print(f"GLOBAL STATS: {total_wins}/{total_fills} Wins ({global_wr:.2f}%)")
    print("="*80)

if __name__ == "__main__":
    main()
