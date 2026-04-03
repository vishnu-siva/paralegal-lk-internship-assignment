"""Data models for judgment extraction."""

from pydantic import BaseModel, ConfigDict, Field


class JudgmentExtraction(BaseModel):
    """Extracted judgment data."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "source_file": "sample-judgment-1.pdf",
            "bench": ["Judge Name 1", "Judge Name 2"],
            "author_judge": ["Judge Name 1"],
        }
    })

    source_file: str = Field(..., description="Name of the PDF file")
    bench: list[str] = Field(default_factory=list, description="List of judges on the bench")
    author_judge: list[str] = Field(
        default_factory=list, description="Judge(s) who authored/delivered the judgment"
    )
