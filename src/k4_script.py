import pandas as pd
import argparse
import os
import logging
import json
from typing import Dict, Optional, Set
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime

# Import SRU generator module
try:
    from sru_generator import generate_sru_files
except ImportError:
    # If sru_generator.py is in the same directory but not installed
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
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

@dataclass
class TradeResult:
    """Structured data class for trade results"""
    antal: int
    beteckning: str
    symbol: str
    forsaljningspris: int
    omkostnadsbelopp: int
    vinst: int
    forlust: int
    ibkr_pnl: float
    diff_vs_ibkr: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for DataFrame creation"""
        return {
            'Antal': self.antal,
            'Beteckning': self.beteckning,
            'Symbol': self.symbol,
            'Försäljningspris': self.forsaljningspris,
            'Omkostnadsbelopp': self.omkostnadsbelopp,
            'Vinst': self.vinst,
            'Förlust': self.forlust,
            'IBKRPnL': self.ibkr_pnl,
            'Diff vs IBKR': self.diff_vs_ibkr
        }

def load_config(config_path: str) -> Dict:
    """Load configuration from JSON file, falling back to defaults if needed"""
    config = DEFAULT_CONFIG.copy()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            config = user_config
                    
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            logger.warning("Using default configuration")
    else:
        logger.warning(f"Config file {config_path} not found. Using default configuration.")
        logger.warning("This will use placeholder personal information. Create a config file with --create-config.")
        
    return config

@contextmanager
def debug_section(title: str):
    """Context manager for structured debug logging sections"""
    logger.debug(f"\n=== {title} ===")
    try:
        yield
    finally:
        logger.debug("=" * (len(title) + 8))

def contains_code(note_str, code: str) -> bool:
    """Safely check if a string contains a code, handling None/NaN values."""
    if pd.isna(note_str) or note_str is None:
        return False
    return code in str(note_str)

def is_put_option(description) -> bool:
    """Check if an option is a put option based on its description."""
    if pd.isna(description):
        return False
    return ' P ' in description or description.endswith(' P')

def load_trades(file_path: str) -> Optional[pd.DataFrame]:
    """Load trades from CSV file with proper type conversion"""
    try:
        df = pd.read_csv(
            file_path,
            sep=";",
            decimal=",",
            parse_dates=["DateTime"],
            dtype={
                'Symbol': str,
                'UnderlyingSymbol': str,
                'Notes/Codes': str,
                'AssetClass': str,
                'Buy/Sell': str
            },
            na_values=['', 'nan', 'NaN', 'NULL']
        )
        # Cut off fractional trades, proceeds are considered regardless.
        df['Quantity'] = df['Quantity'].astype(int)
    except Exception as e:
        logger.error(f"Error reading the input file: {e}")
        return None

    # Validate required columns
    required_cols = {
        "DateTime", "Open/CloseIndicator", "FifoPnlRealized", "Description", "Quantity",
        "CostBasis", "Proceeds", "CurrencyPrimary", "Buy/Sell",
        "Notes/Codes", "AssetClass", "Symbol", "UnderlyingSymbol", "IBCommission"
    }
    missing_cols = required_cols - set(df.columns)
    
    if missing_cols:
        if len(missing_cols) == 1 and 'IBCommission' in missing_cols:
            logger.warning(f"Missing IBCommission column, assuming zero commissions")
            df['IBCommission'] = 0
        else:
            logger.error(f"Missing columns in input file: {missing_cols}")
            return None

    # Standardize column naming
    df['BuySell'] = df['Buy/Sell']
    
    # Add TradeDate column for easier grouping
    df['TradeDate'] = df['DateTime'].dt.date
    
    # Fill NaN values with empty strings for text columns
    for col in ['Notes/Codes', 'UnderlyingSymbol', 'Symbol']:
        if col in df.columns:
            df[col] = df[col].fillna('')
    
    return df

def load_additional_trades(file_path: str) -> pd.DataFrame:
    """Load pre-calculated trades from a CSV file for SRU file inclusion."""
    # Required columns for SRU generation
    required_cols = ['Symbol', 'Beteckning', 'Antal', 'Försäljningspris', 'Omkostnadsbelopp', 'Vinst', 'Förlust']
    
    try:
        # Read CSV, assuming semicolon separator and comma as decimal (common for Swedish data)
        df = pd.read_csv(file_path, sep=';', decimal=',')
        
        # Validate required columns
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns in additional trades CSV: {missing_cols}")
        
        # Add default values for IB-specific or optional columns
        df['IBKRPnL'] = 0  # Not present in extra trades
        df['Diff vs IBKR'] = 0  # Not relevant
        df['BuySell'] = ''  # Default empty string
        df['TradeDate'] = pd.NaT  # Not required for SRU, set to NaT
        df['Notes/Codes'] = ''  # Ensures grouping treats them as single trades
        
        # Ensure correct data types
        for col in ['Försäljningspris', 'Omkostnadsbelopp', 'Vinst', 'Förlust','Antal']:
            df[col] = df[col].astype(int)  # Monetary values as integers per SRU spec
        
        logger.info(f"Loaded {len(df)} pre-calculated trades from {file_path}")
        return df
    except Exception as e:
        logger.error(f"Error loading additional trades: {e}")
        raise

def convert_to_sek(df: pd.DataFrame, fx_rates: Dict[str, float]) -> pd.DataFrame:
    """Convert all monetary values to SEK using vectorized operations"""
    with debug_section("Converting currencies to SEK"):
        result_df = df.copy()
        
        result_df['FX'] = result_df['CurrencyPrimary'].map(fx_rates)
        missing_fx = result_df[result_df['FX'].isna()]['CurrencyPrimary'].unique()
        if len(missing_fx) > 0:
            raise ValueError(f"No FX rate for currencies: {missing_fx}")
        
        result_df['Commission'] = (result_df['IBCommission'].abs() * result_df['FX']).round().astype(int)
        result_df['CostBasis'] = (result_df['CostBasis'] * result_df['FX']).round().astype(int)
        result_df['Proceeds'] = (result_df['Proceeds'] * result_df['FX']).round().astype(int)
        result_df['IBKRPnL'] = result_df['FifoPnlRealized'] * result_df['FX']
        
        logger.debug(f"Converted {len(df)} trades to SEK")
        
        return result_df

def create_result_entry(row: pd.Series, forsaljningspris: int, omkostnadsbelopp: int) -> TradeResult:
    """Create a structured result entry with calculated values"""
    net_pnl = forsaljningspris - omkostnadsbelopp
    
    logger.debug(f"Försäljningspris: {forsaljningspris}")
    logger.debug(f"Omkostnadsbelopp: {omkostnadsbelopp}")
    logger.debug(f"Our P&L calculation: {net_pnl}")
    logger.debug(f"IBKR P&L (for comparison): {row['IBKRPnL']}")
    logger.debug(f"Difference: {net_pnl - row['IBKRPnL']}")
    
    vinst = max(0, net_pnl)
    forlust = max(0, -net_pnl)
    
    diff_vs_ibkr = round(net_pnl - row['IBKRPnL'], 2)
    
    return TradeResult(
        antal=row['Antal'],
        beteckning=row['Beteckning'],
        symbol=row['Symbol'],
        forsaljningspris=forsaljningspris,
        omkostnadsbelopp=omkostnadsbelopp,
        vinst=vinst,
        forlust=forlust,
        ibkr_pnl=row['IBKRPnL'],
        diff_vs_ibkr=diff_vs_ibkr
    )

def process_standard_trade(row: pd.Series) -> TradeResult:
    """Process standard trades (not exercise/assignment)"""
    is_sell = row['BuySell'] == 'SELL'
    
    forsaljningspris = row['Proceeds'] if is_sell else abs(row['CostBasis'])
    omkostnadsbelopp = (abs(row['CostBasis']) if is_sell else abs(row['Proceeds'])) + row['Commission']
    
    return create_result_entry(row, forsaljningspris, omkostnadsbelopp)

def find_related_options(df: pd.DataFrame, date, exercise_assigned_set: Set) -> pd.DataFrame:
    """Find related options on the same date with exercise/assignment codes"""
    mask = (df['TradeDate'] == date) & \
           (df['AssetClass'] == 'OPT') & \
           (df.index.isin(exercise_assigned_set))
    
    return df[mask]

def handle_long_call_exercise(row: pd.Series, related_options: pd.DataFrame) -> TradeResult:
    """Handle long call exercise (BUY stock, SELL option with Ex)"""
    with debug_section("Long Call Exercise Processing"):
        exercised_calls = related_options[
            (related_options['BuySell'] == 'SELL') & 
            (related_options['Notes/Codes'].str.contains('Ex')) & 
            (~related_options['Description'].apply(is_put_option))
        ]
        
        if not exercised_calls.empty:
            logger.debug("LONG CALL EXERCISE (BUY stock, SELL option)")
            forsaljningspris = row['CostBasis']  # Zero or small fee for purchase
            stock_cost = abs(row['Proceeds'])  # Strike price paid
            option_premium = abs(exercised_calls['CostBasis'].iloc[0])
            logger.debug(f"Long call premium: {option_premium}")
            omkostnadsbelopp = stock_cost + option_premium + row['Commission']
        else:
            logger.debug("Unknown call exercise pattern - treating as normal trade")
            forsaljningspris = row['Proceeds']
            omkostnadsbelopp = abs(row['CostBasis']) + row['Commission']
        
        return create_result_entry(row, forsaljningspris, omkostnadsbelopp)

def handle_long_put_exercise(row: pd.Series, related_options: pd.DataFrame) -> TradeResult:
    """Handle long put exercise (SELL stock, SELL option with Ex)"""
    with debug_section("Long Put Exercise Processing"):
        exercised_puts = related_options[
            (related_options['BuySell'] == 'SELL') & 
            (related_options['Notes/Codes'].str.contains('Ex')) & 
            (related_options['Description'].apply(is_put_option))
        ]
        
        if not exercised_puts.empty:
            logger.debug("LONG PUT EXERCISE (SELL stock, SELL option)")
            forsaljningspris = row['Proceeds']  # Amount received
            stock_cost = abs(row['CostBasis'])  # Cost basis of stock
            option_premium = abs(exercised_puts['CostBasis'].iloc[0])
            logger.debug(f"Long put premium: {option_premium}")
            omkostnadsbelopp = stock_cost + option_premium + row['Commission']
        else:
            logger.debug("Unknown put exercise pattern - treating as normal trade")
            forsaljningspris = row['Proceeds']
            omkostnadsbelopp = abs(row['CostBasis']) + row['Commission']
        
        return create_result_entry(row, forsaljningspris, omkostnadsbelopp)

def handle_short_call_assignment(row: pd.Series, related_options: pd.DataFrame) -> TradeResult:
    """Handle short call assignment (SELL stock, BUY option with A)"""
    with debug_section("Short Call Assignment Processing"):
        assigned_calls = related_options[
            (related_options['BuySell'] == 'BUY') & 
            (related_options['Notes/Codes'].str.contains('A')) & 
            (~related_options['Description'].apply(is_put_option))
        ]
        
        if not assigned_calls.empty:
            logger.debug("SHORT CALL ASSIGNMENT (SELL stock, BUY option)")
            forsaljningspris = row['Proceeds']  # Amount received
            stock_cost = abs(row['CostBasis'])  # Cost basis of stock
            option_premium = assigned_calls['CostBasis'].iloc[0]  # Negative, premium received
            logger.debug(f"Short call premium: {option_premium}")
            omkostnadsbelopp = stock_cost - option_premium + row['Commission']
        else:
            logger.debug("Unknown call assignment pattern - treating as normal trade")
            forsaljningspris = row['Proceeds']
            omkostnadsbelopp = abs(row['CostBasis']) + row['Commission']
        
        return create_result_entry(row, forsaljningspris, omkostnadsbelopp)

def handle_short_put_assignment(row: pd.Series, related_options: pd.DataFrame) -> TradeResult:
    """Handle short put assignment (BUY stock, BUY option with A)"""
    with debug_section("Short Put Assignment Processing"):
        assigned_puts = related_options[
            (related_options['BuySell'] == 'BUY') & 
            (related_options['Notes/Codes'].str.contains('A')) & 
            (related_options['Description'].apply(is_put_option))
        ]
        
        if not assigned_puts.empty:
            logger.debug("SHORT PUT ASSIGNMENT (BUY stock, BUY option)")
            forsaljningspris = row['CostBasis']  # Zero or small fee for purchase
            stock_cost = abs(row['Proceeds'])  # Strike price paid
            option_premium = assigned_puts['CostBasis'].iloc[0]  # Negative, premium received
            logger.debug(f"Short put premium: {option_premium}")
            omkostnadsbelopp = stock_cost - option_premium + row['Commission']
        else:
            logger.debug("Unknown put assignment pattern - treating as normal trade")
            forsaljningspris = row['Proceeds']
            omkostnadsbelopp = abs(row['CostBasis']) + row['Commission']
        
        return create_result_entry(row, forsaljningspris, omkostnadsbelopp)

def process_exercise_assignment(row: pd.Series, df: pd.DataFrame, exercise_assigned_set: Set) -> TradeResult:
    """Process stock trades resulting from option exercise or assignment"""
    dt = row['TradeDate']
    
    with debug_section(f"Processing stock trade date {dt}"):
        logger.debug(f"Trade: {row['Beteckning']} - {row['BuySell']} - {row['Notes/Codes']}")
        logger.debug(f"IBKR P&L (for reference only): {row['IBKRPnL']}")
        
        related_options = find_related_options(df, dt, exercise_assigned_set)
        
        for _, opt in related_options.iterrows():
            logger.debug(f"Related option: {opt['Description']} - {opt['BuySell']} - {opt['Notes/Codes']} - CostBasis: {opt['CostBasis']}")
        
        if row['BuySell'] == 'BUY' and 'Ex' in str(row['Notes/Codes']):
            return handle_long_call_exercise(row, related_options)
        elif row['BuySell'] == 'SELL' and 'Ex' in str(row['Notes/Codes']):
            return handle_long_put_exercise(row, related_options)
        elif row['BuySell'] == 'SELL' and 'A' in str(row['Notes/Codes']):
            return handle_short_call_assignment(row, related_options)
        elif row['BuySell'] == 'BUY' and 'A' in str(row['Notes/Codes']):
            return handle_short_put_assignment(row, related_options)
        else:
            logger.debug(f"Unknown exercise/assignment pattern: {row['BuySell']} - {row['Notes/Codes']}")
            return process_standard_trade(row)

def process_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Process trades to create the K4 report format"""
    with debug_section("Processing Trades"):
        trades_df['Antal'] = trades_df['Quantity'].abs()
        trades_df['Beteckning'] = trades_df['Description']
        
        exercise_assigned_mask = trades_df['Notes/Codes'].str.contains('Ex|A', na=False)
        exercise_assigned_set = set(trades_df[exercise_assigned_mask].index)
        
        mask_close = trades_df['Open/CloseIndicator'] == 'C'
        mask_profit = trades_df['IBKRPnL'] != 0
        mask_stock_ex_a = (trades_df['AssetClass'] == 'STK') & exercise_assigned_mask
        
        trades_to_report = trades_df[mask_close & (mask_profit | mask_stock_ex_a)].copy()
        
        logger.debug(f"Found {len(trades_to_report)} trades to report")
        
        skip_mask = (trades_to_report['AssetClass'] == 'OPT') & \
                    (trades_to_report.index.isin(exercise_assigned_set))
        trades_to_report = trades_to_report[~skip_mask]
        
        logger.debug(f"After skipping exercised/assigned options: {len(trades_to_report)} trades")
        
        results = []
        for idx, row in trades_to_report.iterrows():
            if row['AssetClass'] == 'STK' and idx in exercise_assigned_set:
                result = process_exercise_assignment(row, trades_df, exercise_assigned_set)
            else:
                result = process_standard_trade(row)
            
            result_dict = result.to_dict()
            result_dict['BuySell'] = row['BuySell']
            result_dict['TradeDate'] = row['TradeDate']
            result_dict['Notes/Codes'] = row['Notes/Codes']
            
            results.append(result_dict)
        
        result_df = pd.DataFrame(results)
        
        return result_df

