"""Configuration constants for workbook population."""

from shared.config.settings import get_settings

DEFAULT_OUTPUT_DIR = str(get_settings().output_directory)
DEFAULT_OUTPUT_FILE_NAME = "company_model.xlsx"

TEMPLATE_WORKBOOK_MODE = "template"
USER_DECISION_WORKBOOK_MODE = "user_decision"
DYNAMIC_WORKBOOK_MODE = "dynamic"

HIGH_TEMPLATE_MATCH_THRESHOLD = 95.0
LOW_TEMPLATE_MATCH_THRESHOLD = 80.0

INCOME_STATEMENT_SHEET_NAME = "Income Statement"
BALANCE_SHEET_SHEET_NAME = "Balance Sheet"
CASH_FLOW_SHEET_NAME = "Cash Flow"
STATEMENT_OF_CHANGES_IN_EQUITY_SHEET_NAME = "Statement Of Changes In Equity"
DEBT_SCHEDULE_SHEET_NAME = "Debt Schedule"
SEGMENT_INFORMATION_SHEET_NAME = "Segment Information"
TAXATION_NOTE_SHEET_NAME = "Taxation Note"
INVENTORY_NOTE_SHEET_NAME = "Inventory Note"
PROPERTY_PLANT_EQUIPMENT_NOTE_SHEET_NAME = "Property Plant Equipment Note"
NOTES_SHEET_NAME = "Notes"
INSIGHTS_SHEET_NAME = "Insights"

STATEMENT_SHEET_BY_TABLE_TYPE = {
    "income_statement": INCOME_STATEMENT_SHEET_NAME,
    "profit_and_loss": INCOME_STATEMENT_SHEET_NAME,
    "statement_of_profit_or_loss": INCOME_STATEMENT_SHEET_NAME,
    "balance_sheet": BALANCE_SHEET_SHEET_NAME,
    "statement_of_financial_position": BALANCE_SHEET_SHEET_NAME,
    "cash_flow": CASH_FLOW_SHEET_NAME,
    "cash_flow_statement": CASH_FLOW_SHEET_NAME,
    "statement_of_cash_flows": CASH_FLOW_SHEET_NAME,
    "statement_of_changes_in_equity": STATEMENT_OF_CHANGES_IN_EQUITY_SHEET_NAME,
    "changes_in_equity": STATEMENT_OF_CHANGES_IN_EQUITY_SHEET_NAME,
    "debt_schedule": DEBT_SCHEDULE_SHEET_NAME,
    "borrowings_note": DEBT_SCHEDULE_SHEET_NAME,
    "loans_and_borrowings": DEBT_SCHEDULE_SHEET_NAME,
    "segment_information": SEGMENT_INFORMATION_SHEET_NAME,
    "segment_note": SEGMENT_INFORMATION_SHEET_NAME,
    "taxation_note": TAXATION_NOTE_SHEET_NAME,
    "tax_note": TAXATION_NOTE_SHEET_NAME,
    "income_tax_note": TAXATION_NOTE_SHEET_NAME,
    "inventory_note": INVENTORY_NOTE_SHEET_NAME,
    "inventories_note": INVENTORY_NOTE_SHEET_NAME,
    "property_plant_equipment_note": PROPERTY_PLANT_EQUIPMENT_NOTE_SHEET_NAME,
    "property_plant_and_equipment_note": PROPERTY_PLANT_EQUIPMENT_NOTE_SHEET_NAME,
    "ppe_note": PROPERTY_PLANT_EQUIPMENT_NOTE_SHEET_NAME,
    "notes": NOTES_SHEET_NAME,
    "financial_statement_notes": NOTES_SHEET_NAME,
}

CRITICAL_METRICS = {
    "revenue",
    "gross_profit",
    "ebitda",
    "profit_after_tax",
    "pat",
    "total_assets",
    "total_liabilities",
    "total_equity",
}

KNOWN_TEMPLATE_METRICS = CRITICAL_METRICS | {
    "cost_of_sales",
    "operating_profit",
    "finance_cost",
    "tax_expense",
    "cash",
    "inventory",
    "trade_receivables",
    "trade_payables",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "free_cash_flow",
}
