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
        # Extract Pattern Candle Data
        pc = entry.get('pattern_candle', {})
        oc = entry.get('outcome_candle', {})
        sig = entry.get('signal', {})
        tech = entry.get('technical', {})
        meta = entry.get('metadata', {})
        
        flat_entry = {
            'timestamp': meta.get('timestamp'),
            'symbol': meta.get('symbol'),
            'pattern': pc.get('pattern', sig.get('pattern_name')),
            'direction': sig.get('direction'),
            'confidence': pc.get('confidence', sig.get('confidence')),
            'signal_strength': sig.get('signal_strength', 'NONE'), # Default to NONE if missing
            'rsi': tech.get('rsi_value'),
            'trend_score': tech.get('trend_score'),
            
            # Pattern Candle OHLC
            'pattern_open': pc.get('open'),
            'pattern_high': pc.get('high'),
            'pattern_low': pc.get('low'),
            'pattern_close': pc.get('close'),
            
            # Outcome Candle OHLC
            'outcome_open': oc.get('open'),
            'outcome_high': oc.get('high'),
            'outcome_low': oc.get('low'),
            'outcome_close': oc.get('close'),
        }
        flattened_data.append(flat_entry)
        
    return pd.DataFrame(flattened_data)

def classify_rsi(rsi_value):
    """Classifies RSI into zones."""
    if pd.isna(rsi_value):
        return "UNKNOWN"
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
        # Extract Pattern Candle Data
        pc = entry.get('pattern_candle', {})
        oc = entry.get('outcome_candle', {})
        sig = entry.get('signal', {})
        tech = entry.get('technical', {})
        meta = entry.get('metadata', {})
        
        flat_entry = {
            'timestamp': meta.get('timestamp'),
            'symbol': meta.get('symbol'),
            'pattern': pc.get('pattern', sig.get('pattern_name')),
            'direction': sig.get('direction'),
            'confidence': pc.get('confidence', sig.get('confidence')),
            'signal_strength': sig.get('signal_strength', 'NONE'), # Default to NONE if missing
            'rsi': tech.get('rsi_value'),
            'trend_score': tech.get('trend_score'),
            
            # Pattern Candle OHLC
            'pattern_open': pc.get('open'),
            'pattern_high': pc.get('high'),
            'pattern_low': pc.get('low'),
            'pattern_close': pc.get('close'),
            
            # Outcome Candle OHLC
            'outcome_open': oc.get('open'),
            'outcome_high': oc.get('high'),
            'outcome_low': oc.get('low'),
            'outcome_close': oc.get('close'),
        }
        flattened_data.append(flat_entry)
        
    return pd.DataFrame(flattened_data)

def classify_rsi(rsi_value):
    """Classifies RSI into zones."""
    if pd.isna(rsi_value):
        return "UNKNOWN"
    if rsi_value >= Config.RSI_OVERBOUGHT:
        return "OVERBOUGHT"
    if rsi_value <= Config.RSI_OVERSOLD:
        return "OVERSOLD"
    return "NEUTRAL"

def calculate_entry_and_result(row, entry_pct=0.5, safety_margin=0.1):
    """
    Calculates Entry Point, checks for Fill, and determines Result.
    Returns a Series with new metrics.
    """
    direction = row['direction']
    p_high = row['pattern_high']
    p_low = row['pattern_low']
    
    o_high = row['outcome_high']
    o_low = row['outcome_low']
    o_close = row['outcome_close']
    
    # 1. Calculate Entry Price (Limit Entry - 50% Retracement)
    rng = p_high - p_low
    # Entry is always the midpoint of the signal candle
    entry_price = p_low + (rng * entry_pct)

    # 2. Check Fill (ROBUST MODE)
    # We require the price to go DEEPER than the entry price by a safety margin
    # to simulate slippage, latency, and spread.
    margin_abs = rng * safety_margin
    
    filled = False
    if direction == 'PUT':
        # Selling: We need price to go UP to our Limit Sell order
        # Robust: High must be >= Entry + Margin
        if o_high >= (entry_price + margin_abs):
            filled = True
    elif direction == 'CALL':
        # Buying: We need price to go DOWN to our Limit Buy order
        # Robust: Low must be <= Entry - Margin
        if o_low <= (entry_price - margin_abs):
            filled = True
            
    if not filled:
        return pd.Series({
            'entry_price': entry_price,
            'filled': False,
            'result': 'NO_FILL',
            'pnl': 0.0
        })
        
    # 3. Determine Result (Only if Filled)
    result = 'TIE'
    pnl = 0.0
    
    if direction == 'PUT':
        if o_close < entry_price:
            result = 'WIN'
            pnl = 0.86 # Payout
        elif o_close > entry_price:
            result = 'LOSS'
            pnl = -1.00
        else:
            result = 'ATM'
            pnl = 0.00
            
    elif direction == 'CALL':
        if o_close > entry_price:
            result = 'WIN'
            pnl = 0.86
        elif o_close < entry_price:
            result = 'LOSS'
            pnl = -1.00
        else:
            result = 'ATM'
            pnl = 0.00
            
    return pd.Series({
        'entry_price': entry_price,
        'filled': True,
        'result': result,
        'pnl': pnl
    })

