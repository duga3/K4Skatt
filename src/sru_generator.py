import logging
import os
import pandas as pd
from datetime import datetime
from typing import Dict, List

# Configure logging
logger = logging.getLogger(__name__)

def validate_sru_config(config: Dict) -> bool:
    if 'personal' not in config:
        logger.error("Configuration missing 'personal' section")
        return False
    
    personal_fields = ['personnummer', 'namn', 'postnummer', 'adress', 'postort', 'email', 'inkomstar']
    for field in personal_fields:
        if field not in config['personal']:
            logger.error(f"Missing required field in personal config: {field}")
            return False
    
    personnummer = config['personal']['personnummer'].replace('-', '')
    if not len(personnummer) == 12:
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
        for line in info_lines:
            f.write(line + "\n")
            
    logger.info(f"INFO.SRU file generated: {info_path}")
    
def generate_sru_files(result_data: pd.DataFrame, config: Dict, output_dir: str) -> None:
    blanketter_path = os.path.join(output_dir, "BLANKETTER.SRU")
    
    generate_info_sru_file(config, output_dir)
    generate_blankett_sru_file(result_data, config, blanketter_path)
    
    logger.info(f"SRU files generated in directory: {output_dir}")
    logger.info(f"  - BLANKETTER.SRU (contains all transactions)")
    logger.info(f"  - INFO.SRU (contains delivery information)")
    
def format_sru_line(tag: str, value: str) -> str:
    return f"#UPPGIFT {tag} {value}"

