"""Core extraction logic for bench and author_judge from court decisions."""

import re
import sys
from pathlib import Path

import pypdf

from .models import JudgmentExtraction

try:
    import fitz  # pymupdf
    _PYMUPDF_AVAILABLE = True
except ImportError:
    _PYMUPDF_AVAILABLE = False

try:
    import shutil

    import pytesseract
    from PIL import Image

    # On Windows, Tesseract is often not on PATH even when installed.
    # Auto-detect the standard installation location.
    if not shutil.which("tesseract"):
        _win_tess = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if _win_tess.exists():
            pytesseract.pytesseract.tesseract_cmd = str(_win_tess)

    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


class JudgmentExtractor:
    """Deterministic extractor for bench and author_judge from PDF judgments."""

    def __init__(self):
        """Initialize the extractor."""
        pass

    def extract_from_file(self, pdf_path: str | Path) -> JudgmentExtraction:
        """
        Extract bench and author_judge from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            JudgmentExtraction object with extracted data
        """
        pdf_path = Path(pdf_path)
        text = self._extract_text_from_pdf(pdf_path)

        bench = self._extract_bench(text)
        author_judge = self._extract_author_judge(text, bench)

        return JudgmentExtraction(
            source_file=pdf_path.name,
            bench=bench,
            author_judge=author_judge,
        )

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract all text from PDF file.

        First attempts direct text extraction via pypdf.
        If the PDF contains no extractable text (e.g. scanned images),
        falls back to OCR using pymupdf + pytesseract when both are available.
        """
        text = self._extract_text_pypdf(pdf_path)
        if text.strip():
            return text

        # Fallback: OCR for scanned / image-only PDFs
        return self._extract_text_ocr(pdf_path)

    def _extract_text_pypdf(self, pdf_path: Path) -> str:
        """Extract text using pypdf (fast; works on text-based PDFs)."""
        pages = []
        try:
            with open(pdf_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        pages.append(extracted)
        except Exception as e:
            raise ValueError(f"Error reading PDF {pdf_path}: {e}")
        return "\n".join(pages)

    def _extract_text_ocr(self, pdf_path: Path) -> str:
        """Extract text via OCR (for scanned/image-only PDFs).

        Requires pymupdf and pytesseract with the Tesseract binary installed.
        See README for installation instructions.
        """
        pdf_path = Path(pdf_path)
        if not _PYMUPDF_AVAILABLE or not _OCR_AVAILABLE:
            print(
                f"  [WARN] {pdf_path.name} contains no extractable text. "
                "Install tesseract-ocr and ensure pymupdf/pytesseract are available "
                "to enable OCR for scanned PDFs.",
                file=sys.stderr,
            )
            return ""

        try:
            # Re-apply Windows path detection at call time in case tesseract_cmd
            # was not persisted from the module-level import (e.g. in some test runners).
            import shutil as _shutil
            if not _shutil.which("tesseract"):
                _win = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
                if _win.exists():
                    pytesseract.pytesseract.tesseract_cmd = str(_win)

            doc = fitz.open(str(pdf_path))
            pages = []
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text = pytesseract.image_to_string(img)
                if ocr_text.strip():
                    pages.append(ocr_text)
            doc.close()
            return "\n".join(pages)
        except pytesseract.TesseractNotFoundError:
            print(
                f"  [WARN] Tesseract not found. Install it to enable OCR for "
                f"{pdf_path.name}. See README for instructions.",
                file=sys.stderr,
            )
            return ""
        except Exception as e:
            print(f"  [WARN] OCR failed for {pdf_path.name}: {e}", file=sys.stderr)
            return ""

    def _clean_judge_name(self, name: str) -> str:
        """Strip all trailing title suffixes (J., C.J., CJ, PC) from a judge name."""
        name = name.strip()
        # Remove all trailing title tokens in any order/combination.
        # Handles: ", PC, CJ", ", PC,J", ", J.", ", C.J.", "J .", etc.
        title = r'(?:C\.J\.|CJ|J\.?|PC)'
        pattern = rf'(?:[,\s\.]+{title})+[,\s\.]*$'
        name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
        # Remove any residual trailing punctuation
        name = name.rstrip('., ').strip()
        return name

    def _extract_bench(self, text: str) -> list[str]:
        """
        Extract bench (coram) judges from text.

        Tries multiple strategies in order:
        1. Judge names in the first 1000 chars (compact header format)
        2. Judge names in the first 3000 chars (wider header window)
        3. Judge names on lines immediately BEFORE "Present:" / "Counsel:" keywords
        4. Judge names in sections AFTER "Before:", "CORAM:", "Present:" keywords
        """
        # Strategy 1: compact header (first 1000 characters)
        judges = self._extract_judges_from_lines(text[:1000])
        if judges:
            return judges

        # Strategy 2: wider header window (first 3000 characters)
        judges = self._extract_judges_from_lines(text[:3000])
        if judges:
            return judges

        # Strategy 3: judges listed on lines immediately before Present:/Counsel:
        judges = self._extract_judges_before_present(text)
        if judges:
            return judges

        # Strategy 4: "Before:"/"CORAM:"/"Present:" sections (after the keyword)
        bench_section = self._extract_bench_section(text)
        if bench_section:
            judges = self._extract_names_from_section(bench_section)

        return judges

    def _extract_judges_before_present(self, text: str) -> list[str]:
        """Extract judges listed on lines immediately before Present:/Counsel: keywords.

        Some documents (e.g. constitutional determinations) list the bench directly
        before the 'Present:' or 'Counsel:' section without an explicit label.
        """
        match = re.search(
            r'((?:[ \t]*[A-Z][^\n]{0,100}\n){1,10})\s*(?:Present|Councel?|Counsel)\s*:',
            text,
        )
        if not match:
            return []

        judges = []
        for line in match.group(1).split('\n'):
            line = line.strip()
            if not line or len(line) < 3:
                continue
            if not re.search(r'(?:Chief Justice|J\.|J,|CJ|PC|C\.J\.)', line, re.IGNORECASE):
                continue
            # Strip the "Chief Justice" title suffix and any trailing punctuation/colons
            name = re.sub(r',?\s*Chief Justice.*$', '', line, flags=re.IGNORECASE).strip()
            name = name.rstrip(' :')  # drop OCR artefacts like trailing " :"
            name = self._clean_judge_name(name)
            if name and len(name) > 2 and name not in judges:
                judges.append(name)
        return judges

    def _extract_bench_section(self, text: str) -> str:
        """Find and extract the bench section of the document."""
        patterns = [
            r"(?:Before|BEFORE)[:\s]+(.{0,1200}?)(?:APPLICATION|PETITION|Counsel|COUNSEL|Minutes)",
            r"(?:Coram|CORAM)[:\s]+(.{0,1200}?)(?:APPLICATION|PETITION|Counsel|COUNSEL)",
            r"(?:Present|PRESENT)[:\s]+(.{0,1200}?)(?:APPLICATION|PETITION|Counsel|COUNSEL)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1)

        return ""

    def _extract_judges_from_lines(self, text: str) -> list[str]:
        """Extract judge names from text by analysing line-by-line."""
        judges = []
        lines = text.split('\n')

        # Priority 1: multi-judge lines (e.g. "A. J., B. J. AND C. J.")
        for line in lines[:20]:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            if line.count('J.') >= 2 or (line.count(',') >= 2 and re.search(r'(?:J\.|CJ|PC)', line)):
                extracted = self._parse_judge_line(line)
                if extracted:
                    judges.extend(extracted)
                    return judges

        # Priority 2: single lines with judge title markers
        for line in lines[:50]:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            if any(skip in line.lower() for skip in [
                'counsel', 'copy', 'page', 'no', 'article',
                'fundamental', 'application', 'petition',
                'the court', 'v.', 'versus', 'and others',
                'supreme', 'law reports', 'reports',
            ]):
                continue
            # Handle "Name, Chief Justice" lines (no "J." marker)
            if re.search(r'Chief Justice', line, re.IGNORECASE):
                name = re.sub(r',?\s*Chief Justice.*$', '', line, flags=re.IGNORECASE).strip()
                name = self._clean_judge_name(name)
                if name and len(name) > 2 and name not in judges:
                    judges.append(name)
                continue
            if re.search(r'(?:J\.|CJ|PC|C\.J\.)', line, re.IGNORECASE):
                extracted = self._parse_judge_line(line)
                if extracted:
                    judges.extend(extracted)

        return judges

    def _parse_judge_line(self, line: str) -> list[str]:
        """Parse a single line that may contain one or more judge names."""
        line = line.strip()
        if not re.search(r'(?:J\.|CJ|PC|C\.J\.)', line, re.IGNORECASE):
            return []

        parts = re.split(r'\s+AND\s+', line, flags=re.IGNORECASE)
        all_judges = []

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Strip trailing title before splitting on embedded ". J." separators
            part_cleaned = re.sub(r'\s*(?:J\.|C\.J\.|CJ|PC)\s*\.?$', '', part).strip()

            # Split "H. A. G. DE SILVA. J.. AMERASINGHE" on ". J." patterns
            subparts = re.split(r'\.\s*J\.?\s*\.?\s*', part_cleaned, flags=re.IGNORECASE)

            for subpart in subparts:
                subpart = re.sub(r'\s+', ' ', subpart).strip().rstrip('.,')
                if subpart and len(subpart) > 2 and subpart not in all_judges:
                    all_judges.append(subpart)

        return all_judges

    def _extract_names_from_section(self, section: str) -> list[str]:
        """Extract and clean judge names from a bench section."""
        judges = []
        lines = section.split('\n')

        for line in lines:
            line = line.strip()
            if not line or len(line) <= 2:
                continue
            if line.lower() in ['and', 'counsel', 'application', 'etc']:
                continue
            # Skip pure numbers (e.g. page numbers leaking in)
            if re.match(r'^\d+$', line):
                continue
            # Must start with an uppercase letter or a known prefix
            if not re.match(r'^(?:Dr\.|Mr\.|Ms\.|Mrs\.)?[A-Z]', line):
                continue
            # Must contain actual letters
            if not re.search(r'[A-Za-z]{2,}', line):
                continue

            name = self._clean_judge_name(line)

            if (len(name) > 2
                    and not name.replace('.', '').replace(',', '').replace(' ', '').isdigit()
                    and name.lower() not in ['the', 'court', 'and']):
                if name not in judges:
                    judges.append(name)

        # Fallback: treat the whole short section as a single judge line
        if not judges and len(section) < 500:
            judges.extend(self._parse_judge_line(section))

        return judges

    def _extract_author_judge(self, text: str, bench: list[str] | None = None) -> list[str]:
        """
        Extract the judge(s) who authored/delivered the judgment.

        Strategies (in order):
        1. Explicit "delivered by" / "written by" phrases
        2. Judge name immediately after a standalone JUDGMENT heading
        3. Parenthetical attribution  – e.g. "(Amerasinghe, J.)"
        4. End-of-document signature blocks – e.g. "Name,\nChief Justice."
        5. Judge name on the line immediately before a bare "Chief Justice" near end
        6. Anonymous "Chief Justice" near end → resolve via C.J. designation
        """
        # Strategy 1: explicit attribution phrases.
        # Uses IGNORECASE for the keywords so "Delivered", "DELIVERED", and "delivered"
        # all match. The captured name is validated to start with a genuine uppercase
        # letter (author[0].isupper()) to reject false matches like "by the Authority".
        delivery_patterns = [
            r"(?:delivered|written)\s+by\s+([A-Z][A-Za-z\s\.\-,]+?)(?:\n|\.)",
            r"(?:judgment).*?(?:delivered|given)\s+by\s+([A-Z][A-Za-z\s\.\-,]+?)(?:\n|\.)",
        ]
        for pattern in delivery_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                author = re.sub(r'\s+', ' ', match.group(1)).strip()
                # Strict check: captured name must start with a real uppercase letter
                if len(author) > 2 and author[0].isupper():
                    return [author]

        # Strategy 2: judge name on the line right after a standalone JUDGMENT heading
        judgment_header = r"(?:^|\n)\s*JUDGMENT\s*(?:OF\s+)?(?:THE\s+)?(?:COURT)?\s*\n\s*([A-Z][A-Za-z\s\.\-,]+?)\s*,\s*(?:J\.|CJ|PC|C\.J\.)"
        match = re.search(judgment_header, text, re.IGNORECASE | re.MULTILINE)
        if match:
            author = match.group(1).strip()
            if len(author) > 2:
                return [author]

        # Strategy 3: parenthetical attribution – "(Amerasinghe, J.)"
        paren = r"\(([A-Z][A-Za-z\s\.\-]+?)\s*(?:,|\.)\s*(?:J\.|CJ|PC|C\.J\.)\)"
        match = re.search(paren, text)
        if match:
            author = match.group(1).strip()
            if len(author) > 2:
                return [author]

        # Strategy 4: end-of-document signature blocks.
        # Handles documents where all judges sign at the bottom, e.g.:
        #   "G. P. S. de Silva,\nChief Justice.\n\nA.R.B. Amarasinghe,\nJudge of the Supreme Court."
        sig_authors = self._extract_end_signatures(text)
        if sig_authors:
            return sig_authors

        # Strategy 5: judge name on the line immediately before "Chief Justice" near end
        end_text = text[-3000:]
        for cj_pos in re.finditer(r'\n[ \t]*(?:Chief Justice|CHIEF JUSTICE)', end_text):
            before = end_text[:cj_pos.start()]
            prev_lines = [ln.strip() for ln in before.split('\n') if ln.strip()]
            if prev_lines:
                candidate = prev_lines[-1]
                name = self._clean_judge_name(candidate)
                # Must look like a name: starts uppercase, reasonable length, no sentence words
                if (2 < len(name) < 60
                        and re.match(r'^[A-Z]', name)
                        and not re.search(
                            r'\b(?:the|and|of|in|for|that|this|court|petition|cost|limine|dismiss)\b',
                            name, re.IGNORECASE)):
                    return [name]
            break  # only check the first "Chief Justice" occurrence

        # Strategy 6: anonymous "Chief Justice" near end → find C.J. judge in document
        if re.search(r'\bChief Justice\b', end_text, re.IGNORECASE):
            # Match "NAME, C.J." (with dot) to avoid ambiguity with "CJ" abbreviations
            cj_match = re.search(
                r'([A-Z][A-Za-z\.]+(?:\s[A-Za-z\.]+)*?)\s*,\s*C\.J\.',
                text,
            )
            if cj_match:
                author = self._clean_judge_name(cj_match.group(1))
                if len(author) > 2:
                    return [author]

        return []

    def _extract_end_signatures(self, text: str) -> list[str]:
        """Extract judges who signed at the end of the document.

        Handles multi-signatory decisions where each judge's name appears on one line
        followed by their title on the next, e.g.:
            G. P. S. de Silva,
            Chief Justice.
        """
        end_text = text[-3000:]
        # Use [ \t] (not \s) to keep the name on a single line — avoids spanning
        # into preceding body text when the document has no blank line before the signature.
        pattern = re.compile(
            r'([A-Z][A-Za-z \t\.]+),\s*\n\s*'
            r'(?:Chief Justice|Judge of the Supreme Court|Justice of the Supreme Court)[.\n]',
        )
        authors = []
        for m in pattern.finditer(end_text):
            name = m.group(1).strip().rstrip(',').strip()
            if len(name) > 2 and name not in authors:
                authors.append(name)
        return authors
