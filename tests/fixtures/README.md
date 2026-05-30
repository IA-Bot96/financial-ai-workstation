# OCR Integration Fixtures

Place a real annual report PDF at:

```text
tests/fixtures/sample_annual_report.pdf
```

The end-to-end OCR integration test intentionally does not fabricate OCR
outputs. The fixture should contain at least one financial statement table so
the real detection and extraction layers can produce data.

Recommended fixture PDF characteristics:

* Public annual report PDF with selectable or OCR-readable text.
* Contains income statement, balance sheet, and cash flow tables.
* Contains at least one narrative business review section.
* Small enough for CI execution, ideally under 50 pages or a curated excerpt.
* Licensed for internal test use.

Good candidates are public annual reports from listed companies where annual
reports are distributed as standard text PDFs rather than scanned image-only
documents.
