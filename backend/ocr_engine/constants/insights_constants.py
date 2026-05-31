"""Configuration constants for OCR narrative insights extraction."""

INSIGHTS_CHUNK_MAX_CHARACTERS = 2800
INSIGHTS_CHUNK_OVERLAP_CHARACTERS = 250
INSIGHTS_MAX_RANKED_CHUNKS = None
INSIGHTS_CHUNKS_PER_LLM_CALL = 8
INSIGHTS_RETRIEVAL_STRATEGY = "section_balanced_score_all_relevant_chunks"

INSIGHTS_RELEVANT_SECTIONS = (
    "Chairman Review",
    "CEO Review",
    "Directors Report",
    "Management Discussion & Analysis",
    "Business Review",
    "Risks",
    "Opportunities",
    "Outlook",
    "Financial Review",
    "Sustainability",
    "ESG",
)

INSIGHTS_IGNORED_SECTION_KEYWORDS = (
    "auditor",
    "independent auditor",
    "financial statements",
    "notes to the financial statements",
    "corporate information",
    "notice of annual general meeting",
    "pattern of shareholding",
    "proxy form",
)

INSIGHTS_FINANCIAL_KEYWORDS = (
    "expansion",
    "capacity",
    "debt",
    "borrowings",
    "exports",
    "export",
    "cost",
    "margin",
    "working capital",
    "inventory",
    "receivables",
    "payables",
    "regulatory",
    "inflation",
    "exchange rate",
    "interest rate",
    "raw material",
    "energy",
    "coal",
    "oil",
    "freight",
    "risk",
    "opportunity",
    "outlook",
    "esg",
    "sustainability",
)
