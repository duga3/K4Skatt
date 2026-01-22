# K4Skatt

**K4Skatt** is a Python script designed to generate K4 tax forms and SRU files from Interactive Brokers (IBKR) trade data for Swedish tax submissions. It processes trade data, supports option trades (including long and short positions, assignments, and exercises), and allows the inclusion of pre-calculated trades from other sources to ensure all your trade data is accurately reflected in the output files.

---

## Features

- Processes IBKR trade data to generate K4 tax forms.
- Generates SRU files (`INFO.SRU` and `BLANKETTER.SRU`) for submission to Skatteverket.
- Supports **option trades**, including:
  - Long and short options
  - Assignments
  - Exercises
- Includes pre-calculated trades from non-IBKR sources.
- Automatically groups partial executions for simplified reporting.
- Simple command-line interface for ease of use.

## Quick start

1. Install Python 3 and `pandas` (see prerequisites below).
2. Generate a default config if you do not have one yet:
   ```bash
   python src/k4_script.py --create-config --config config.json
   ```
3. Run the example IBKR export to verify everything works:
   ```bash
   python src/k4_script.py input/example.csv --config config.json
   ```
   The K4 CSVs and SRU files will appear in `output/`.

---

## Prerequisites

- **Python 3.9+**
- **Python packages**: `pandas`

Install the dependency with:

```bash
pip install pandas
```

---

## Preparing Interactive Brokers trade data

1. **Create a Flex Query Report** in IBKR Client Portal:
   - Reports → Flex Queries → Create New Flex Query → **Trades**.
   - Configure **Date/Time** without separator and use the format `YYYYMMDDHHMMSS`.
   - Include these fields:
     - `DateTime`
     - `Buy/Sell`
     - `Open/Close Indicator`
     - `AssetClass`
     - `Description`
     - `Quantity`
     - `Cost Basis`
     - `Proceeds`
     - `Currency`
     - `IB Commission`
     - `Realized P/L`
     - `Notes/Codes`
     - `Symbol`
     - `Underlying Symbol`
2. **Save and Run** the Flex Query.
3. **Export the Report** as **CSV**.
4. Place the CSV file in a convenient location (e.g., the `input/` directory, though any path is accepted by the script).

---

## Installation

1. Clone or download the repository to your local machine.
2. Ensure the script files (`k4_script.py`, `sru_generator.py`, etc.) are located in the `src/` directory.
3. *(Optional)* Place your IBKR trade data CSV file in the `input/` directory for organization (any path works).
4. *(Optional)* If you have additional trade data, place it in the `input/` directory or another accessible location.
5. Update `config.json` with your personal details and currency exchange rates (or generate it with `--create-config`). See **Config File** below.

---

## Config File

The script uses `config.json` (default path) for personal information and FX rates. If it doesn’t exist, generate a default one with `--create-config`.

Here’s the expected structure:

```json
{
    "personal": {
        "personnummer": "YYYYMMDD-XXXX",
        "namn": "Förnamn Efternamn",
        "adress": "Gatan 1",
        "postnummer": "XXXXX",
        "postort": "Staden",
        "email": "example@email.com",
        "inkomstar": "2025"
    },
    "fx_rates": {
        "USD": 10.5,
        "CHF": 12.2,
        "SEK": 1.0,
        "EUR": 10.0
    }
}
```

- **Personal Information**: Update with your details (e.g., `personnummer`, `namn`, etc.).
- **`inkomstar`**: Set to the tax year you’re reporting. Defaults to the previous year if not specified.
- **`fx_rates`**: Provide exchange rates (in SEK) for all currencies in your trade data. Ensure every currency present in your trades is included to avoid errors. You can get the official rates from [Riksbankens website](https://www.riksbank.se/sv/statistik/rantor-och-valutakurser/sok-rantor-och-valutakurser/).

---

## Usage

Run the script from the command line with:

```bash
python src/k4_script.py input/ib_trades.csv --config config.json
```

### Options

| Option                | Description                                                          |
|-----------------------|----------------------------------------------------------------------|
| `input_file`          | Path to the IBKR trades CSV file (required unless creating config).  |
| `--config`            | Path to the configuration file (default: `config.json`).             |
| `--create-config`     | Create a default `config.json` file and exit if no input file is provided. |
| `--verbose`           | Enable detailed logging for debugging.                               |
| `--no-sru`            | Skip SRU file generation.                                            |
| `--additional-trades` | Path to a CSV file with pre-calculated trades from other sources.     |

#### Examples

- **Basic usage**:
  ```bash
  python src/k4_script.py input/ib_trades.csv --config config.json
  ```

- **With additional trades**:
  ```bash
  python src/k4_script.py input/ib_trades.csv --additional-trades input/additional_trades.csv --config config.json
  ```

- **Create a default config file**:
  ```bash
  python src/k4_script.py --create-config
  ```

### Additional trades CSV format

If you pass `--additional-trades`, the file must be **semicolon-separated**, use comma as the decimal separator, and include these columns:

- `Symbol`
- `Beteckning`
- `Antal`
- `Försäljningspris`
- `Omkostnadsbelopp`
- `Vinst`
- `Förlust`

All monetary values must be integers in SEK (e.g., `1000` for 1,000 SEK). Missing columns cause the run to fail early.

## Output

The script generates the following files in the `output/` directory, with names based on the input file’s base name (e.g., for `input/ib_trades.csv`, the base name is `ib_trades`):

- **K4 Report**: A detailed CSV of processed trades (`output/<input_base_name>_k4.csv`).
- **Grouped K4 Report**: A CSV with grouped partial executions (`output/<input_base_name>_k4_grouped.csv`).
- **SRU Files**: `INFO.SRU` and `BLANKETTER.SRU` for tax submission, located in the `output/` directory (unless `--no-sru` is specified).

**Notes**:
- Output CSVs use **semicolon (;)** as the delimiter and **comma (,)** as the decimal separator.
- Partial executions (trades with a `P` in `Notes/Codes`) are automatically grouped by `BuySell`, `TradeDate`, and `Beteckning` in the grouped report.
- SRU files are generated from the combined data (IBKR trades plus additional trades, if provided).

---

## Uploading Results to Skatteverket

If you have fewer than 300 trades to report, you can upload the `BLANKETTER.SRU` file directly during the Inkomstdeklaration 1 process as your K4 form. For more than 300 trades, you’ll need to use Skatteverket’s file transfer service ([filöverföring](https://www.skatteverket.se/foretag/etjansterochblanketter/allaetjanster/tjanster/filoverforing.4.1f604301062bf0c47e8000527.html)). After uploading, the K4 forms will appear under "Mina sidor" in the "Inlämnade deklarationer" section within a few minutes.

## Disclaimer

**K4Skatt** is provided "as is" without warranty of any kind. Users are responsible for verifying the accuracy of the calculations and ensuring compliance with applicable tax laws.

---

## Kort svensk sammanfattning

**K4Skatt** är ett Python-skript som genererar K4-skattedeklarationer och SRU-filer från Interactive Brokers (IBKR) handelsdata för svenska skattedeklarationer. Det stödjer optioner (långa och korta positioner, lösen och tvångslösen) samt inkludering av förberäknade affärer från andra källor. Utdatafiler sparas i `output/`-mappen och inkluderar K4-rapporter och SRU-filer för inlämning till Skatteverket.