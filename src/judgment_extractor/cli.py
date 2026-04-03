"""Command-line interface for judgment extraction."""

import json
import sys
from pathlib import Path

from .extractor import JudgmentExtractor


def main():
    """Main CLI entry point."""
    # Define input and output directories
    data_dir = Path("data")
    output_dir = Path("output")

    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)

    # Initialize extractor
    extractor = JudgmentExtractor()

    # Process all PDF files in data directory
    pdf_files = sorted(data_dir.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found in data/ directory.", file=sys.stderr)
        return 1

    for pdf_file in pdf_files:
        try:
            print(f"Processing {pdf_file.name}...")

            # Extract judgment data
            extraction = extractor.extract_from_file(pdf_file)

            # Generate output filename
            output_file = output_dir / f"{pdf_file.stem}.json"

            # Write JSON output
            with open(output_file, "w") as f:
                json.dump(extraction.model_dump(), f, indent=2)

            print(f"  [OK] Written to {output_file}")

        except Exception as e:
            print(f"  [ERR] Error processing {pdf_file.name}: {e}", file=sys.stderr)
            return 1

    print(f"\nSuccessfully processed {len(pdf_files)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
