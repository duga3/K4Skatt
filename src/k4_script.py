import pandas as pd
import os
import argparse
import logging
import json
from typing import Dict, Optional, Set

from datetime import datetime

from sru_generator import generate_sru_files

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Default config values - will be overridden by config.json if present
DEFAULT_CONFIG = {
    "personal": {
        "personnummer": "YYYYMMDD-XXXX",
        "namn": "Förnamn Efternamn",
        "adress": "Gatan 1",
        "postnummer": "XXXXX",
        "postort": "Staden",
        "email": "example@email.com",
        "inkomstar": str(datetime.now().year - 1)
    },
    "fx_rates": {
        "USD": 10.5,
        "CHF": 12.2,
        "SEK": 1.0,
        "EUR": 10.0
    }
}

def load_config(config_path: str = "config.json") -> Dict:
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding='utf-8') as config_file:
                config.update(json.load(config_file))
            logger.info(f"Loaded config from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using defaults.")
    else:
        logger.warning(f"No config found at {config_path}. Using defaults.")
    return config

def load_trades(file_path: str) -> Optional[pd.DataFrame]:
    """Load trades from CSV file with proper type conversion."""
    try:
        trades_df = pd.read_csv(
            file_path,
            sep=",",
            decimal=".",
            parse_dates=["DateTime"],
            date_format='%Y%m%d%H%M%S',
            dtype={
                'Symbol': str,
                'UnderlyingSymbol': str,
                'Notes/Codes': str,
                'AssetClass': str,
                'Buy/Sell': str,
                'Put/Call': str
            }
        )
    except Exception as exc:
        logger.error(f"Error reading input file: {exc}")
        return None

    # Validate required columns
    required_cols = {
        "DateTime", "Open/CloseIndicator", "FifoPnlRealized", "Description", "Quantity",
        "CostBasis", "Proceeds", "CurrencyPrimary", "Buy/Sell",
        "Notes/Codes", "AssetClass", "Symbol", "UnderlyingSymbol", "IBCommission", 'Put/Call'
    }
    missing_cols = required_cols - set(trades_df.columns)

    if missing_cols:
        logger.error(f"Missing columns: {missing_cols}")
        return None

    trades_df['Quantity'] = trades_df['Quantity'].astype(int)
    trades_df['TradeDate'] = trades_df['DateTime'].dt.date

    return trades_df