def generate_blankett_sru_file(result_data: pd.DataFrame, config: Dict, output_path: str) -> None:
    logger.info("Generating SRU file...")
    MAX_TRADES_PER_SECTION_A = 9
    MAX_TRADES_PER_SECTION_D = 7
    
    SECTION_D_INSTRUMENTS = ['BITW', 'BTC', 'ETH', 'GBTC', 'ETHE', 'SOL', 'DOT', 'ADA']
    
    TEST_LIMIT = 2000
    if len(result_data) > TEST_LIMIT:
        logger.warning(f"TESTING MODE: Limiting to {TEST_LIMIT} trades for testing purposes")
        result_data = result_data.head(TEST_LIMIT)
    
    if not validate_sru_config(config):
        logger.error("Invalid SRU configuration. SRU file generation aborted.")
        return
    
    personal = config['personal']
    
    section_d_mask = result_data['Symbol'].isin(SECTION_D_INSTRUMENTS)
    section_d_data = result_data[section_d_mask].copy()
    section_a_data = result_data[~section_d_mask].copy()
    
    total_section_a = len(section_a_data)
    total_section_d = len(section_d_data)
    
    logger.info(f"Found {total_section_a} securities for Section A and {total_section_d} for Section D")
    
    num_blanketts_a = (total_section_a + MAX_TRADES_PER_SECTION_A - 1) // MAX_TRADES_PER_SECTION_A
    num_blanketts_d = (total_section_d + MAX_TRADES_PER_SECTION_D - 1) // MAX_TRADES_PER_SECTION_D
    num_blanketts = max(num_blanketts_a, num_blanketts_d, 1)  # Ensure at least 1 blankett
    
    logger.info(f"Will generate {num_blanketts} blanketts")
    
    sru_lines = []
    
    timestamp = datetime.now().strftime("%Y%m%d %H%M%S")
    personnummer = personal['personnummer'].replace('-', '')
    
    total_gain_a = 0
    total_loss_a = 0
    total_gain_d = 0
    total_loss_d = 0
    
    for blankett_index in range(num_blanketts):
        has_data = False  # Track if this blankett has any data
        
        sru_lines.append(f"#BLANKETT K4-{personal['inkomstar']}P4")
        sru_lines.append(f"#IDENTITET {personnummer} {timestamp}")
        
        # Section A
        section_a_start = blankett_index * MAX_TRADES_PER_SECTION_A
        section_a_end = min((blankett_index + 1) * MAX_TRADES_PER_SECTION_A, total_section_a)
        blankett_section_a = section_a_data.iloc[section_a_start:section_a_end] if section_a_start < total_section_a else pd.DataFrame()
        
        if not blankett_section_a.empty:
            has_data = True
            blankett_gain_a = blankett_section_a['Vinst'].sum()
            blankett_loss_a = blankett_section_a['Förlust'].sum()
            total_gain_a += blankett_gain_a
            total_loss_a += blankett_loss_a
            
            for i, (_, row) in enumerate(blankett_section_a.iterrows()):
                beteckning = row['Beteckning']
                if len(beteckning) > 80:
                    beteckning = beteckning[:80]
                
                sru_lines.append(format_sru_line(f"31{i}0", str(int(row['Antal']))))
                sru_lines.append(format_sru_line(f"31{i}1", beteckning))
                sru_lines.append(format_sru_line(f"31{i}2", str(int(row['Försäljningspris']))))
                sru_lines.append(format_sru_line(f"31{i}3", str(int(row['Omkostnadsbelopp']))))
                sru_lines.append(format_sru_line(f"31{i}4", str(int(row['Vinst']))))
                sru_lines.append(format_sru_line(f"31{i}5", str(int(row['Förlust']))))
            
            sru_lines.append(format_sru_line("3300", str(int(blankett_section_a['Försäljningspris'].sum()))))
            sru_lines.append(format_sru_line("3301", str(int(blankett_section_a['Omkostnadsbelopp'].sum()))))
            sru_lines.append(format_sru_line("3304", str(int(blankett_section_a['Vinst'].sum()))))
            sru_lines.append(format_sru_line("3305", str(int(blankett_section_a['Förlust'].sum()))))
        
        # Section D
        section_d_start = blankett_index * MAX_TRADES_PER_SECTION_D
        section_d_end = min((blankett_index + 1) * MAX_TRADES_PER_SECTION_D, total_section_d)
        blankett_section_d = section_d_data.iloc[section_d_start:section_d_end] if section_d_start < total_section_d else pd.DataFrame()
        
        if not blankett_section_d.empty:
            has_data = True
            blankett_gain_d = blankett_section_d['Vinst'].sum()
            blankett_loss_d = blankett_section_d['Förlust'].sum()
            total_gain_d += blankett_gain_d
            total_loss_d += blankett_loss_d
            
            for i, (_, row) in enumerate(blankett_section_d.iterrows()):
                beteckning = row['Beteckning']
                if len(beteckning) > 80:
                    beteckning = beteckning[:80]
                
                sru_lines.append(format_sru_line(f"34{i+1}0", str(int(row['Antal']))))
                sru_lines.append(format_sru_line(f"34{i+1}1", beteckning))
                sru_lines.append(format_sru_line(f"34{i+1}2", str(int(row['Försäljningspris']))))
                sru_lines.append(format_sru_line(f"34{i+1}3", str(int(row['Omkostnadsbelopp']))))
                sru_lines.append(format_sru_line(f"34{i+1}4", str(int(row['Vinst']))))
                sru_lines.append(format_sru_line(f"34{i+1}5", str(int(row['Förlust']))))
            
            sru_lines.append(format_sru_line("3500", str(int(blankett_section_d['Försäljningspris'].sum()))))
            sru_lines.append(format_sru_line("3501", str(int(blankett_section_d['Omkostnadsbelopp'].sum()))))
            sru_lines.append(format_sru_line("3503", str(int(blankett_section_d['Vinst'].sum()))))
            sru_lines.append(format_sru_line("3504", str(int(blankett_section_d['Förlust'].sum()))))
        
        # Only include blankett if it has data or is the first blankett (for empty case)
        if has_data or blankett_index == 0:
            sru_lines.append(format_sru_line("7014", str(blankett_index + 1)))
            sru_lines.append("#BLANKETTSLUT")
        else:
            # Remove blankett header and identity if no data
            sru_lines = sru_lines[:-2]
    
    sru_lines.append("#FIL_SLUT")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in sru_lines:
            f.write(line + "\n")
    
    # Enhanced logging output
    logger.info("SRU File Generation Summary")
    logger.info("---------------------------------------")
    logger.info(f"SRU File: {output_path}")
    logger.info("")
    logger.info("Section A (Securities)")
    logger.info(f"  Number of Securities: {total_section_a}")
    logger.info(f"  Total Gain:          {int(total_gain_a)} SEK")
    logger.info(f"  Total Loss:          {int(total_loss_a)} SEK")
    logger.info("")
    logger.info("Section D (Cryptocurrencies)")
    logger.info(f"  Number of Securities: {total_section_d}")
    logger.info(f"  Total Gain:          {int(total_gain_d)} SEK")
    logger.info(f"  Total Loss:          {int(total_loss_d)} SEK")
    logger.info("")
    logger.info("Totals")
    logger.info(f"  Total Securities:    {total_section_a + total_section_d}")
    logger.info(f"  Total Gain:          {int(total_gain_a + total_gain_d)} SEK (Report in K4 Declaration)")
    logger.info(f"  Total Loss:          {int(total_loss_a + total_loss_d)} SEK (Report in K4 Declaration)")
    logger.info("")
    logger.info(f"Total Blanketts Generated: {num_blanketts}")
    logger.info("---------------------------------------")