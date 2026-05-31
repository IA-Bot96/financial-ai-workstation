# Dependency Compatibility Report

Target runtime: Python 3.12 on Windows x64, Linux containers, and CI.

The dependency set is intentionally biased toward installability and operational
stability. Optional extras that add native transitive dependencies are avoided
unless the platform directly needs them.

## Compatibility Summary

| Package | Required | Purpose | Python 3.12 Notes |
| --- | --- | --- | --- |
| `pymupdf` | Yes | Opens PDFs, extracts page text, renders pages as images through `fitz`. | Modern wheels support Python 3.12. |
| `pillow` | Yes | Converts rendered PDF page bytes into image objects for table detection. | Pinned to `>=10.4` to match Camelot 1.x and Python 3.12 wheel availability. |
| `torch` | Yes | Runtime for Microsoft Table Transformer inference. | CPU wheels are available for Windows x64 on Python 3.12; install size is large. |
| `transformers` | Yes | Loads `microsoft/table-transformer-detection` processor and model. | Compatible with current PyTorch and Python 3.12 ranges. |
| `camelot-py` | Yes | Primary PDF table extraction backend. | Uses Camelot 1.x with the default pdfium backend. No `cv` extra is used. |
| `pdfplumber` | Yes | Fallback table extraction backend when Camelot returns no tables. | Pure Python plus PDF dependencies with Python 3.12 support. |
| `pandas` | Yes | Internal table and validation data handling. | Pinned to `>=2.2.2` for mature Python 3.12 wheels. |
| `numpy` | Yes | Embedding math and fallback cosine similarity. | Kept below NumPy 2 to reduce native ABI risk on Windows. |
| `sentence-transformers` | Yes | Local embedding model for shared metric normalization. | Requires PyTorch and pulls scientific transitive dependencies. |
| `openai` | Yes | Financial table classification and insights extraction. | SDK supports Python 3.12. |
| `openpyxl` | Yes | Reads templates and writes generated Excel workbooks. | Pure Python and stable on Python 3.12. |
| `pydantic` | Yes | Production data contracts for all engine models. | Pydantic v2 supports Python 3.12. |
| `pydantic-settings` | Yes | Environment-based runtime configuration. | Required by `shared.config.settings`. |
| `fastapi` | Yes | API surface for OCR orchestration. | Compatible with Pydantic v2. |
| `uvicorn` | Yes | ASGI server for FastAPI. | Base package only; `standard` extra is intentionally omitted. |

## Resolver Verification

Verified with:

```powershell
python -m pip install --dry-run --index-url https://pypi.org/simple -r requirements.txt
```

Result: dependency resolution completed successfully on Python 3.12 for Windows.

Notable resolved packages included:

| Package | Resolved Version |
| --- | --- |
| `camelot-py` | `1.0.9` |
| `numpy` | `1.26.4` |
| `pandas` | `2.3.3` |
| `pymupdf` | `1.27.2.3` |
| `torch` | `2.12.0` |
| `transformers` | `4.57.6` |
| `sentence-transformers` | `5.5.1` |
| `openai` | `1.109.1` |
| `openpyxl` | already satisfied as `3.1.5` in the verification runtime |

`scikit-learn` resolved transitively through `sentence-transformers`; it is not
listed directly because application code can run cosine similarity with NumPy
when `scikit-learn` is absent.

## Optional Dependencies

| Dependency | Status | Reason |
| --- | --- | --- |
| `scikit-learn` | Optional transitive dependency only | `SimilaritySearchService` can use it when present, but falls back to NumPy. It is not a direct dependency to reduce Windows native install risk. |
| Camelot `ghostscript` extra | Optional, omitted | Camelot 1.x defaults to pdfium. Ghostscript is only needed if a legacy Ghostscript backend is explicitly configured. |
| Camelot `cv` extra | Omitted | The project does not require an extra named `cv`; depending on Camelot 1.x directly avoids stale or broken extra resolution. |
| `uvicorn[standard]` | Omitted | The standard extra pulls optional performance packages that are not required for a stable baseline install. |
| CUDA packages | Omitted | Table detection can run on CPU. GPU-specific PyTorch packages should be installed separately only for dedicated inference hosts. |

## Dependency Selection Decisions

### Camelot

Use:

```text
camelot-py>=1.0.9,<2
```

Do not use:

```text
camelot-py[cv]
```

Camelot 1.x uses pdfium as the default rendering backend. This removes the old
baseline requirement for a system Ghostscript installation and makes a clean
Windows setup much easier. If a future deployment deliberately chooses
Ghostscript, install the backend explicitly for that environment rather than
making it part of the core platform dependency set.

### NumPy

Use:

```text
numpy>=1.26.4,<2
```

The platform does not need NumPy 2 features. Staying on the mature 1.26 line
reduces ABI churn across pandas, sentence-transformers, and native wheels on
Windows.

### Uvicorn

Use:

```text
uvicorn>=0.30,<1
```

The base package is sufficient to run FastAPI. The `standard` extra adds
optional event-loop and parser dependencies that increase install variance on
Windows without being required for correctness.

### Scikit-Learn

Do not list `scikit-learn` directly. It may still be installed transitively by
`sentence-transformers`, but the application code does not require it because
cosine similarity falls back to a NumPy implementation.

## Clean Windows Install Guidance

1. Use Python 3.12 x64.
2. Create a fresh virtual environment.
3. Upgrade pip before installing dependencies.
4. Install `requirements.txt`.
5. Do not install Camelot extras or `uvicorn[standard]` unless a deployment
   explicitly needs them.
6. Expect `torch` and `sentence-transformers` to dominate install size and time.

Recommended commands:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Production Notes

The current dependency files are suitable as broad production constraints. For
release builds, generate a locked artifact with hashes after validating on the
target Windows and Linux runners.
