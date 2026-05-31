# OCR Platform Installation

## Local Setup

1. Install Python 3.12.
2. Create a virtual environment.
3. Install production dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Copy environment defaults and configure secrets:

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`.

## Windows Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Camelot 1.x uses `pypdfium2` as the default PDF rendering backend, so
Ghostscript is not required for the default extraction path. Install Ghostscript
only if you explicitly configure Camelot to use its optional Ghostscript backend.

## Linux Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Install system OCR/PDF dependencies:

```bash
sudo apt-get update
sudo apt-get install -y libgl1 libglib2.0-0
```

## Development Setup

```bash
python -m pip install -r requirements-dev.txt
```

## Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=backend
```

Run the OCR end-to-end integration test after placing a real annual report at
`tests/fixtures/sample_annual_report.pdf`:

```bash
pytest tests/integration -m integration -s
```

## Running The Pipeline

Set `PYTHONPATH` so the backend packages are importable:

```bash
export PYTHONPATH=backend
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "backend"
```

Run the pipeline from a serialized `CompanyContext` JSON file:

```bash
python backend/run_pipeline.py --context-json data/context.json --output-json output/context_result.json
```

The pipeline validates required startup configuration before initializing heavy
OCR and AI dependencies.

## Docker

```bash
cp .env.example .env
docker compose build
docker compose run --rm ocr-platform python backend/run_pipeline.py --context-json /app/data/context.json --output-json /app/output/context_result.json
```

Mount input files under `./data` and generated workbooks under `./output`.
