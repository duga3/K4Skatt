import unittest
import os
import pandas as pd
import tempfile
import logging
from datetime import datetime
from uuid import uuid4
from io import StringIO
from src.sru_generator import validate_sru_config, generate_info_sru_file, generate_sru_files, generate_blankett_sru_file

# Configure logging capture for tests
logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_capture_string = StringIO()
handler = logging.StreamHandler(log_capture_string)
logger.addHandler(handler)

class TestSRUGenerator(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        
        # Mock configuration
        self.config = {
            'personal': {
                'personnummer': '19800101-1234',
                'namn': 'Test Person',
                'postnummer': '12345',
                'adress': 'Testgatan 1',
                'postort': 'Teststad',
                'email': 'test@example.com',
                'inkomstar': '2023'
            }
        }
        
        # Mock data for testing Section A and Section D differentiation
        self.mock_data = pd.DataFrame([
            # Section A
            {
                'Symbol': 'AAPL',
                'Beteckning': 'Apple Inc.',
                'Antal': 10,
                'Försäljningspris': 15000,
                'Omkostnadsbelopp': 12000,
                'Vinst': 3000,
                'Förlust': 0
            },
            {
                'Symbol': 'GOOGL',
                'Beteckning': 'Alphabet Inc.',
                'Antal': 5,
                'Försäljningspris': 10000,
                'Omkostnadsbelopp': 11000,
                'Vinst': 0,
                'Förlust': 1000
            },
            # Section D
            {
                'Symbol': 'BTC',
                'Beteckning': 'Bitcoin',
                'Antal': 2,
                'Försäljningspris': 20000,
                'Omkostnadsbelopp': 15000,
                'Vinst': 5000,
                'Förlust': 0
            },
            {
                'Symbol': 'ETH',
                'Beteckning': 'Ethereum',
                'Antal': 3,
                'Försäljningspris': 9000,
                'Omkostnadsbelopp': 10000,
                'Vinst': 0,
                'Förlust': 1000
            }
        ])

        # Mock data for testing multiple pages (>9 trades for A, >7 for D)
        self.multi_page_data = pd.DataFrame()
        # Section A: 10 trades
        for i in range(10):
            self.multi_page_data = pd.concat([self.multi_page_data, pd.DataFrame([{
                'Symbol': 'AAPL',
                'Beteckning': f'Apple Inc. Trade {i+1}',
                'Antal': 10,
                'Försäljningspris': 15000,
                'Omkostnadsbelopp': 12000,
                'Vinst': 3000,
                'Förlust': 0
            }])], ignore_index=True)
        # Section D: 10 trades
        for i in range(10):
            self.multi_page_data = pd.concat([self.multi_page_data, pd.DataFrame([{
                'Symbol': 'BTC',
                'Beteckning': f'Bitcoin Trade {i+1}',
                'Antal': 2,
                'Försäljningspris': 20000,
                'Omkostnadsbelopp': 15000,
                'Vinst': 5000,
                'Förlust': 0
            }])], ignore_index=True)

        # Mock data for testing long Beteckning
        self.long_beteckning_data = pd.DataFrame([
            {
                'Symbol': 'AAPL',
                'Beteckning': 'Apple Inc. Very Long Description That Tests The Eighty Character Limit For Beteckning Field',
                'Antal': 10,
                'Försäljningspris': 15000,
                'Omkostnadsbelopp': 12000,
                'Vinst': 3000,
                'Förlust': 0
            }
        ])

        # Mock data for single Section A trade
        self.single_section_a_data = pd.DataFrame([
            {
                'Symbol': 'AAPL',
                'Beteckning': 'Apple Inc.',
                'Antal': 10,
                'Försäljningspris': 15000,
                'Omkostnadsbelopp': 12000,
                'Vinst': 3000,
                'Förlust': 0
            }
        ])

        # Mock data for single Section D trade
        self.single_section_d_data = pd.DataFrame([
            {
                'Symbol': 'BTC',
                'Beteckning': 'Bitcoin',
                'Antal': 2,
                'Försäljningspris': 20000,
                'Omkostnadsbelopp': 15000,
                'Vinst': 5000,
                'Förlust': 0
            }
        ])

    def tearDown(self):
        # Clean up temporary directory
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)
        # Clear log capture
        log_capture_string.truncate(0)
        log_capture_string.seek(0)

    def test_validate_sru_config_valid(self):
        """Test valid configuration"""
        result = validate_sru_config(self.config)
        self.assertTrue(result)

    def test_validate_sru_config_missing_personal(self):
        """Test configuration missing personal section"""
        invalid_config = {}
        result = validate_sru_config(invalid_config)
        self.assertFalse(result)

    def test_validate_sru_config_missing_field(self):
        """Test configuration missing required field"""
        invalid_config = self.config.copy()
        del invalid_config['personal']['namn']
        result = validate_sru_config(invalid_config)
        self.assertFalse(result)

    def test_generate_info_sru_file(self):
        """Test INFO.SRU file generation"""
        generate_info_sru_file(self.config, self.temp_dir)
        info_path = os.path.join(self.temp_dir, "INFO.SRU")
        
        self.assertTrue(os.path.exists(info_path))
        
        with open(info_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        expected_lines = [
            "#DATABESKRIVNING_START",
            "#PRODUKT SRU",
            "#FILNAMN BLANKETTER.SRU",
            "#DATABESKRIVNING_SLUT",
            "#MEDIELEV_START",
            "#ORGNR 198001011234",
            "#NAMN Test Person",
            "#ADRESS Testgatan 1",
            "#POSTNR 12345",
            "#POSTORT Teststad",
            "#EMAIL test@example.com",
            "#MEDIELEV_SLUT"
        ]
        
        for line in expected_lines:
            self.assertIn(line, content)

    def test_generate_blankett_sru_file_section_a_and_d(self):
        """Test BLANKETTER.SRU file generation with Section A and D differentiation"""
        blanketter_path = os.path.join(self.temp_dir, "BLANKETTER.SRU")
        generate_blankett_sru_file(self.mock_data, self.config, blanketter_path)
        
        self.assertTrue(os.path.exists(blanketter_path))
        
        with open(blanketter_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
        
        # Verify Section A entries (AAPL and GOOGL)
        self.assertIn("#UPPGIFT 3100 10\n", content)  # AAPL Antal
        self.assertIn("#UPPGIFT 3101 Apple Inc.\n", content)  # AAPL Beteckning
        self.assertIn("#UPPGIFT 3102 15000\n", content)  # AAPL Försäljningspris
        self.assertIn("#UPPGIFT 3103 12000\n", content)  # AAPL Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3104 3000\n", content)  # AAPL Vinst
        self.assertIn("#UPPGIFT 3105 0\n", content)  # AAPL Förlust
        
        self.assertIn("#UPPGIFT 3110 5\n", content)  # GOOGL Antal
        self.assertIn("#UPPGIFT 3111 Alphabet Inc.\n", content)  # GOOGL Beteckning
        self.assertIn("#UPPGIFT 3112 10000\n", content)  # GOOGL Försäljningspris
        self.assertIn("#UPPGIFT 3113 11000\n", content)  # GOOGL Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3114 0\n", content)  # GOOGL Vinst
        self.assertIn("#UPPGIFT 3115 1000\n", content)  # GOOGL Förlust
        
        # Verify Section A summary
        self.assertIn("#UPPGIFT 3300 25000\n", content)  # Total Försäljningspris
        self.assertIn("#UPPGIFT 3301 23000\n", content)  # Total Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3304 3000\n", content)  # Total Vinst
        self.assertIn("#UPPGIFT 3305 1000\n", content)  # Total Förlust
        
        # Verify Section D entries (BTC and ETH)
        self.assertIn("#UPPGIFT 3410 2\n", content)  # BTC Antal
        self.assertIn("#UPPGIFT 3411 Bitcoin\n", content)  # BTC Beteckning
        self.assertIn("#UPPGIFT 3412 20000\n", content)  # BTC Försäljningspris
        self.assertIn("#UPPGIFT 3413 15000\n", content)  # BTC Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3414 5000\n", content)  # BTC Vinst
        self.assertIn("#UPPGIFT 3415 0\n", content)  # BTC Förlust
        
        self.assertIn("#UPPGIFT 3420 3\n", content)  # ETH Antal
        self.assertIn("#UPPGIFT 3421 Ethereum\n", content)  # ETH Beteckning
        self.assertIn("#UPPGIFT 3422 9000\n", content)  # ETH Försäljningspris
        self.assertIn("#UPPGIFT 3423 10000\n", content)  # ETH Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3424 0\n", content)  # ETH Vinst
        self.assertIn("#UPPGIFT 3425 1000\n", content)  # ETH Förlust
        
        # Verify Section D summary
        self.assertIn("#UPPGIFT 3500 29000\n", content)  # Total Försäljningspris
        self.assertIn("#UPPGIFT 3501 25000\n", content)  # Total Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3503 5000\n", content)  # Total Vinst
        self.assertIn("#UPPGIFT 3504 1000\n", content)  # Total Förlust
        
        # Verify blankett structure
        self.assertIn(f"#BLANKETT K4-{self.config['personal']['inkomstar']}P4\n", content)
        self.assertIn("#BLANKETTSLUT\n", content)
        self.assertIn("#FIL_SLUT\n", content)

    def test_generate_sru_files(self):
        """Test generation of both INFO.SRU and BLANKETTER.SRU files"""
        generate_sru_files(self.mock_data, self.config, self.temp_dir)
        
        info_path = os.path.join(self.temp_dir, "INFO.SRU")
        blanketter_path = os.path.join(self.temp_dir, "BLANKETTER.SRU")
        
        self.assertTrue(os.path.exists(info_path))
        self.assertTrue(os.path.exists(blanketter_path))

    def test_empty_data(self):
        """Test handling of empty DataFrame"""
        empty_data = pd.DataFrame(columns=['Symbol', 'Beteckning', 'Antal', 'Försäljningspris', 'Omkostnadsbelopp', 'Vinst', 'Förlust'])
        blanketter_path = os.path.join(self.temp_dir, "BLANKETTER.SRU")
        generate_blankett_sru_file(empty_data, self.config, blanketter_path)
        
        self.assertTrue(os.path.exists(blanketter_path))
        
        with open(blanketter_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
        
        # Should still have basic structure but no data entries
        self.assertIn(f"#BLANKETT K4-{self.config['personal']['inkomstar']}P4\n", content)
        self.assertIn("#BLANKETTSLUT\n", content)
        self.assertIn("#FIL_SLUT\n", content)
        self.assertNotIn("#UPPGIFT 31", content)  # No Section A data
        self.assertNotIn("#UPPGIFT 34", content)  # No Section D data

    def test_generate_blankett_sru_file_multiple_pages(self):
        """Test BLANKETTER.SRU file generation with more than 9 trades for A and 7 for D requiring multiple pages"""
        blanketter_path = os.path.join(self.temp_dir, "BLANKETTER.SRU")
        generate_blankett_sru_file(self.multi_page_data, self.config, blanketter_path)

        self.assertTrue(os.path.exists(blanketter_path))

        with open(blanketter_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
        
        # Count number of blanketts (should be 2: 10 trades for A needs 2, 10 for D needs 2)
        blankett_lines = [line for line in content if line.startswith("#BLANKETT") and not line.startswith("#BLANKETTSLUT")]
        blankett_count = len(blankett_lines)
        self.assertEqual(blankett_count, 2, "Should generate 2 blanketts")

        # Verify first blankett (9 trades for Section A, 7 for Section D)
        # Section A: First trade
        self.assertIn("#UPPGIFT 3100 10\n", content)  # Apple Trade 1 Antal
        self.assertIn("#UPPGIFT 3101 Apple Inc. Trade 1\n", content)  # Apple Trade 1 Beteckning
        self.assertIn("#UPPGIFT 3102 15000\n", content)  # Apple Trade 1 Försäljningspris
        self.assertIn("#UPPGIFT 3103 12000\n", content)  # Apple Trade 1 Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3104 3000\n", content)  # Apple Trade 1 Vinst
        self.assertIn("#UPPGIFT 3105 0\n", content)  # Apple Trade 1 Förlust

        # Section A: Last trade in first blankett
        self.assertIn("#UPPGIFT 3180 10\n", content)  # Apple Trade 9 Antal
        self.assertIn("#UPPGIFT 3181 Apple Inc. Trade 9\n", content)  # Apple Trade 9 Beteckning

        # Section A summary for first blankett (9 trades)
        self.assertIn("#UPPGIFT 3300 135000\n", content)  # 9 * 15000
        self.assertIn("#UPPGIFT 3301 108000\n", content)  # 9 * 12000
        self.assertIn("#UPPGIFT 3304 27000\n", content)  # 9 * 3000
        self.assertIn("#UPPGIFT 3305 0\n", content)  # 9 * 0

        # Section D: First trade
        self.assertIn("#UPPGIFT 3410 2\n", content)  # Bitcoin Trade 1 Antal
        self.assertIn("#UPPGIFT 3411 Bitcoin Trade 1\n", content)  # Bitcoin Trade 1 Beteckning
        self.assertIn("#UPPGIFT 3412 20000\n", content)  # Bitcoin Trade 1 Försäljningspris
        self.assertIn("#UPPGIFT 3413 15000\n", content)  # Bitcoin Trade 1 Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3414 5000\n", content)  # Bitcoin Trade 1 Vinst
        self.assertIn("#UPPGIFT 3415 0\n", content)  # Bitcoin Trade 1 Förlust

        # Section D: Last trade in first blankett
        self.assertIn("#UPPGIFT 3470 2\n", content)  # Bitcoin Trade 7 Antal
        self.assertIn("#UPPGIFT 3471 Bitcoin Trade 7\n", content)  # Bitcoin Trade 7 Beteckning

        # Section D summary for first blankett (7 trades)
        self.assertIn("#UPPGIFT 3500 140000\n", content)  # 7 * 20000
        self.assertIn("#UPPGIFT 3501 105000\n", content)  # 7 * 15000
        self.assertIn("#UPPGIFT 3503 35000\n", content)  # 7 * 5000
        self.assertIn("#UPPGIFT 3504 0\n", content)  # 7 * 0

        # Verify second blankett (1 trade for Section A, 3 for Section D)
        second_blankett_start = content.index("#BLANKETT K4-2023P4\n", content.index("#BLANKETTSLUT\n"))
        second_blankett_content = content[second_blankett_start:]

        # Section A: Last trade
        self.assertIn("#UPPGIFT 3100 10\n", second_blankett_content)  # Apple Trade 10 Antal
        self.assertIn("#UPPGIFT 3101 Apple Inc. Trade 10\n", second_blankett_content)  # Apple Trade 10 Beteckning

        # Section A summary for second blankett (1 trade)
        self.assertIn("#UPPGIFT 3300 15000\n", second_blankett_content)  # 1 * 15000
        self.assertIn("#UPPGIFT 3301 12000\n", second_blankett_content)  # 1 * 12000
        self.assertIn("#UPPGIFT 3304 3000\n", second_blankett_content)  # 1 * 3000
        self.assertIn("#UPPGIFT 3305 0\n", second_blankett_content)  # 1 * 0

        # Section D: First trade in second blankett
        self.assertIn("#UPPGIFT 3410 2\n", second_blankett_content)  # Bitcoin Trade 8 Antal
        self.assertIn("#UPPGIFT 3411 Bitcoin Trade 8\n", second_blankett_content)  # Bitcoin Trade 8 Beteckning

        # Section D: Last trade in second blankett
        self.assertIn("#UPPGIFT 3430 2\n", second_blankett_content)  # Bitcoin Trade 10 Antal
        self.assertIn("#UPPGIFT 3431 Bitcoin Trade 10\n", second_blankett_content)  # Bitcoin Trade 10 Beteckning

        # Section D summary for second blankett (3 trades)
        self.assertIn("#UPPGIFT 3500 60000\n", second_blankett_content)  # 3 * 20000
        self.assertIn("#UPPGIFT 3501 45000\n", second_blankett_content)  # 3 * 15000
        self.assertIn("#UPPGIFT 3503 15000\n", second_blankett_content)  # 3 * 5000
        self.assertIn("#UPPGIFT 3504 0\n", second_blankett_content)  # 3 * 0

        # Verify blankett numbers
        self.assertIn("#UPPGIFT 7014 1\n", content)  # First blankett
        self.assertIn("#UPPGIFT 7014 2\n", content)  # Second blankett

        # Verify file structure
        self.assertEqual(content.count("#BLANKETTSLUT\n"), 2)
        self.assertIn("#FIL_SLUT\n", content)

    def test_generate_blankett_sru_file_long_beteckning(self):
        """Test BLANKETTER.SRU file generation with long Beteckning"""
        blanketter_path = os.path.join(self.temp_dir, "BLANKETTER.SRU")
        generate_blankett_sru_file(self.long_beteckning_data, self.config, blanketter_path)

        self.assertTrue(os.path.exists(blanketter_path))

        with open(blanketter_path, 'r', encoding='utf-8') as f:
            content = f.readlines()

        # Verify long Beteckning (80 characters)
        expected_beteckning = "Apple Inc. Very Long Description That Tests The Eighty Character Limit For Beteckning Field"
        self.assertIn(f"#UPPGIFT 3101 {expected_beteckning[:80]}\n", content)

    def test_generate_blankett_sru_file_single_section_a(self):
        """Test BLANKETTER.SRU file generation with a single Section A trade"""
        blanketter_path = os.path.join(self.temp_dir, "BLANKETTER.SRU")
        
        # Clear log capture before running
        log_capture_string.truncate(0)
        log_capture_string.seek(0)
        
        generate_blankett_sru_file(self.single_section_a_data, self.config, blanketter_path)

        self.assertTrue(os.path.exists(blanketter_path))

        with open(blanketter_path, 'r', encoding='utf-8') as f:
            content = f.readlines()

        # Verify Section A entry (AAPL)
        self.assertIn("#UPPGIFT 3100 10\n", content)  # Antal
        self.assertIn("#UPPGIFT 3101 Apple Inc.\n", content)  # Beteckning
        self.assertIn("#UPPGIFT 3102 15000\n", content)  # Försäljningspris
        self.assertIn("#UPPGIFT 3103 12000\n", content)  # Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3104 3000\n", content)  # Vinst
        self.assertIn("#UPPGIFT 3105 0\n", content)  # Förlust

        # Verify Section A summary
        self.assertIn("#UPPGIFT 3300 15000\n", content)  # Total Försäljningspris
        self.assertIn("#UPPGIFT 3301 12000\n", content)  # Total Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3304 3000\n", content)  # Total Vinst
        self.assertIn("#UPPGIFT 3305 0\n", content)  # Total Förlust

        # Verify no Section D entries
        self.assertNotIn("#UPPGIFT 34", content)  # No Section D data

        # Verify blankett structure
        self.assertIn(f"#BLANKETT K4-{self.config['personal']['inkomstar']}P4\n", content)
        self.assertIn("#UPPGIFT 7014 1\n", content)  # Single blankett
        self.assertIn("#BLANKETTSLUT\n", content)
        self.assertIn("#FIL_SLUT\n", content)

    def test_generate_blankett_sru_file_single_section_d(self):
        """Test BLANKETTER.SRU file generation with a single Section D trade"""
        blanketter_path = os.path.join(self.temp_dir, "BLANKETTER.SRU")
        
        # Clear log capture before running
        log_capture_string.truncate(0)
        log_capture_string.seek(0)
        
        generate_blankett_sru_file(self.single_section_d_data, self.config, blanketter_path)

        self.assertTrue(os.path.exists(blanketter_path))

        with open(blanketter_path, 'r', encoding='utf-8') as f:
            content = f.readlines()

        # Verify Section D entry (BTC)
        self.assertIn("#UPPGIFT 3410 2\n", content)  # Antal
        self.assertIn("#UPPGIFT 3411 Bitcoin\n", content)  # Beteckning
        self.assertIn("#UPPGIFT 3412 20000\n", content)  # Försäljningspris
        self.assertIn("#UPPGIFT 3413 15000\n", content)  # Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3414 5000\n", content)  # Vinst
        self.assertIn("#UPPGIFT 3415 0\n", content)  # Förlust

        # Verify Section D summary
        self.assertIn("#UPPGIFT 3500 20000\n", content)  # Total Försäljningspris
        self.assertIn("#UPPGIFT 3501 15000\n", content)  # Total Omkostnadsbelopp
        self.assertIn("#UPPGIFT 3503 5000\n", content)  # Total Vinst
        self.assertIn("#UPPGIFT 3504 0\n", content)  # Total Förlust

        # Verify no Section A entries
        self.assertNotIn("#UPPGIFT 31", content)  # No Section A data

        # Verify blankett structure
        self.assertIn(f"#BLANKETT K4-{self.config['personal']['inkomstar']}P4\n", content)
        self.assertIn("#UPPGIFT 7014 1\n", content)  # Single blankett
        self.assertIn("#BLANKETTSLUT\n", content)
        self.assertIn("#FIL_SLUT\n", content)

if __name__ == '__main__':
    unittest.main()