"""Prompt builder for financial table classification."""


class TableClassificationPromptBuilder:
    """Build prompts for page-level financial table classification."""

    _SYSTEM_PROMPT = (
        "You classify financial table types in annual report page text. "
        "Return only structured JSON matching the provided schema. "
        "Use concise snake_case table type labels. The table type set is open; "
        "do not force labels into a fixed enum."
    )

    def build_messages(
        self,
        *,
        page_number: int,
        tables_detected: int,
        page_text: str,
    ) -> list[dict[str, str]]:
        """Build OpenAI messages for classifying a detected PDF page."""

        user_prompt = (
            "Given the page text from an annual report, identify all financial "
            "table types present on the page.\n\n"
            f"Page number: {page_number}\n"
            f"Tables detected on page: {tables_detected}\n\n"
            "Return ONLY JSON in this shape:\n"
            '{"table_types":["balance_sheet","debt_schedule"]}\n\n'
            "Rules:\n"
            "- Include every financial table type visible in the page text.\n"
            "- Use snake_case labels such as balance_sheet, income_statement, "
            "cash_flow_statement, notes, debt_schedule, taxation_note.\n"
            "- Do not extract rows, values, facts, or recommendations.\n"
            "- If the table type cannot be determined, return an empty list.\n\n"
            "Page text:\n"
            f"{page_text}"
        )

        return [
            {"role": "system", "content": self._SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
