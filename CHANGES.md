# What's in this zip

This is your `IFRS-Reporting` project with the climate-risk-analysis feature
already applied in place. Everything below was either added as a new file
or patched directly into the existing file — nothing needs to be manually
copied into a different folder. `node_modules/`, `.venv/`, `.angular/`,
`dist/`, and `__pycache__/` were stripped (regenerate with `npm install` /
`pip install -r requirements.txt`); the stale `db.sqlite3` was also removed
so your first `migrate` starts clean and actually includes the new tables.

## New files

```
data/payload_BANK01_improved.json          -- the improved/augmented data file

backend/requirements.txt                   -- new (didn't exist before)
backend/risk_analysis/                     -- new Django app
  __init__.py
  admin.py
  apps.py
  llm.py            -- NVIDIA NIM (meta/llama-3.3-70b-instruct) call, server-side
  models.py         -- RiskAnalysis, AssessmentResult
  serializers.py
  services.py       -- all chart/KPI/augmentation derivation logic
  urls.py
  validators.py
  views.py
  migrations/
    __init__.py
    0001_initial.py -- generated with makemigrations against your real User model

frontend/esg-intelligence-system/src/app/auth.interceptor.ts   -- new (none existed before)
```

## Patched files (changes applied directly, nothing else in them touched)

- **`backend/config/settings.py`**
  - added `"risk_analysis"` to `INSTALLED_APPS`
  - added `NVIDIA_API_KEY = config("NVIDIA_API_KEY", default=None)`
  - added `FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE` (25MB)
- **`backend/config/urls.py`** — added `path("api/", include("risk_analysis.urls"))`
- **`backend/.env`** — appended an empty `NVIDIA_API_KEY=` line with a comment.
  **You still need to paste your own key here** — see "Before you run it" below.
- **`frontend/.../src/app/core/services/risk.ts`** — was an empty stub, now the real service
- **`frontend/.../src/app/pages/risk-analysis/risk-analysis.ts / .html / .css`** — were a placeholder page, now the real upload-to-dashboard workflow
- **`frontend/.../src/app/app.routes.ts`** — added the `risk-analysis` route, which previously didn't exist anywhere
- **`frontend/.../src/app/app.config.ts`** — registered the new `authInterceptor`
- **`frontend/.../src/app/layout/sidebar/sidebar.html`** — the existing "Risk Analysis" nav link had no `routerLink` (it was dead); it now points at `/risk-analysis`

## Before you run it

1. **Open `backend/.env`** and set your own key:
   ```
   NVIDIA_API_KEY=nvapi-your-real-key-here
   ```
   Do not reuse any key that has appeared in a chat, code sample, or shared
   doc — rotate it in NVIDIA NGC first if it has. Without a key, the
   assessment endpoint still works; it just always returns the
   deterministic fallback in `risk_analysis/llm.py::_fallback` instead of a
   live Llama-3.3-70B paragraph.

2. **Backend:**
   ```bash
   cd backend
   pip install -r requirements.txt
   python manage.py makemigrations   # should report "No changes detected"
   python manage.py migrate
   python manage.py runserver
   ```

3. **Frontend:**
   ```bash
   cd frontend/esg-intelligence-system
   npm install
   npm start
   ```

4. Log in, click **Risk Analysis** in the sidebar (it's now a live link),
   and drop in `data/payload_BANK01_improved.json` — or any other reporting
   payload JSON — to see the upload happen for real.

## The workflow this gives you

1. Drop a `.json` reporting payload on `/risk-analysis`.
2. It's POSTed to `/api/risk/upload/`, which validates it
   (`validators.py` — hard-fails only if `bank` / `reporting_kpis` /
   `financial_summary` is entirely missing; everything else is a
   non-blocking warning shown on the page), processes it (`services.py` —
   derives every KPI, chart series, and the data-quality / peer-benchmark /
   sensitivity augmentation from whatever is actually in the file), and
   persists + returns the result in one round trip.
3. The page renders every KPI and chart from that response immediately —
   nothing is hardcoded; categories, hazard types, and risk types are read
   from the upload via groupby logic, so a different bank's payload with
   different categories still renders correctly.
4. The page then calls `/api/risk/analyses/<id>/assessment/`, which calls
   NVIDIA's NIM-hosted Llama 3.3 70B server-side. The model can only cite
   `[E#]` ids that already exist with real sourced values; hovering one
   shows that value, its source table, and the IFRS S2 paragraph. A
   hallucinated or malformed response falls back to a deterministic
   template built from the same evidence catalogue — the dashboard never
   breaks.
5. Click "New upload" to analyze a different file — no redeploy needed.

## What was actually tested before this was packaged

- The Django migration was generated for real with `makemigrations`
  against the real `accounts.User` model, then applied with `migrate`.
- The full upload to process to assess to fetch flow was exercised through
  Django's real test client (login, upload, detail, assessment generate,
  assessment latest, list) — all returning the expected status codes.
- `llm.py` was tested against five mocked scenarios at the HTTP boundary:
  valid citation, hallucinated citation, markdown-fenced JSON, non-JSON
  garbage, and missing API key — all five behave correctly, including a
  citation-parsing bug that was caught and fixed during this testing.
- The Angular component, service, interceptor, and template were compiled
  with the real `@angular/compiler-cli` in strict template mode: 0 errors,
  0 warnings.
- The only thing **not** tested live is the actual network call to
  `integrate.api.nvidia.com` — that domain isn't reachable from the
  sandbox this was built in. Everything up to and after that call (request
  construction, response parsing, citation validation, fallback) is
  verified; the live round trip itself will be exercised for the first
  time when you run it.
