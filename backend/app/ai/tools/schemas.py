"""Bounded Pydantic input contracts for model-facing LangChain tools."""

from pydantic import BaseModel, ConfigDict, Field


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchSourcePassagesInput(ToolInput):
    query: str = Field(
        min_length=1,
        max_length=4_000,
        description="A focused evidence query; never include tenant or project identifiers.",
    )


class ReadSourcePassageInput(ToolInput):
    source_version_id: str = Field(min_length=1, max_length=200)
    passage_id: str = Field(min_length=1, max_length=200)


class CitationOffsetsInput(ToolInput):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class CitationReferenceInput(ToolInput):
    passage_id: str = Field(min_length=1, max_length=200)
    source_version_id: str = Field(min_length=1, max_length=200)
    block_id: str = Field(min_length=1, max_length=200)
    page: int | None = Field(default=None, ge=1)
    section_path: str | None = Field(default=None, max_length=1_000)
    offsets: CitationOffsetsInput | None = None


class ProposeTextPatchInput(ToolInput):
    summary: str = Field(min_length=1, max_length=2_000)
    text: str = Field(min_length=1, max_length=20_000)
    citations: list[CitationReferenceInput] | None = Field(default=None, max_length=20)