def group_partial_executions(processed_df: pd.DataFrame) -> pd.DataFrame:
    """Group partial executions for reporting purposes"""
    with debug_section("Grouping Partial Executions"):
        has_partial = processed_df['Notes/Codes'].str.contains('P', na=False).any()
        if not has_partial:
            logger.debug("No partial executions found to group")
            return processed_df.copy()
        
        grouped_df = processed_df.copy()
        
        partial_mask = grouped_df['Notes/Codes'].str.contains('P', na=False)
        logger.debug(f"Found {partial_mask.sum()} trades with 'P' in Notes/Codes")
        
        grouped_df['GroupKey'] = grouped_df.apply(
            lambda row: f"{row['BuySell']}_{row['TradeDate']}_{row['Beteckning']}" 
            if partial_mask.loc[row.name] else f"single_{row.name}", 
            axis=1
        )
        
        group_counts = grouped_df['GroupKey'].value_counts()
        multi_entry_groups = group_counts[group_counts > 1].index
        logger.debug(f"Found {len(multi_entry_groups)} groups of partial executions")
        
        result_rows = []
        non_grouped_mask = ~grouped_df['GroupKey'].isin(multi_entry_groups)
        result_rows.append(grouped_df[non_grouped_mask].drop(columns=['GroupKey']))
        
        for group_key in multi_entry_groups:
            group = grouped_df[grouped_df['GroupKey'] == group_key]
            logger.debug(f"Grouping {len(group)} partial executions for {group_key}")
            
            combined_row = group.iloc[0].copy()
            
            for field in ['Antal', 'Försäljningspris', 'Omkostnadsbelopp', 'Vinst', 'Förlust', 'IBKRPnL', 'Diff vs IBKR']:
                if field in group.columns:
                    combined_row[field] = group[field].sum()
            
            combined_row['GroupInfo'] = f"Grouped {len(group)} partial executions"
            combined_row = combined_row.drop('GroupKey')
            
            result_rows.append(pd.DataFrame([combined_row]))
        
        result_df = pd.concat(result_rows, ignore_index=True)
        
        logger.info(f"Reduced from {len(processed_df)} to {len(result_df)} trades after grouping")
        
        return result_df

