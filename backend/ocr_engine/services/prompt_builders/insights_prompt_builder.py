"""Prompt builder for business insights extraction."""

from ocr_engine.services.chunk_builder import NarrativeChunk


class InsightsPromptBuilder:
    """Build structured-output prompts for annual-report business insights."""

    def build_messages(
        self,
        chunks: list[NarrativeChunk],
        metric_context: tuple[str, ...],
        report_year: int,
    ) -> list[dict[str, str]]:
        """Build OpenAI messages from ranked chunks and financial context."""

        financial_context = ", ".join(metric_context[:40]) or "No normalized metrics available."
        chunk_text = "\n\n".join(
            (
                f"Chunk {index}\n"
                f"source_section: {chunk.source_section}\n"
                f"page_number: {chunk.page_number}\n"
                f"source_report_year: {report_year}\n"
                f"default_value_year: {chunk.year or report_year}\n"
                f"text:\n{chunk.text}"
            )
            for index, chunk in enumerate(chunks, start=1)
        )

        return [
            {
                "role": "system",
                "content": (
                    "You extract concise, actionable business insights from "
                    "annual-report narrative text. Return JSON only. Do not "
                    "summarize the whole report. Every insight must be directly "
                    "supported by the provided source chunk."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract business insights from the ranked annual-report "
                    "chunks below. Focus on expansion plans, debt changes, "
                    "capacity expansion, exports, cost pressures, working "
                    "capital, regulatory impacts, margin drivers, risks, "
                    "opportunities, and outlook.\n\n"
                    "Normalized financial context:\n"
                    f"{financial_context}\n\n"
                    "Return only JSON matching this shape:\n"
                    "{\n"
                    '  "insights": [\n'
                    "    {\n"
                    '      "area": "...",\n'
                    '      "takeaway": "...",\n'
                    '      "source_section": "...",\n'
                    f'      "source_report_year": {report_year},\n'
                    f'      "value_year": {report_year},\n'
                    '      "page_number": 1,\n'
                    '      "confidence": 0.0\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "Ranked source chunks:\n"
                    f"{chunk_text}"
                ),
            },
        ]
