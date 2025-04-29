# K4Skatt

**K4Skatt** is a Python script designed to generate K4 tax forms and SRU files from Interactive Brokers (IB) trade data for Swedish tax submissions. It also supports the inclusion of pre-calculated trades from other sources, ensuring all your trade data is accurately reflected in the SRU files.

Additionally, the script fully supports **option trades**, including **long and short positions**, as well as **assignments** and **exercises**.

---

## Features

- Processes IB trade data to generate K4 tax forms.
- Includes pre-calculated trades from non-IB sources.
- Supports **option trades**, including:
  - Long and short options
  - Assignments
  - Exercises
- Generates SRU files (`INFO.SRU` and `BLANKETTER.SRU`) for submission to Skatteverket.
- Simple command-line interface for ease of use.

---

## Prerequisites

- Python 3.x installed on your system.
- Required Python libraries: `pandas`, `argparse`, `logging`, `json`, `os`.

You can install the required libraries using:

```bash
pip install pandas
```

---

## Preparing Interactive Brokers Trade Data

1. **Create a Flex Query Report** in Interactive Brokers (Client Portal):
   - Go to **Reports** > **Flex Queries** > **Create New Flex Query**.
   - Select **Trades** as the report type.
   - Include at least the following fields in your report:
     - `DateTime`
     - `Buy/Sell`
     - `Open/CloseIndicator`
     - `AssetClass`
     - `Description`
     - `Quantity`
     - `CostBasis`
     - `Proceeds`
     - `CurrencyPrimary`
     - `IBCommission`
     - `FifoPnlRealized`
     - `Notes/Codes`
     - `Symbol`
     - `UnderlyingSymbol`
2. **Save and Run** the Flex Query.
3. **Export the Report** as **CSV**.
4. Place the exported CSV file into the `input/` directory.

---

## Installation

1. Clone or download the repository to your local machine.
2. Ensure the script files (`k4_script.py`, `sru_generator.py`, etc.) are located in the `src/` directory.
3. Place your IB trade data CSV file in the `input/` directory.
4. *(Optional)* If you have additional trade data, place it in `input/` as well.
5. Update `config/config.json` with your personal details and any necessary settings.

---

## Usage

To run the script, use the following command:

```bash
python src/k4_script.py input/ib_trades.csv --config config/config.json
```

### Options

| Option | Description |
|:---|:---|
| `--output` | Specify a custom output CSV file name. |
| `--grouped-output` | Specify a custom grouped output CSV file name. |
| `--sru-output` | Specify a directory for SRU files (default: `output/`). |
| `--additional-trades` | Include a CSV file with pre-calculated trades from other sources. |
| `--verbose` | Enable detailed logging for debugging. |

**Example with additional trades:**

```bash
python src/k4_script.py input/ib_trades.csv --additional-trades input/additional_trades.csv --config config/config.json
```

---

## Output

- **K4 Report**: A detailed CSV of processed trades (`output/k4_report.csv`).
- **Grouped K4 Report**: A CSV with grouped partial executions (`output/k4_grouped.csv`).
- **SRU Files**: `INFO.SRU` and `BLANKETTER.SRU` for tax submission, located in the `output/` directory.

---

## Disclaimer

**K4Skatt** is provided "as is" without warranty of any kind. Users are responsible for verifying the accuracy of the calculations and ensuring compliance with applicable tax laws.

---

## Kort svensk sammanfattning

**K4Skatt** är ett Python-skript som genererar K4-skattedeklarationer och SRU-filer från Interactive Brokers (IB) handelsdata för svenska skattedeklarationer. Skriptet stödjer även inkludering av förberäknade affärer från andra källor. Skriptet hanterar även optioner, inklusive långa och korta positioner samt lösen och tvångslösen (assignments och exercises).  
Utdatafiler sparas i `output/`-mappen och inkluderar K4-rapporten och SRU-filer för inlämning till Skatteverket.
