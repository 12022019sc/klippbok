# External Integrations

**Analysis Date:** 2026-02-27

## APIs & External Services

**AI Captioning Providers:**
- Google Gemini API - VLM for video and image captioning
  - SDK/Client: `google-genai` (1.0+)
  - Auth: `GEMINI_API_KEY` environment variable
  - Implementation: `klippbok/caption/gemini.py`
  - **Flow:** Upload video → Poll for ACTIVE state → Generate caption → Delete file
  - Models: `gemini-2.5-flash` (default, configurable in `CaptionConfig`)
  - File handling: Supports MP4, MOV, MKV, AVI, WebM with MIME type auto-detection

- Replicate API - Cloud VLM inference via HTTP
  - SDK/Client: raw HTTP via `requests` (2.20+)
  - Auth: `REPLICATE_API_TOKEN` environment variable
  - Implementation: `klippbok/caption/replicate.py`
  - **Flow:** Encode file as base64 data URI → POST to predictions API → Poll/wait for result
  - Models: `google/gemini-2.5-flash` (default, configurable)
  - Endpoint: `https://api.replicate.com/v1/models/{model}/predictions`
  - Features: Schema auto-detection for model input fields (supports "videos", "images", "media")

- OpenAI-compatible Endpoints - Local VLMs via OpenAI chat completions protocol
  - SDK/Client: raw HTTP via `requests` (no `openai` package dependency)
  - Auth: Optional Bearer token
  - Implementation: `klippbok/caption/openai_compat.py`
  - **Supported Servers:**
    - Ollama (default: `http://localhost:11434/v1`)
    - vLLM
    - LM Studio
    - Any OpenAI-format endpoint
  - **Video Handling:** Extracts keyframes via ffmpeg → sends as multi-image prompt (images only accepted)
  - Models: `llama3.2-vision` (default, configurable via `openai_model` in `CaptionConfig`)
  - Configurable frame rate: `caption_fps` parameter controls extraction rate for temporal understanding

**HuggingFace Model Hub:**
- CLIP Model - Semantic embedding for scene triage/matching
  - Model: `openai/clip-vit-base-patch32` (default in `klippbok/triage/`)
  - Transport: Downloaded via HuggingFace Transformers library
  - Usage: Reference image embedding → video frame matching by cosine similarity
  - Implementation: `klippbok/triage/embeddings.py`

## Data Storage

**Databases:**
- None - Klippbok is a stateless data processing tool, not a database application

**File Storage:**
- Local filesystem only
  - Dataset sources: User-provided directories of video clips
  - Outputs: Manifests, captions (`.txt` files), audit reports
  - Temporary files: Frame extraction via tempfile during video processing
  - No cloud storage integration (S3, GCS, Azure Blob)

**Caching:**
- None at application layer
- Dependency caching (pip packages) handled by environment

## Authentication & Identity

**Auth Provider:**
- None - Klippbok is CLI-based, not a multi-user service
- API authentication: Environment variables for each provider
  - Gemini: `GEMINI_API_KEY`
  - Replicate: `REPLICATE_API_TOKEN`
  - OpenAI-compatible: Optional Bearer token

**Implementation:**
- Environment variables loaded by caption backends at initialization
- Fallback to runtime error with installation instructions if missing
- Example from `klippbok/caption/gemini.py`:
  ```python
  self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
  if not self.api_key:
      raise ValueError("Gemini API key not found...")
  ```

## Monitoring & Observability

**Error Tracking:**
- None - No external error tracking service integrated

**Logging:**
- Console output only (stdout/stderr)
- Print statements for progress and errors (e.g., retry messages in captioning)
- No structured logging framework
- Example from `klippbok/caption/gemini.py`:
  ```python
  print(f"    Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{self.max_retries})")
  ```

**Structured Data Output:**
- YAML: Config files (`klippbok_data.yaml`)
- JSONL: Caption audit output (optional)
- Plain text: Captions (`.txt` files alongside videos)

## CI/CD & Deployment

**Hosting:**
- None - Klippbok is a CLI tool, not a hosted service
- Designed for local machine or HPC cluster execution

**CI Pipeline:**
- GitHub Actions (workflow files in `.github/` directory)
- Testing: pytest via CI

**Deployment Model:**
- pip package installation (`pip install klippbok` or from source)
- Optional dependency groups allow selective feature installation

## Environment Configuration

**Required env vars:**
- None are strictly required; all are optional and checked at runtime
- Provider-specific keys loaded on-demand:
  - `GEMINI_API_KEY` - Required only when `provider="gemini"` in caption config
  - `REPLICATE_API_TOKEN` - Required only when `provider="replicate"`

**Optional env vars (convenience):**
- None — all configuration via YAML config file and env vars for secrets only

**Secrets location:**
- `.env` file (gitignored via `.gitignore`)
- Template: `.env.example` (checked in with placeholders)
- Loading: Manual by users (not auto-loaded; explicitly read by backends)

## Webhooks & Callbacks

**Incoming:**
- None - Klippbok is a one-way batch processing tool

**Outgoing:**
- None - No webhook callbacks to external systems

## Rate Limiting & Quotas

**Gemini API:**
- Free tier: ~20 requests/minute
- Handled in `klippbok/caption/gemini.py` via exponential backoff
- Default delay between requests: `between_request_delay = 10.0` seconds (configurable in `CaptionConfig`)
- Retry logic: `max_retries = 5` with 45s, 90s, 135s waits on 429/503 errors

**Replicate API:**
- Typically permissive; 2s between requests usually safe
- Retry logic: `max_retries = 3` with 15s, 30s, 45s waits
- Schema auto-detection on first use (cached in `_input_schema`)

**OpenAI-compatible (Local):**
- No rate limiting (local server)
- Timeout: Configurable, default 120 seconds per request

## Response Format Standards

**Gemini API Response:**
- Standard Google AI SDK response format
- Text extraction: `response.text.strip()`
- Error handling: `uploaded_file.state.name` polling for ACTIVE status

**Replicate API Response:**
- JSON REST response with status field
- Status values: "succeeded" (normal), "failed" (error)
- Output extraction: Either list or string; concatenated if list
- Error responses: 422 Unprocessable, 200/201 success codes

**OpenAI-compatible Response:**
- Standard OpenAI chat completions JSON format
- Structure: `{"choices": [{"message": {"content": "text"}}]}`
- Text extraction: `choices[0]["message"]["content"]`

---

*Integration audit: 2026-02-27*