def print_summary(result: pd.DataFrame, report_type: str = "Summary"):
    """Print summary statistics of the processing results"""
    with debug_section(f"{report_type} Statistics"):
        total_gain = result['Vinst'].sum()
        total_loss = result['Förlust'].sum()
        total_diff = result['Diff vs IBKR'].sum()
        net_result = total_gain - total_loss
        
        if 'GroupInfo' in result.columns:
            grouped_count = result['GroupInfo'].notna().sum()
            if grouped_count > 0:
                logger.info(f"Grouped {grouped_count} sets of partial executions")
        
        logger.info(f"\n{report_type}:")
        logger.info(f"Total Gain: {total_gain:.2f} SEK")
        logger.info(f"Total Loss: {total_loss:.2f} SEK")
        logger.info(f"Net Result: {net_result:.2f} SEK")
        logger.info(f"Total diff: {total_diff:.2f} SEK")

def create_default_config(output_path: str) -> None:
    """Create a default config file if none exists"""
    if not os.path.exists(output_path):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
            
        logger.info(f"Created default configuration file: {output_path}")

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
            logger.info("No input file specified. Exiting after creating config.")
            return
    
    # Load configuration
    config = load_config(args.config)
    
    if not args.input_file:
        logger.error("No input file specified. Use --create-config to generate a config file.")
        return
    
    if not os.path.isfile(args.input_file):
        logger.error(f"Error: Input file not found: {args.input_file}")
        return
    
    try:
        with debug_section("K4 Report Generation"):
            trades = load_trades(args.input_file)
            if trades is None:
                return
                
            trades_sek = convert_to_sek(trades, config['fx_rates'])
            
            result = process_trades(trades_sek)
            
            # Load and combine additional trades if provided
            if args.additional_trades:
                additional_trades = load_additional_trades(args.additional_trades)
                result = pd.concat([result, additional_trades], ignore_index=True)
                logger.info(f"Combined {len(result)} total trades (IB and additional)")
            else:
                logger.info(f"Processed {len(result)} IB trades")
            
            result.sort_values('Beteckning', inplace=True)
            grouped_result = group_partial_executions(result)
            
            print_summary(result, "Original Report")
            print_summary(grouped_result, "Grouped Report")
            
            # Save CSV outputs
            # Ensure the output directory exists
            output_dir = 'output'
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            input_base_name = os.path.splitext(os.path.basename(args.input_file))[0]
            
            output_file = os.path.join(output_dir, f"{input_base_name}_k4.csv")
            result.to_csv(output_file, sep=';', decimal=',', index=False)
            logger.info(f"\nResults saved to: {output_file}")
            
            grouped_output_file = os.path.join(output_dir, f"{input_base_name}_k4_grouped.csv")
            
            output_cols = list(grouped_result.columns)
            if 'GroupInfo' in output_cols and 'Notes/Codes' in output_cols:
                output_cols.remove('GroupInfo')
                notes_index = output_cols.index('Notes/Codes')
                output_cols.insert(notes_index + 1, 'GroupInfo')
                grouped_result = grouped_result[output_cols]
            
            grouped_result.to_csv(grouped_output_file, sep=';', decimal=',', index=False)
            logger.info(f"Grouped results saved to: {grouped_output_file}")
            
            # Generate SRU files (if not disabled)
            if not args.no_sru:            
                with debug_section("Generating SRU Files"):
                    generate_sru_files(grouped_result, config, output_dir)
            else:
                logger.info("SRU file generation skipped (--no-sru flag provided)")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()