def main():
    parser = argparse.ArgumentParser(description="Analyze Backtesting Results V8 (Limit Entry)")
    parser.add_argument("--file", type=str, default="data/trading_signals_dataset_v8.jsonl", help="Path to input JSONL file")
    parser.add_argument("--symbol", type=str, help="Filter by Symbol")
    parser.add_argument("--entry_pct", type=float, default=0.5, help="Entry Percentage (0.5 = 50% Retracement)")
    parser.add_argument("--safety_margin", type=float, default=0.1, help="Safety Margin for Fill (0.1 = 10% of candle range)")
    
    args = parser.parse_args()
    
    print(f"Loading data from {args.file}...")
    df = load_data(args.file)
    
    if args.symbol:
        df = df[df['symbol'] == args.symbol]

    # --- FILTERING CRITICO ---
    # Eliminamos las señales NONE antes de empezar cualquier análisis
    initial_count = len(df)
    df = df[df['signal_strength'] != 'NONE']
    filtered_count = len(df)
    
    print(f"Filtering NONE signals: {initial_count} -> {filtered_count} valid signals.")
        
    if df.empty:
        print("No valid signals found (all were NONE).")
        return

    print(f"Analyzing {len(df)} QUALIFIED signals with Limit Entry Strategy...")
    print(f"🛡️  MODO BACKTEST ROBUSTO: Entry @ {args.entry_pct*100:.1f}% | Margin Requerido: +{args.safety_margin*100:.1f}%")
    
    # Apply Strategy Logic
    results = df.apply(lambda row: calculate_entry_and_result(row, entry_pct=args.entry_pct, safety_margin=args.safety_margin), axis=1)
    df = pd.concat([df, results], axis=1)
    
    # Classify RSI
    df['rsi_zone'] = df['rsi'].apply(classify_rsi)
    
    # =============================================================================
    # REPORTING
    # =============================================================================
    
    # Filter for Filled Trades
    filled_trades = df[df['filled'] == True].copy()
    
    total_signals = len(df)
    total_filled = len(filled_trades)
    fill_rate = (total_filled / total_signals * 100) if total_signals > 0 else 0
    
    wins = len(filled_trades[filled_trades['result'] == 'WIN'])
    losses = len(filled_trades[filled_trades['result'] == 'LOSS'])
    atms = len(filled_trades[filled_trades['result'] == 'ATM'])
    
    decisive_trades = wins + losses
    win_rate = (wins / decisive_trades * 100) if decisive_trades > 0 else 0.0
    total_pnl = filled_trades['pnl'].sum()
    
    print("\n" + "="*60)
    print(f"📊 BACKTEST RESULTS: QUALIFIED SIGNALS ONLY")
    print("="*60)
    print(f"Qualified Signals:      {total_signals}")
    print(f"Filled Trades:          {total_filled} ({fill_rate:.1f}%)")
    print("-" * 30)
    print(f"Wins:                   {wins}")
    print(f"Losses:                 {losses}")
    print(f"ATM (Refunds):          {atms}")
    print("-" * 30)
    print(f"🏆 WIN RATE (Pure):     {win_rate:.2f}%")
    print(f"💰 TOTAL PnL:           ${total_pnl:.2f}")
    print("="*60)
    
    # --- HELPER FOR PRINTING TABLES ---
    def print_breakdown(df_grouped, title):
        if df_grouped.empty:
            print(f"\n🔍 {title}: No Data")
            return
            
        print(f"\n🔍 {title}:")
        # Calculate Win Rate
        df_grouped['win_rate'] = (df_grouped['wins'] / (df_grouped['wins'] + df_grouped['losses']) * 100).fillna(0).round(1)
        # Sort by PnL desc for general view
        if 'trend_score' in df_grouped.columns:
            # Sort by Pattern -> Strength -> Score (Desc)
            # This keeps Very High scores at the top
            pass 
        else:
             df_grouped = df_grouped.sort_values('pnl', ascending=False)
             
        print(df_grouped.to_string(index=False))

    # Define order for signal strength (Excluding NONE as they are filtered)
    strength_order = ['VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW', 'VERY_LOW', 'UNKNOWN']
    # Use observed=True to handle the fact that NONE is gone but might be in the type definition if reusing
    filled_trades['signal_strength'] = pd.Categorical(filled_trades['signal_strength'], categories=strength_order, ordered=True)

    # 1. BREAKDOWN BY SIGNAL STRENGTH
    strength_breakdown = filled_trades.groupby('signal_strength', observed=True).agg(
        trades=('result', 'count'),
        wins=('result', lambda x: (x == 'WIN').sum()),
        losses=('result', lambda x: (x == 'LOSS').sum()),
        pnl=('pnl', 'sum')
    ).reset_index()
    print_breakdown(strength_breakdown, "BREAKDOWN BY SIGNAL STRENGTH")

    # 2. BREAKDOWN BY PATTERN & STRENGTH & SCORE
    # This gives the detailed view "separated by candle/signal" requested
    score_breakdown = filled_trades.groupby(['pattern', 'signal_strength', 'trend_score'], observed=True).agg(
        trades=('result', 'count'),
        wins=('result', lambda x: (x == 'WIN').sum()),
        losses=('result', lambda x: (x == 'LOSS').sum()),
        pnl=('pnl', 'sum')
    ).reset_index()
    
    # Sort: Pattern A-Z, Strength (Very High -> Low), Score (Descending: 10 -> -10)
    score_breakdown = score_breakdown.sort_values(['pattern', 'signal_strength', 'trend_score'], ascending=[True, True, False])
    
    print_breakdown(score_breakdown, "BREAKDOWN BY PATTERN, STRENGTH & SCORE")

if __name__ == "__main__":
    main()