def load_additional_trades(file_path: str) -> pd.DataFrame:
    """Load pre-calculated trades from a CSV file for SRU file inclusion."""
    # Required columns for SRU generation
    required_cols = ['Symbol', 'Beteckning', 'Antal', 'Försäljningspris', 'Omkostnadsbelopp', 'Vinst', 'Förlust']
    
    try:
        # Read CSV, assuming semicolon separator and comma as decimal (common for Swedish data)
        additional_df = pd.read_csv(file_path, sep=';', decimal=',')
        
        # Validate required columns
        missing_cols = [col for col in required_cols if col not in additional_df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Add default values for IB-specific or optional columns
        additional_df['IBKRPnL'] = 0  # Not present in extra trades
        additional_df['Diff vs IBKR'] = 0  # Not relevant
        additional_df['Buy/Sell'] = ''  # Default empty string
        additional_df['TradeDate'] = pd.NaT  # Not required for SRU, set to NaT
        additional_df['Notes/Codes'] = ''  # Ensures grouping treats them as single trades
        
        # Ensure correct data types
        for col in ['Försäljningspris', 'Omkostnadsbelopp', 'Vinst', 'Förlust','Antal']:
            additional_df[col] = additional_df[col].astype(int)  # Monetary values as integers per SRU spec
        
        logger.info(f"Loaded {len(additional_df)} additional trades from {file_path}")
        return additional_df
    except Exception as e:
        logger.error(f"Error loading additional trades: {e}")
        raise

def convert_to_sek(trades_df: pd.DataFrame, exchange_rates: Dict[str, float]) -> pd.DataFrame:
    converted_df = trades_df.copy()
    converted_df['FX'] = converted_df['CurrencyPrimary'].map(exchange_rates)

    missing_currencies = converted_df[converted_df['FX'].isna()]['CurrencyPrimary'].unique()
    if len(missing_currencies) > 0:
        raise ValueError(f"Missing FX rates for: {', '.join(missing_currencies)}")

    for col in ['IBCommission', 'CostBasis', 'Proceeds']:
        converted_df[col] = (converted_df[col].abs() * converted_df['FX']).round().astype(int)

    converted_df['IBKRPnL'] = (converted_df['FifoPnlRealized'] * converted_df['FX']).round(2)
    return converted_df

def make_trade_result(trade_row: pd.Series, forsaljningspris: int, omkostnadsbelopp: int) -> Dict:
    """Create a standardized dict for a processed trade using canonical column names.

    Returns a dict matching the SRU/CSV expected columns so it can be combined
    with additional pre-calculated trades without later attribute mutation.
    """
    net_result = forsaljningspris - omkostnadsbelopp
    return {
        'Antal': int(trade_row['Antal']),
        'Beteckning': trade_row['Beteckning'],
        'Symbol': trade_row.get('Symbol', ''),
        'Försäljningspris': int(forsaljningspris),
        'Omkostnadsbelopp': int(omkostnadsbelopp),
        'Vinst': int(max(0, net_result)),
        'Förlust': int(max(0, -net_result)),
        'IBKRPnL': float(trade_row.get('IBKRPnL', 0.0)),
        'Diff vs IBKR': round(net_result - float(trade_row.get('IBKRPnL', 0.0)), 2)
    }

def process_standard_trade(trade_row: pd.Series) -> Dict:
    """Process standard trades (not exercise/assignment)"""
    is_sell = trade_row['Buy/Sell'] == 'SELL'
    
    forsaljningspris = trade_row['Proceeds'] if is_sell else abs(trade_row['CostBasis'])
    omkostnadsbelopp = (abs(trade_row['CostBasis']) if is_sell else abs(trade_row['Proceeds'])) + trade_row['IBCommission']
    
    return make_trade_result(trade_row, forsaljningspris, omkostnadsbelopp)

def find_related_options(trades_df: pd.DataFrame, trade_date, symbol, exercise_assigned_indices: Set) -> pd.DataFrame:
    """Find related options on the same date with exercise/assignment codes"""
    mask = (trades_df['TradeDate'] == trade_date) & \
           (trades_df['AssetClass'] == 'OPT') & \
           (trades_df['UnderlyingSymbol'] == symbol) & \
           (trades_df.index.isin(exercise_assigned_indices))
    
    return trades_df[mask]

def get_option_premium(related_options: pd.DataFrame, buy_sell: str, put_call: str, notes_code: str) -> float:
    """Extract the option premium from related options trades."""
    filtered_options = related_options[
        (related_options['Buy/Sell'] == buy_sell) & 
        (related_options['Notes/Codes'] == notes_code) & 
        (related_options['Put/Call'] == put_call)
    ]
    # Assuming the option exists, take the first match
    return filtered_options['CostBasis'].iloc[0]

def handle_long_call_exercise(stock_trade_row: pd.Series, related_options: pd.DataFrame) -> Dict:
    """Handle long call exercise (BUY stock, SELL option with Ex)"""
    option_premium = abs(get_option_premium(related_options, 'SELL', 'C', 'Ex'))
    forsaljningspris = stock_trade_row['CostBasis']
    stock_cost = abs(stock_trade_row['Proceeds'])
    omkostnadsbelopp = stock_cost + option_premium + stock_trade_row['IBCommission']
    return make_trade_result(stock_trade_row, forsaljningspris, omkostnadsbelopp)

def handle_long_put_exercise(stock_trade_row: pd.Series, related_options: pd.DataFrame) -> Dict:
    """Handle long put exercise (SELL stock, SELL option with Ex)"""
    option_premium = abs(get_option_premium(related_options, 'SELL', 'P', 'Ex'))
    forsaljningspris = stock_trade_row['Proceeds']
    stock_cost = abs(stock_trade_row['CostBasis'])
    omkostnadsbelopp = stock_cost + option_premium + stock_trade_row['IBCommission']
    return make_trade_result(stock_trade_row, forsaljningspris, omkostnadsbelopp)

def handle_short_call_assignment(stock_trade_row: pd.Series, related_options: pd.DataFrame) -> Dict:
    """Handle short call assignment (SELL stock, BUY option with A)"""
    option_premium = get_option_premium(related_options, 'BUY', 'C', 'A')
    forsaljningspris = stock_trade_row['Proceeds']
    stock_cost = abs(stock_trade_row['CostBasis'])
    omkostnadsbelopp = stock_cost - option_premium + stock_trade_row['IBCommission']
    return make_trade_result(stock_trade_row, forsaljningspris, omkostnadsbelopp)

def handle_short_put_assignment(stock_trade_row: pd.Series, related_options: pd.DataFrame) -> Dict:
    """Handle short put assignment (BUY stock, BUY option with A)"""
    option_premium = get_option_premium(related_options, 'BUY', 'P', 'A')
    forsaljningspris = stock_trade_row['CostBasis']
    stock_cost = abs(stock_trade_row['Proceeds'])
    omkostnadsbelopp = stock_cost - option_premium + stock_trade_row['IBCommission']
    return make_trade_result(stock_trade_row, forsaljningspris, omkostnadsbelopp)

def process_exercise_assignment(stock_trade_row: pd.Series, trades_df: pd.DataFrame, exercise_assigned_indices: Set) -> Dict:
    """Process stock trades resulting from option exercise or assignment"""
    trade_date = stock_trade_row['TradeDate']
    
    symbol = stock_trade_row['Symbol']
    related_options = find_related_options(trades_df, trade_date, symbol,exercise_assigned_indices)
    
    if stock_trade_row['Buy/Sell'] == 'BUY' and 'Ex' in stock_trade_row['Notes/Codes']:
        return handle_long_call_exercise(stock_trade_row, related_options)
    elif stock_trade_row['Buy/Sell'] == 'SELL' and 'Ex' in stock_trade_row['Notes/Codes']:
        return handle_long_put_exercise(stock_trade_row, related_options)
    elif stock_trade_row['Buy/Sell'] == 'SELL' and 'A' in stock_trade_row['Notes/Codes']:
        return handle_short_call_assignment(stock_trade_row, related_options)
    elif stock_trade_row['Buy/Sell'] == 'BUY' and 'A' in stock_trade_row['Notes/Codes']:
        return handle_short_put_assignment(stock_trade_row, related_options)
    else:
        return process_standard_trade(stock_trade_row)

def process_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Process trades to create the K4 report format"""
    trades_df['Antal'] = trades_df['Quantity'].abs()
    trades_df['Beteckning'] = trades_df['Description']
    
    exercise_assigned_mask = trades_df['Notes/Codes'].isin(['Ex', 'A'])
    exercise_assigned_indices = set(trades_df[exercise_assigned_mask].index)
    
    is_closing_trade = trades_df['Open/CloseIndicator'] == 'C'
    has_profit_or_loss = trades_df['IBKRPnL'] != 0
    is_stock_exercise_or_assignment = (trades_df['AssetClass'] == 'STK') & exercise_assigned_mask
    
    trades_to_report = trades_df[is_closing_trade & (has_profit_or_loss | is_stock_exercise_or_assignment)].copy()
    
    # Skip options that were exercised/assigned (they're handled with stock trades)
    skip_exercised_options_mask = (trades_to_report['AssetClass'] == 'OPT') & \
                                   (trades_to_report.index.isin(exercise_assigned_indices))
    trades_to_report = trades_to_report[~skip_exercised_options_mask]
    
    processed_results = []
    for trade_idx, trade_row in trades_to_report.iterrows():
        logger.debug(f"Processing trade {trade_idx}: Symbol={trade_row['Symbol']}, Description={trade_row['Description']}, AssetClass={trade_row['AssetClass']}, Notes/Codes={trade_row['Notes/Codes']}")
        try:
            if trade_row['AssetClass'] == 'STK' and trade_idx in exercise_assigned_indices:
                trade_result = process_exercise_assignment(trade_row, trades_df, exercise_assigned_indices)
            else:
                trade_result = process_standard_trade(trade_row)
            
            trade_result['Buy/Sell'] = trade_row['Buy/Sell']
            trade_result['TradeDate'] = trade_row['TradeDate']
            trade_result['Notes/Codes'] = trade_row['Notes/Codes']
            processed_results.append(trade_result)
        except Exception as e:
            logger.error(f"Error processing trade {trade_idx}: {e}")
            raise
    
    result_df = pd.DataFrame(processed_results)
    
    return result_df

def group_partial_executions(processed_df: pd.DataFrame) -> pd.DataFrame:
    """Group trades by instrument for reporting purposes"""
    if len(processed_df) == 0:
        return processed_df

    # Aggregate trades by instrument
    aggregation_dict = {
        'Antal': 'sum',
        'Försäljningspris': 'sum',
        'Omkostnadsbelopp': 'sum',
        'Vinst': 'sum',
        'Förlust': 'sum',
        'IBKRPnL': 'sum',
        'Diff vs IBKR': 'sum',
        'Symbol': 'first',
        'Buy/Sell': 'first',
        'TradeDate': 'first',
        'Notes/Codes': 'first'
    }
    
    # Group by instrument and count trades per group
    trades_per_instrument = processed_df.groupby('Beteckning').size()
    grouped_df = processed_df.groupby('Beteckning', as_index=False).agg(aggregation_dict)
    
    # Round Diff vs IBKR to 2 decimal places
    grouped_df['Diff vs IBKR'] = grouped_df['Diff vs IBKR'].round(2)
    
    # Add GroupInfo for multi-trade instruments
    grouped_df['GroupInfo'] = trades_per_instrument.apply(lambda count: f"Grouped {count} trades" if count > 1 else None).values
    
    logger.info(f"Grouped trades: {len(processed_df)} -> {len(grouped_df)}")
    
    return grouped_df

def print_summary(result_df: pd.DataFrame, report_type: str = "Summary"):
    """Print summary statistics of the processing results"""
    total_gain = result_df['Vinst'].sum()
    total_loss = result_df['Förlust'].sum()
    total_diff = result_df['Diff vs IBKR'].sum()
    net_result = total_gain - total_loss
    
    if 'GroupInfo' in result_df.columns:
        grouped_instruments_count = result_df['GroupInfo'].notna().sum()
        if grouped_instruments_count > 0:
            logger.info(f"Grouped {grouped_instruments_count} instruments")
    
    logger.info(f"{report_type}: Gain {total_gain:.2f}, Loss {total_loss:.2f}, Net {net_result:.2f}, Diff {total_diff:.2f}")

def create_default_config(output_path: str) -> None:
    """Create a default config file if none exists"""
    if not os.path.exists(output_path):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
        logger.info(f"Created default config: {output_path}")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Generate Swedish K4 tax report and SRU files from IBKR trades.")
    parser.add_argument('input_file', nargs='?', help='Path to IBKR trades CSV file')
    parser.add_argument('--config', '-c', default='config.json', help='Path to configuration file (default: config.json)')
    parser.add_argument('--create-config', action='store_true', help='Create a default config file if it doesn\'t exist')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--no-sru', action='store_true', help='Skip SRU file generation')
    parser.add_argument('--additional-trades', help='Path to additional pre-calculated trades CSV file')
    return parser.parse_args()

def main():
    """Main entry point for the script"""
    args = parse_arguments()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Create default config if requested
    if args.create_config:
        create_default_config(args.config)
        if not args.input_file or not os.path.isfile(args.input_file):
            logger.info("No input file specified. Exiting.")
            return
    
    # Load configuration
    config = load_config(args.config)
    
    if not args.input_file:
        logger.error("No input file specified.")
        return
    
    if not os.path.isfile(args.input_file):
        logger.error(f"Input file not found: {args.input_file}")
        return
    
    try:
        trades_df = load_trades(args.input_file)
        if trades_df is None:
            return
            
        trades_in_sek = convert_to_sek(trades_df, config['fx_rates'])
        
        processed_trades = process_trades(trades_in_sek)
        
        # Load and combine additional trades if provided
        if args.additional_trades:
            additional_trades = load_additional_trades(args.additional_trades)
            processed_trades = pd.concat([processed_trades, additional_trades], ignore_index=True)
            logger.info(f"Total trades: {len(processed_trades)} (IB + additional)")
        else:
            logger.info(f"Processed {len(processed_trades)} IB trades")
        
        processed_trades.sort_values('Beteckning', inplace=True)
        grouped_trades = group_partial_executions(processed_trades)
        
        print_summary(processed_trades, "Original")
        print_summary(grouped_trades, "Grouped")
        
        # Save CSV outputs
        output_dir = 'output'
        os.makedirs(output_dir, exist_ok=True)
        
        input_base_name = os.path.splitext(os.path.basename(args.input_file))[0]
        
        output_file = os.path.join(output_dir, f"{input_base_name}_k4.csv")
        processed_trades.to_csv(output_file, sep=';', decimal=',', index=False)
        logger.info(f"Saved: {output_file}")
        
        grouped_output_file = os.path.join(output_dir, f"{input_base_name}_k4_grouped.csv")
        
        output_columns = list(grouped_trades.columns)
        if 'GroupInfo' in output_columns and 'Notes/Codes' in output_columns:
            output_columns.remove('GroupInfo')
            notes_column_index = output_columns.index('Notes/Codes')
            output_columns.insert(notes_column_index + 1, 'GroupInfo')
            grouped_trades = grouped_trades[output_columns]
        
        grouped_trades.to_csv(grouped_output_file, sep=';', decimal=',', index=False)
        logger.info(f"Saved: {grouped_output_file}")
        
        # Generate SRU files (if not disabled)
        if not args.no_sru:            
            generate_sru_files(grouped_trades, config, output_dir)
        else:
            logger.info("SRU generation skipped")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()