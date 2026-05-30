# Integration Tests

Run OCR integration tests with:

```bash
pytest tests/integration -m integration -s
```

The OCR E2E test requires:

* `tests/fixtures/sample_annual_report.pdf`
* PyMuPDF
* Torch
* Transformers
* Camelot
* pdfplumber
* sentence-transformers
* OpenPyXL

OpenAI network calls are mocked. The real pipeline layers still execute for
table detection, table extraction, normalization, validation, consolidation,
and workbook population.

Optional environment variables:

```text
OCR_E2E_REPORT_YEAR=2024
OCR_E2E_COMPANY_NAME=Integration Test Company
OCR_E2E_MAX_SECONDS=300
```
