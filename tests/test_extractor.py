"""Tests for judgment extraction."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from judgment_extractor.extractor import JudgmentExtractor
from judgment_extractor.models import JudgmentExtraction

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


# ---------------------------------------------------------------------------
# Unit tests: bench extraction
# ---------------------------------------------------------------------------

class TestBenchExtraction:

    def test_multi_judge_header_line(self):
        """Bench extracted from a single-line header with AND separators."""
        extractor = JudgmentExtractor()
        text = "H. A. G. DE SILVA. J., AMERASINGHE. J. AND DHEERARATNE, J.\nSome body text."
        bench = extractor._extract_bench(text)
        assert len(bench) >= 2

    def test_bench_after_coram_keyword(self):
        """Bench extracted when listed after CORAM: keyword."""
        extractor = JudgmentExtractor()
        text = (
            "CORAM:\nJohn Smith, J.\nMary Johnson, J.\n\nCOUNSEL:\nSome counsel."
        )
        bench = extractor._extract_bench(text)
        assert len(bench) >= 1

    def test_bench_before_present_keyword(self):
        """Bench extracted from lines listed immediately before Present:."""
        extractor = JudgmentExtractor()
        text = (
            "Respondent\n\n"
            "G. P. S. de Silva, Chief Justice\n"
            "Amerasinghe, J.\n"
            "Ramanahan, J.\n\n"
            "Present:\n\nCounsel:\nSome counsel."
        )
        bench = extractor._extract_bench(text)
        assert "G. P. S. de Silva" in bench
        assert "Amerasinghe" in bench
        assert "Ramanahan" in bench

    def test_bench_returns_list(self):
        extractor = JudgmentExtractor()
        assert isinstance(extractor._extract_bench("no judges here"), list)


# ---------------------------------------------------------------------------
# Unit tests: author extraction
# ---------------------------------------------------------------------------

class TestAuthorExtraction:

    def test_delivered_by_phrase(self):
        extractor = JudgmentExtractor()
        text = "This judgment is Delivered by Justice Jane Doe.\nThe court orders..."
        author = extractor._extract_author_judge(text)
        assert len(author) > 0
        assert any("Jane Doe" in j for j in author)

    def test_delivered_by_does_not_match_lowercase(self):
        """'delivered by the Authority' (lowercase) must NOT be captured as an author."""
        extractor = JudgmentExtractor()
        text = (
            "functions delivered by the Authority shall be subject to...\n"
            "G. P. S. de Silva,\nChief Justice.\n"
        )
        author = extractor._extract_author_judge(text)
        assert "the Authority" not in author
        assert "the authority" not in [a.lower() for a in author]

    def test_judgment_header_attribution(self):
        extractor = JudgmentExtractor()
        text = "\nJUDGMENT\nAmerasinghe, J.\nThe facts are..."
        author = extractor._extract_author_judge(text)
        assert len(author) > 0

    def test_parenthetical_attribution(self):
        extractor = JudgmentExtractor()
        text = "As held (Amerasinghe, J.) the court decided..."
        author = extractor._extract_author_judge(text)
        assert len(author) > 0
        assert "Amerasinghe" in author[0]

    def test_end_signature_blocks(self):
        """All signatories extracted from end-of-document signature blocks."""
        extractor = JudgmentExtractor()
        text = (
            "We determine that the Bill is unconstitutional.\n\n"
            "G. P. S. de Silva,\nChief Justice.\n\n"
            "A.R.B. Amarasinghe,\nJudge of the Supreme Court.\n\n"
            "P. Ramanathan,\nJudge of the Supreme Court.\n"
        )
        author = extractor._extract_author_judge(text)
        assert "G. P. S. de Silva" in author
        assert "A.R.B. Amarasinghe" in author
        assert "P. Ramanathan" in author

    def test_author_returns_list(self):
        extractor = JudgmentExtractor()
        assert isinstance(extractor._extract_author_judge("no judges"), list)


# ---------------------------------------------------------------------------
# Unit tests: data model
# ---------------------------------------------------------------------------

class TestDataModel:

    def test_model_structure(self):
        extraction = JudgmentExtraction(
            source_file="test.pdf",
            bench=["Judge A", "Judge B"],
            author_judge=["Judge A"],
        )
        assert extraction.source_file == "test.pdf"
        assert len(extraction.bench) == 2
        assert len(extraction.author_judge) == 1

    def test_json_schema(self):
        extraction = JudgmentExtraction(
            source_file="sample-judgment-1.pdf",
            bench=["Justice A", "Justice B"],
            author_judge=["Justice A"],
        )
        data = json.loads(extraction.model_dump_json())
        assert set(data.keys()) == {"source_file", "bench", "author_judge"}
        assert data["source_file"] == "sample-judgment-1.pdf"
        assert isinstance(data["bench"], list)
        assert isinstance(data["author_judge"], list)

    def test_empty_pdf_handling(self):
        """Extractor returns empty lists for a PDF with no extractable text."""
        extractor = JudgmentExtractor()
        with patch("builtins.open", create=True):
            with patch("judgment_extractor.extractor.pypdf.PdfReader") as mock_reader:
                mock_page = MagicMock()
                mock_page.extract_text.return_value = ""
                mock_reader.return_value.pages = [mock_page]

                # Patch OCR to also return empty so test is self-contained
                with patch.object(extractor, "_extract_text_ocr", return_value=""):
                    result = extractor.extract_from_file("dummy.pdf")

        assert result.bench == []
        assert result.author_judge == []


# ---------------------------------------------------------------------------
# Integration: reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:

    def test_deterministic_output(self):
        """Identical input always produces identical output."""
        extractor = JudgmentExtractor()
        sample_text = (
            "CORAM:\nJustice Ahmed Hassan, J.\nJustice Lakshmi Srinivasan, J.\n\n"
            "JUDGMENT\n\nThis judgment is Delivered by Justice Ahmed Hassan.\n"
        )
        bench1 = extractor._extract_bench(sample_text)
        author1 = extractor._extract_author_judge(sample_text)
        bench2 = extractor._extract_bench(sample_text)
        author2 = extractor._extract_author_judge(sample_text)
        assert bench1 == bench2
        assert author1 == author2


# ---------------------------------------------------------------------------
# End-to-end: all 4 sample PDFs
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not DATA_DIR.exists(),
    reason="data/ directory not present",
)
class TestEndToEnd:
    """Run full extraction on every sample PDF and verify output structure."""

    @pytest.fixture(scope="class")
    def extractor(self):
        return JudgmentExtractor()

    @pytest.fixture(scope="class")
    def results(self, extractor):
        return {
            i: extractor.extract_from_file(DATA_DIR / f"sample-judgment-{i}.pdf")
            for i in range(1, 5)
        }

    def test_all_files_have_source_file(self, results):
        for i, r in results.items():
            assert r.source_file == f"sample-judgment-{i}.pdf"

    def test_all_files_have_bench(self, results):
        for i, r in results.items():
            assert isinstance(r.bench, list), f"file {i}: bench is not a list"
            assert len(r.bench) > 0, f"file {i}: bench is empty"

    def test_all_files_have_author(self, results):
        for i, r in results.items():
            assert isinstance(r.author_judge, list), f"file {i}: author_judge is not a list"
            assert len(r.author_judge) > 0, f"file {i}: author_judge is empty"

    def test_all_bench_entries_are_non_empty_strings(self, results):
        for i, r in results.items():
            for name in r.bench:
                assert isinstance(name, str) and len(name) > 1, (
                    f"file {i}: invalid bench entry {name!r}"
                )

    def test_all_author_entries_are_non_empty_strings(self, results):
        for i, r in results.items():
            for name in r.author_judge:
                assert isinstance(name, str) and len(name) > 1, (
                    f"file {i}: invalid author entry {name!r}"
                )

    # --- Strict known-value assertions ---

    def test_file1_bench_contains_three_judges(self, results):
        assert len(results[1].bench) == 3

    def test_file1_bench_de_silva(self, results):
        assert any("DE SILVA" in n.upper() for n in results[1].bench)

    def test_file1_bench_amerasinghe(self, results):
        assert any("AMERASINGHE" in n.upper() for n in results[1].bench)

    def test_file1_bench_dheeraratne(self, results):
        assert any("DHEERARATNE" in n.upper() for n in results[1].bench)

    def test_file1_author_amerasinghe(self, results):
        assert any("AMERASINGHE" in n.upper() for n in results[1].author_judge)

    def test_file3_bench_de_silva(self, results):
        assert any("DE SILVA" in n.upper() for n in results[3].bench)

    def test_file3_bench_amerasinghe(self, results):
        assert any("AMERASINGHE" in n.upper() for n in results[3].bench)

    def test_file3_bench_ramanathan(self, results):
        assert any("RAMANAH" in n.upper() for n in results[3].bench)

    def test_file3_author_de_silva(self, results):
        assert any("DE SILVA" in n.upper() for n in results[3].author_judge)

    def test_file4_bench_jayasuriya(self, results):
        assert any("JAYASURIYA" in n.upper() for n in results[4].bench)

    def test_file4_author_jayasuriya(self, results):
        assert any("JAYASURIYA" in n.upper() for n in results[4].author_judge)


# ---------------------------------------------------------------------------
# End-to-end: output JSON files match expected schema
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not OUTPUT_DIR.exists(),
    reason="output/ directory not present — run extract-judgments first",
)
class TestOutputFiles:

    @pytest.mark.parametrize("i", range(1, 5))
    def test_output_file_exists(self, i):
        assert (OUTPUT_DIR / f"sample-judgment-{i}.json").exists()

    @pytest.mark.parametrize("i", range(1, 5))
    def test_output_file_schema(self, i):
        data = json.loads((OUTPUT_DIR / f"sample-judgment-{i}.json").read_text())
        assert "source_file" in data
        assert "bench" in data
        assert "author_judge" in data
        assert data["source_file"] == f"sample-judgment-{i}.pdf"
        assert isinstance(data["bench"], list)
        assert isinstance(data["author_judge"], list)
