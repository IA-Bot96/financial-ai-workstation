"""Configuration constants for OCR narrative insights extraction."""

INSIGHTS_CHUNK_MAX_CHARACTERS = 2800
INSIGHTS_CHUNK_OVERLAP_CHARACTERS = 250
INSIGHTS_MAX_RANKED_CHUNKS = None
INSIGHTS_CHUNKS_PER_LLM_CALL = 8
INSIGHTS_RETRIEVAL_STRATEGY = "section_balanced_score_all_relevant_chunks"
INSIGHT_CONFIDENCE_REJECT_THRESHOLD = 0.50
INSIGHT_CONFIDENCE_REVIEW_THRESHOLD = 0.70

INSIGHTS_RELEVANT_SECTIONS = (
    "Chairman Review",
    "CEO Review",
    "Directors Report",
    "Management Discussion & Analysis",
    "Business Review",
    "Risks",
    "Opportunities",
    "Outlook",
    "Strategy",
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

GENERIC_INSIGHT_FILTER_PATTERNS = (
    "adequate internal controls",
    "internal financial controls",
    "ifrs have been followed",
    "ifrs, as applicable in pakistan, have been followed",
    "going concern",
    "no significant doubts",
    "corporate governance",
    "code of conduct",
    "zero tolerance for non-compliance",
    "zero-tolerance policy for non-compliance",
    "no apparent risk or uncertainty",
)

QUANTITATIVE_EVIDENCE_TERMS = (
    "%",
    "rs",
    "pkr",
    "usd",
    "million",
    "billion",
    "kwh",
    "co2",
    "ton",
    "tons",
    "tractor",
    "tractors",
    "units",
    "export",
    "exports",
    "revenue",
    "sales",
    "profit",
    "margin",
    "eps",
    "debt",
    "borrowings",
    "finance cost",
    "working capital",
    "cash",
    "capacity",
    "production",
)
