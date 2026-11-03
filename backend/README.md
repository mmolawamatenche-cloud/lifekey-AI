# Local AI backend

The local backend adds Ollama/Qwen chat without replacing the existing AppDeploy
backend. During Vite development, `/api` requests are proxied to this service.
The service binds to `127.0.0.1` and keeps prompts on this computer; cloud AI is
disabled. Regular chat uses free-form responses; role-based Brain requests ask
Ollama for the answer/actions JSON schema.

## Windows setup

Install Python 3.10 or newer and Ollama for Windows first. Open PowerShell in the
repository root, then install the Python dependencies:

```powershell
winget install --id Ollama.Ollama --exact --source winget --accept-source-agreements --accept-package-agreements
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

The `winget` command installs Ollama. The `venv` and `pip` commands create an
isolated Python environment and install the backend packages. The copy command
creates local configuration; edit `backend\.env` to select a different model.
If the system drive is low on space, set `OLLAMA_MODELS` to a folder on a drive
with room before starting Ollama. For example, this PowerShell command stores
Ollama models on D:; restart Ollama after changing it:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "D:\LIFEKEY-AI\models", "User")
```

Start Ollama and download the default model:

```powershell
ollama pull qwen3:8b
```

In one VS Code terminal, select the requested model and start the backend from
the repository root:

```powershell
$env:LIFEKEY_OLLAMA_MODEL = "qwen3:8b"
backend\.venv\Scripts\python.exe -m uvicorn lifekey_backend.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal, start the existing frontend:

```powershell
npm run dev
```

The frontend uses the local backend when `LIFEKEY_AI_URL` is blank. The verified
default is `qwen3:8b`; change `LIFEKEY_OLLAMA_MODEL` in `backend\.env` to
`qwen3:4b` for lower memory use or faster CPU inference.

The microphone uses the browser's speech recognition to produce a transcript.
Dictation mode sends that text to `/api/voice/cleanup` for local Ollama cleanup;
it does not upload raw audio to this Python backend. Browser speech recognition
may use browser-managed services. Cleaned text is placed in the composer for
review and is not sent to chat automatically.

## Brain and proposed actions

`POST /api/brain/ask` provides role-specific intelligence for the general
assistant, planner, voice, NeuroLia, vision descriptions, and memory guidance.
It only returns proposed actions. Sensitive proposals create pending approvals;
the backend does not execute proposed actions. These Brain endpoints are an
additive backend API and are not yet connected to new controls in the frontend.

`GET /api/brain/roles` lists available roles. Approval requests can be viewed at
`GET /api/approvals/pending` and decided with
`POST /api/approvals/{approval_id}/decision`.

An optional JSONL audit log can be enabled by setting
`LIFEKEY_APPROVAL_LOG_PATH` in `backend\.env` to a writable file path. It records
request, approval/denial, and consumption events with the action name and summary;
it never records action parameters. A consumed approval is not evidence that an
action was executed. Leave the setting empty to disable logging.

Run backend tests from the repository root with:

```powershell
backend\.venv\Scripts\python.exe -m pytest -q
```

After Ollama is running and the backend is started, verify the live model, chat,
Brain structured-output, and dictation cleanup paths with:

```powershell
backend\.venv\Scripts\python.exe scripts\verify_live_model.py http://127.0.0.1:8000 qwen3:8b
```
