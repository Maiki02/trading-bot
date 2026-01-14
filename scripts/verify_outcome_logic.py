
import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.logic.candle import get_pattern_action, get_candle_direction

def simulate_outcome(pattern, entry_price, close_price, low_price, high_price):
    action = get_pattern_action(pattern)
    
    # Check Fill
    filled = False
    if entry_price is not None:
        if low_price <= entry_price <= high_price:
            filled = True
            
    if not filled:
        return action, "NO_ENTRY"
    
    result = "ATM"
    if action == "PUT":
        if close_price < entry_price:
            result = "WIN"
        elif close_price > entry_price:
            result = "LOSS"
    elif action == "CALL":
        if close_price > entry_price:
            result = "WIN"
        elif close_price < entry_price:
            result = "LOSS"
            
    return action, result

def test_logic():
    print("--- Testing Outcome Logic ---")
    
    # pattern, entry, close, low, high, expected_action, expected_result
    scenarios = [
        ("SHOOTING_STAR", 1.1000, 1.0900, 1.0800, 1.1100, "PUT", "WIN"),
        ("SHOOTING_STAR", 1.1000, 1.1100, 1.0800, 1.1200, "PUT", "LOSS"),
        # NO ENTRY CASES
        ("SHOOTING_STAR", 1.1000, 1.0900, 1.0800, 1.0950, "PUT", "NO_ENTRY"), # High (1.0950) < Entry (1.1000)
        ("HAMMER", 1.1000, 1.1100, 1.1050, 1.1200, "CALL", "NO_ENTRY"),       # Low (1.1050) > Entry (1.1000)
        
        ("INVERTED_HAMMER", 1.1000, 1.0900, 1.0800, 1.1100, "PUT", "WIN"),
        ("HAMMER", 1.1000, 1.1100, 1.0900, 1.1200, "CALL", "WIN"),
        ("HANGING_MAN", 1.1000, 1.1100, 1.0900, 1.1200, "CALL", "WIN"),
    ]
    
    for pattern, entry, close, low, high, exp_action, exp_result in scenarios:
        act, res = simulate_outcome(pattern, entry, close, low, high)
        status = "✅" if act == exp_action and res == exp_result else "❌"
        print(f"{status} Pat: {pattern:12} | Ent: {entry:.4f} | Rng: {low:.4f}-{high:.4f} | Cls: {close:.4f} -> Action: {act:4} | Result: {res:8}")

if __name__ == "__main__":
    test_logic()
