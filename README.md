# Judgment Bench and Author Extraction System

A deterministic Python system for extracting structured information (bench composition and authored/delivered judges) from court decision PDFs. This solution uses only classical parsing techniques (regex and rule-based extraction) without any LLMs or machine learning models.

## Overview

This project processes court judgment PDF files and extracts:

- **Bench**: All judges listed as part of the bench (coram/present/before)
- **Author Judge**: Judge(s) who authored or delivered the final judgment

The system is designed to be:
- **Deterministic**: Same input always produces identical output
- **Reproducible**: Full code and dependencies declared
- **Non-LLM**: Uses only regex, rule-based patterns, and classical NLP
- **Robust**: Handles various document formats and formatting variations

## Quick Start

### Prerequisites

- Python 3.11 or higher  
- `uv` package manager (https://docs.astral.sh/uv/)

### Setup and Execution

```bash
# Clone the repository
git clone https://github.com/vishnu-siva/paralegal-lk-internship-assignment.git
cd paralegal-lk-internship-assignment

# Install Python dependencies using uv
uv sync

# Run the extraction pipeline
uv run extract-judgments
```

### Windows Troubleshooting (if `uv run extract-judgments` fails due to file lock)

On some Windows systems, antivirus/indexing can temporarily lock files inside `.venv`, causing a reinstall error when running the script entry point.

Use this fallback command (same extractor, same output):

```bash
# PowerShell
$env:PYTHONPATH='src'; uv run --no-sync python -m judgment_extractor.cli
```

Then run normal command again later:

```bash
uv run extract-judgments
```

### What Happens

The pipeline will:
1. Discover all `.pdf` files in the `data/` folder
2. Extract bench and judgment author information from each PDF
3. Generate one JSON output file per PDF into the `output/` folder
4. Print processing status and confirmation

### Output Format

For each input PDF, a JSON file is generated in `output/` with:

```json
{
  "source_file": "sample-judgment-1.pdf",
  "bench": ["Judge Name 1", "Judge Name 2"],
  "author_judge": ["Judge Name 1"]
}
```

**Output Filename**: Input filename with `.pdf` replaced by `.json`  
Example: `data/sample-judgment-1.pdf` → `output/sample-judgment-1.json`

### Example Usage

```bash
# After installation and setup:
uv run extract-judgments

# View results
cat output/sample-judgment-1.json
```

## Approach

### Extraction Methodology

The system employs a multi-strategy deterministic approach:

#### 1. **Bench Extraction** 

**Strategy Priority**:
1. **Header Analysis** (first 1000 characters): Identifies judge names in document header, typically formatted with judicial title markers (J., C.J., PC). Handles formats like:
   - `H. A. G. DE SILVA. J., AMERASINGHE. J. AND DHEERARATNE, J.`
   - `Jayantha Jayasuriya, PC; B.P. Aluwihare, PC,J; L.T.B.Dehideniya, J`

2. **Section Marker Search**: If header analysis yields no results, searches for explicit bench section markers:
   - Keywords: `Before:`, `CORAM:`, `Present:`
   - Extracts judge names from sections immediately following these markers

3. **Line-by-Line Processing**: For each candidate section:
   - Splits lines by "AND" to identify individual judges
   - Uses regex patterns to recognize judge names with titles
   - Validates extracted text matches judge naming conventions

#### 2. **Author Judge Extraction**

**Strategy Priority**:
1. **Explicit Attribution**: Searches for phrases indicating judgment authorship:
   - "delivered by [Judge Name]"
   - "judgment...delivered by [Judge Name]"
   - "written by [Judge Name]"

2. **Judgment Section Analysis**: Looks for judge names immediately after the `JUDGMENT` keyword:
   - Typically formatted as `JUDGE_NAME, J.` on a separate line
   - Example: `AMERASINGHE, J.` appearing right after `JUDGMENT`

3. **Parenthetical Attribution**: Finds judge names in footer-style parentheses:
   - Example: `(Amerasinghe, J.)` appearing in page footers

4. **Header-Based Search**: For documents where authorship isn't explicitly stated, searches beginning for judge names (used when bench is "judgment of the court")

#### 3. **Pattern Matching & Validation**

All extraction uses carefully designed regex patterns. Patterns account for:
- Abbreviated names: `H.A.G.` or `J.A.N.`
- Prefixes: `Dr.`, `Mr.`, `Ms.`, `Mrs.`
- Titles: `J.`, `C.J.`, `PC`, `CJ`
- Multi-word names: `de Silva`, `Aluwihare`
- Special characters: hyphens and periods

### Handling Formatting Variations

The system robustly handles:
- **Case Variations**: CORAM, Coram, coram
- **Whitespace**: Extra spaces, line breaks, indentation
- **Title Formats**: `J.`, `J`, `CJ`, `C.J.`, `PC`, `PC,J`
- **Name Formats**: "Judge Name", "Justice Name", abbreviated initials
- **Separators**: "AND", ",", ";", "." between judge names
- **Special Characters**: Hyphens, periods within names

### Design Decisions

- **Header Priority**: Checking the document header first maximizes accuracy since bench is typically listed prominently at the start
- **Fallback Strategies**: Multiple extraction paths ensure robustness across different document formats
- **No External Models**: All operations use deterministic regex and string operations - no ML or language models
- **Line-Aware Processing**: Splits by lines to avoid capturing multi-line text fragments
- **Validation**: Extracted data is validated using Pydantic models before JSON serialization

## Project Structure

```
.
├── src/
│   └── judgment_extractor/
│       ├── __init__.py              # Package initialization
│       ├── models.py                # Pydantic data validation models
│       ├── extractor.py             # Core extraction logic (deterministic)
│       └── cli.py                   # Command-line interface
├── tests/
│   └── test_extractor.py            # Unit and integration tests
├── data/                            # Input PDF files directory
│   ├── sample-judgment-1.pdf
│   ├── sample-judgment-2.pdf
│   ├── sample-judgment-3.pdf
│   └── sample-judgment-4.pdf
├── output/                          # Generated JSON output (created on first run)
├── pyproject.toml                   # Project configuration & dependencies
├── README.md                        # This file
└── .gitignore                       # Git ignore rules
```

## Dependencies

All dependencies are declared in `pyproject.toml`:

- **pypdf** (>=3.17.0): Primary PDF text extraction
- **pymupdf** (>=1.23.0): PDF page rendering to images (for scanned PDFs)
- **pytesseract** (>=0.3.10): OCR wrapper for Tesseract (for scanned PDFs)
- **Pillow** (>=10.0.0): Image processing (required by pytesseract)
- **pydantic** (>=2.0.0): Data validation and JSON serialization
- **pytest** (dev, optional): Testing framework

> **Note**: OCR (pytesseract) requires the `tesseract-ocr` binary installed on your system. See Prerequisites above. Without it, scanned PDFs will produce empty output but the program will still run successfully.

Install all dependencies with:
```bash
uv sync
```

## Testing

Run the test suite to verify extraction logic:

```bash
uv run pytest tests/ -v
```

Tests verify:
- Bench extraction with various keyword formats
- Author judge extraction with different patterns
- Data model validation and JSON serialization
- Reproducibility (deterministic output)
- Empty PDF handling

## Reproducibility

The extraction system is **fully deterministic**:

- **Same input** → **Identical output** every time  
- No randomization  
- No external API calls  
- No machine learning or probabilistic elements  
- Fixed regex patterns and string operations  

To verify reproducibility:
```bash
# Run extraction twice
uv run extract-judgments
# output/sample-judgment-1.json created

uv run extract-judgments
# output/sample-judgment-1.json recreated identically
```

All output files are byte-for-byte identical when re-extracted.

## Limitations & Assumptions

### Limitations

1. **Scanned PDFs**: Text PDFs are processed with pypdf. Scanned/image-only PDFs fall back to OCR via pytesseract — requires `tesseract-ocr` to be installed on the system
2. **Language**: Assumes English-language documents with standard judicial formatting
3. **Formatting Assumptions**: Assumes bench is listed near document start (first 1000 characters)
4. **Role Attribution**: May not identify multiple co-authors if not explicitly stated
5. **Abbreviations**: May not expand abbreviated judge names (e.g., "H.A.G." vs "Henry Albert George")

### Reasonable Assumptions

1. **Document Structure**: Court judgments follow standard Sri Lankan judicial formatting:
   - Bench listed in header or after "Before:" keyword
   - "JUDGMENT" section exists and contains authorship information
   - Judge names followed by titles like "J." or "PC"

2. **Name Patterns**: Judge names follow common conventions:
   - Capitalized surnames and given names
   - Standard prefixes (Dr., Mr., Ms., etc.)
   - Long surnames may contain hyphens or particles (e.g., "de Silva")

3. **Bench Composition**: Assumes bench information is centralized in one location, not scattered throughout the document

4. **Judgment Attribution**: Assumes single primary author (though multiple judges may be listed as "Judgment of the Court")

## Development

### Adding New Pattern

To add support for a new document format:

1. Edit `src/judgment_extractor/extractor.py`
2. Add new pattern to appropriate method (`_extract_bench` or `_extract_author_judge`)
3. Add unit test to `tests/test_extractor.py`
4. Run: `uv run pytest tests/ -v`
5. Test on actual document: `uv run extract-judgments`

### Debugging

Add debug output to CLI:

```bash
python -c "
import sys
sys.path.insert(0, 'src')
from judgment_extractor.extractor import JudgmentExtractor
extractor = JudgmentExtractor()
result = extractor.extract_from_file('data/sample-judgment-1.pdf')
print(result.model_dump_json(indent=2))
"
```

## Environment Variables

None required. The system uses fixed paths:
- **Input**: `data/` directory (relative to working directory)
- **Output**: `output/` directory (created if not exists)

## Performance

- **Processing Speed**: ~100-500ms per PDF (depending on file size)
- **Memory Usage**: ~10-50MB for typical judgments
- **Scalability**: Efficiently processes 100+ documents

## License

This project is submitted as part of the Paralegal.lk internship assessment.

## Author

Developed as a submission for the Paralegal.lk Engineering Internship Program.

---

**Last Updated**: April 3, 2026  
**Python Version**: 3.11.9  
**Status**: Production Ready
