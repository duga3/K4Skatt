import logging
import os
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

SECTION_D_INSTRUMENTS = ['BITW', 'BTC', 'ETH', 'GBTC', 'ETHE', 'SOL', 'DOT', 'ADA']
MAX_TRADES_PER_SECTION_A = 9
MAX_TRADES_PER_SECTION_D = 7

def validate_sru_config(config: Dict) -> bool:
    if 'personal' not in config:
        logger.error("Configuration missing 'personal' section")
        return False
    
    required_fields = ['personnummer', 'namn', 'postnummer', 'adress', 'postort', 'email', 'inkomstar']
    for field in required_fields:
        if field not in config['personal']:
            logger.error(f"Missing required field in personal config: {field}")
            return False
    
    personnummer = config['personal']['personnummer'].replace('-', '')
    if len(personnummer) != 12:
        logger.warning(f"Personnummer format may be invalid: {config['personal']['personnummer']}")
    
    return True

def generate_info_sru_file(config: Dict, output_dir: str) -> None:
    info_path = os.path.join(output_dir, "INFO.SRU")
    personal = config['personal']
    personnummer = personal['personnummer'].replace('-', '')
    
    info_lines = [
        "#DATABESKRIVNING_START",
        "#PRODUKT SRU",
        "#FILNAMN BLANKETTER.SRU",
        "#DATABESKRIVNING_SLUT",
        "#MEDIELEV_START",
        f"#ORGNR {personnummer}",
        f"#NAMN {personal['namn']}",
        f"#ADRESS {personal['adress']}",
        f"#POSTNR {personal['postnummer']}",
        f"#POSTORT {personal['postort']}",
        f"#EMAIL {personal['email']}",
        "#MEDIELEV_SLUT"
    ]
    
    with open(info_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(info_lines) + "\n")
            
    logger.info(f"INFO.SRU file generated: {info_path}")

def generate_sru_files(result_data: pd.DataFrame, config: Dict, output_dir: str) -> None:
    blanketter_path = os.path.join(output_dir, "BLANKETTER.SRU")
    
    generate_info_sru_file(config, output_dir)
    generate_blankett_sru_file(result_data, config, blanketter_path)
    
    logger.info(f"SRU files generated in directory: {output_dir}")

def format_sru_line(tag: str, value: str) -> str:
    return f"#UPPGIFT {tag} {value}"

def append_section_data(sru_lines: List[str], data: pd.DataFrame, base_prefix: str, 
                       index_offset: int, summary_tags: List[Tuple[str, str]]) -> None:
    """Append section data and summaries to SRU lines."""
    for i, (_, row) in enumerate(data.iterrows()):
        idx = i + index_offset
        beteckning = row['Beteckning'][:80]  # Truncate to 80 chars
        
        sru_lines.append(format_sru_line(f"{base_prefix}{idx}0", str(int(row['Antal']))))
        sru_lines.append(format_sru_line(f"{base_prefix}{idx}1", beteckning))
        sru_lines.append(format_sru_line(f"{base_prefix}{idx}2", str(int(row['Försäljningspris']))))
        sru_lines.append(format_sru_line(f"{base_prefix}{idx}3", str(int(row['Omkostnadsbelopp']))))
        sru_lines.append(format_sru_line(f"{base_prefix}{idx}4", str(int(row['Vinst']))))
        sru_lines.append(format_sru_line(f"{base_prefix}{idx}5", str(int(row['Förlust']))))
    
    # Add summaries
    for tag, col in summary_tags:
        sru_lines.append(format_sru_line(tag, str(int(data[col].sum()))))

def generate_blankett_sru_file(result_data: pd.DataFrame, config: Dict, output_path: str) -> None:
    logger.info("Generating SRU file...")
    
    if not validate_sru_config(config):
        logger.error("Invalid SRU configuration. SRU file generation aborted.")
        return
    
    personal = config['personal']
    personnummer = personal['personnummer'].replace('-', '')
    timestamp = datetime.now().strftime("%Y%m%d %H%M%S")
    
    # Split data into sections
    section_d_mask = result_data['Symbol'].isin(SECTION_D_INSTRUMENTS)
    section_d_data = result_data[section_d_mask].copy()
    section_a_data = result_data[~section_d_mask].copy()
    
    total_section_a = len(section_a_data)
    total_section_d = len(section_d_data)
    
    logger.info(f"Section A: {total_section_a} securities | Section D: {total_section_d} cryptocurrencies")
    
    # Calculate number of blanketts needed
    num_blanketts_a = (total_section_a + MAX_TRADES_PER_SECTION_A - 1) // MAX_TRADES_PER_SECTION_A if total_section_a > 0 else 0
    num_blanketts_d = (total_section_d + MAX_TRADES_PER_SECTION_D - 1) // MAX_TRADES_PER_SECTION_D if total_section_d > 0 else 0
    num_blanketts = max(num_blanketts_a, num_blanketts_d, 1)
    
    logger.info(f"Generating {num_blanketts} blanketts")
    
    sru_lines = []
    
    for blankett_index in range(num_blanketts):
        sru_lines.append(f"#BLANKETT K4-{personal['inkomstar']}P4")
        sru_lines.append(f"#IDENTITET {personnummer} {timestamp}")
        
        # Section A data
        a_start = blankett_index * MAX_TRADES_PER_SECTION_A
        a_end = min((blankett_index + 1) * MAX_TRADES_PER_SECTION_A, total_section_a)
        blankett_a = section_a_data.iloc[a_start:a_end] if a_start < total_section_a else pd.DataFrame()
        
        if not blankett_a.empty:
            summary_tags_a = [('3300', 'Försäljningspris'), ('3301', 'Omkostnadsbelopp'), 
                             ('3304', 'Vinst'), ('3305', 'Förlust')]
            append_section_data(sru_lines, blankett_a, base_prefix='31', 
                              index_offset=0, summary_tags=summary_tags_a)
        
        # Section D data
        d_start = blankett_index * MAX_TRADES_PER_SECTION_D
        d_end = min((blankett_index + 1) * MAX_TRADES_PER_SECTION_D, total_section_d)
        blankett_d = section_d_data.iloc[d_start:d_end] if d_start < total_section_d else pd.DataFrame()
        
        if not blankett_d.empty:
            summary_tags_d = [('3500', 'Försäljningspris'), ('3501', 'Omkostnadsbelopp'), 
                             ('3503', 'Vinst'), ('3504', 'Förlust')]
            append_section_data(sru_lines, blankett_d, base_prefix='34', 
                              index_offset=1, summary_tags=summary_tags_d)
        
        sru_lines.append(format_sru_line("7014", str(blankett_index + 1)))
        sru_lines.append("#BLANKETTSLUT")
    
    sru_lines.append("#FIL_SLUT")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sru_lines) + '\n')
    
    # Log summary
    total_gain_a = section_a_data['Vinst'].sum() if not section_a_data.empty else 0
    total_loss_a = section_a_data['Förlust'].sum() if not section_a_data.empty else 0
    total_gain_d = section_d_data['Vinst'].sum() if not section_d_data.empty else 0
    total_loss_d = section_d_data['Förlust'].sum() if not section_d_data.empty else 0
    
    logger.info("=" * 50)
    logger.info("SRU FILE GENERATION SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Section A - Securities:     {total_section_a:5d} | Gain: {int(total_gain_a):10d} | Loss: {int(total_loss_a):10d}")
    logger.info(f"Section D - Crypto:         {total_section_d:5d} | Gain: {int(total_gain_d):10d} | Loss: {int(total_loss_d):10d}")
    logger.info("-" * 50)
    logger.info(f"TOTAL:                      {total_section_a + total_section_d:5d} | Gain: {int(total_gain_a + total_gain_d):10d} | Loss: {int(total_loss_a + total_loss_d):10d}")
    logger.info(f"Blanketts: {num_blanketts}")
    logger.info("=" * 50)