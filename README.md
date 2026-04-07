# CorpusLens

**CorpusLens** is a **local-first research workspace**: upload PDFs and images, run **hybrid retrieval** (lexical + semantic), and get **Markdown answers** with **citations** and an **evidence panel**—without sending your documents to a third-party cloud API.

Repository: **[github.com/tayyabrehman96/CorpusLens](https://github.com/tayyabrehman96/CorpusLens)**

**Architecture (detailed)**: see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — directory map, data flow, modules, Mermaid diagram, and extension points.

**AI roadmap**: see **[docs/ROADMAP.md](docs/ROADMAP.md)** — reranking, scan OCR, optional Ollama vision captions, and future ideas.

---

## About

**CorpusLens** helps researchers, students, and teams **query their own PDFs and images** using **retrieval-augmented generation** that runs **on your hardware**. Documents are chunked, indexed with **hybrid search** (keyword + embeddings), and answers stream back with **citations** and an **evidence** view so you can verify claims against the source files. It is designed for **privacy** (no required cloud document upload), **hackability** (clear API + local data folder), and **honest limits** (quality depends on your PDFs, retrieval settings, and local LLM choice).

---

## Topics & stack

| Topic | Notes |
|-------|--------|
| **Languages** | Python (API, ingest, RAG), TypeScript (UI) |
| **Retrieval** | BM25, dense vectors, Chroma, reciprocal rank fusion |
| **Models** | sentence-transformers (`bge-small-en-v1.5` default), Hugging Face or Ollama LLMs |
| **Documents** | PyMuPDF, optional Tesseract OCR on figures |
| **UI** | Next.js 15, Tailwind, React Markdown + GFM |

**Suggested GitHub topics** (add under repository **About → Topics**):  
`rag` `retrieval-augmented-generation` `llm` `local-llm` `ollama` `huggingface` `fastapi` `nextjs` `typescript` `python` `chromadb` `sentence-transformers` `bm25` `pdf` `ocr` `privacy` `open-source` `research-tools` `semantic-search` `hybrid-search`

---

## What it is

| Aspect | Description |
|--------|-------------|
| **Purpose** | Private **RAG** (retrieval-augmented generation) for papers, reports, and image-backed notes. |
| **Stack** | **FastAPI** backend, **Next.js 15** UI, **SQLite** (metadata), **Chroma** (vector index), **sentence-transformers** embeddings, **PyMuPDF** PDF parsing. |
| **LLM** | **Your machine**: either a local **Hugging Face** instruct model (`hf_local`) or **Ollama** over HTTP—configurable in `backend/.env`. |
| **Privacy** | Documents and indexes stay under `backend/data/` on disk (git-ignored). No vendor lock-in for file storage. |

---

## What works today

- **Ingest**: PDFs (text-native and many scans) and **images** (PNG, JPEG, WebP, …).
- **PDF profiling**: Heuristic hints (e.g. text-rich vs scan-heavy) after upload.
- **Hybrid retrieval**: **BM25** + **dense vectors** fused with **reciprocal rank fusion**; optional figure caption / OCR indexing.
- **Chat**: **Server-sent events (SSE)** streaming; modes such as **Summary**, **Compare**, **Methodology**, etc.
- **UI**: Dark **research console** layout; **Markdown** answers (including **GFM tables**); **text evidence** table + snippets; **figure** thumbnails when retrieved.
- **Library management**: **Replace library** on upload, **full reset**, per-document delete; **scope** retrieval with checkboxes (with stale-ID safeguards).
- **Export**: **Markdown** export of answer + evidence.

---

## How to use it (quick path)

1. **Backend** — from repo root:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   copy .env.example .env
   # Edit .env: LLM_BACKEND (hf_local | ollama), models, CORS if needed
   .\.venv\Scripts\uvicorn.exe app.main:app --reload --host localhost --port 8000
   ```

   To reach the API from **another device** on your network, use `--host 0.0.0.0 --port 8000`, add that machine’s IP to `CORS_ORIGINS` in `backend/.env`, and set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to `http://<that-ip>:8000`.

2. **Frontend**:

   ```powershell
   cd frontend
   copy .env.local.example .env.local
   npm install
   npm run dev
   ```

3. Open **[http://localhost:3000](http://localhost:3000)**. The UI defaults to `http://localhost:8000` for the API; override with `NEXT_PUBLIC_API_URL` in `frontend/.env.local` if you use another host or port.

4. **Workflow**: Upload files → wait until **chunk counts** appear on library cards → enter a question → **Run query** → read the streamed answer and **evidence** panels. Leave checkboxes **off** to search the whole library; tick files to **restrict scope**.

---

## How it works (high level)

1. **Upload** → file stored on disk, document row in SQLite, **PDF profile** metadata when applicable.  
2. **Ingest** → text chunked (size/overlap from settings), optional **figure** extraction + caption heuristics + optional **Tesseract** OCR on crops.  
3. **Index** → chunks (and figure text) embedded with **`BAAI/bge-small-en-v1.5`** by default, stored in **Chroma**.  
4. **Query** → user message retrieves top‑k chunks (and optionally figures), then the **LLM** generates an answer **only from that context** (prompt enforces citations).  
5. **Stream** → tokens returned over SSE; final event includes **evidence** payloads for the UI.

Default URLs use **`localhost`** for readability; **`127.0.0.1`** is equivalent for loopback. For LAN access, bind the API with `--host 0.0.0.0`, point the frontend at `http://<server-ip>:8000`, and align **`CORS_ORIGINS`**, **`NEXT_PUBLIC_API_URL`**, and optional **`API_PUBLIC_URL`** (Markdown export figure links).

---

## Accuracy & limitations (read this)

CorpusLens is a **tool**, not a source of truth. Quality depends on **retrieval**, **model size**, and **your PDFs**.

| Factor | Effect |
|--------|--------|
| **Retrieval** | If the right passages are not in the top‑k chunks, the model cannot cite them. **Increase “context breadth”** in the UI or rephrase questions. |
| **Scoped checkboxes** | If the wrong (or stale) documents are selected, answers can be empty or irrelevant. **Clear scope** to search the full library. |
| **PDF type** | **Text-native PDFs** index best. **Scanned** or image-heavy PDFs may yield little text unless figures/OCR help; the UI surfaces **profile hints**. |
| **Local LLM size** | Default **`hf_local`** uses a **small** instruct model suitable for CPU; it may **hallucinate** or **over-generalize** more than large cloud models. **Ollama** with a larger model (e.g. 7B+) often improves reasoning—at the cost of RAM/VRAM and speed. |
| **Citations** | The system **asks** the model to cite like `[Title p.N]`; adherence is **not guaranteed**—always **verify** against the **evidence** panel and original PDF. |

**Bottom line:** Use CorpusLens for **draft synthesis**, **exploration**, and **source-grounded drafts**—not as a substitute for reading critical sources yourself.

---

## Performance (expectations)

| Area | What to expect |
|------|----------------|
| **First run** | Embedding model download; **HF** LLM weights download into `backend/data/hf_hub/` unless pre-cached. |
| **CPU** | Embeddings and small HF models run on **CPU** by default; **first** generation after load can take **minutes** on modest hardware; later queries are faster. |
| **Streaming** | SSE **reduces perceived latency**; tokens appear as they are generated. |
| **Disk** | SQLite + Chroma + uploads grow with library size; wipe with **Reset library** or `replace_library` on upload when needed. |
| **Ollama** | Latency scales with **model size** and hardware; use a smaller tag for speed, larger for quality. |

Install **[Tesseract OCR](https://github.com/tesseract-ocr/tesseract)** on your `PATH` for **figure OCR** and for **full-page OCR** on PDFs classified as scan-heavy or low-text (`PDF_OCR_PAGES_ENABLED`, see `.env.example`).

---

## API overview

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/documents/upload` | Upload PDF/image (`replace_library` query optional). |
| `POST` | `/api/documents/library/reset` | Wipe DB, vectors, files, assets. |
| `GET` | `/api/documents` | List documents (+ chunk/asset counts, ingest profile). |
| `DELETE` | `/api/documents/{id}` | Remove one document. |
| `GET` | `/api/documents/{id}/file` | Download original file. |
| `POST` | `/api/chat/stream` | SSE chat (`message`, `document_ids`, `mode`, `retrieve_k`, `detail_level`, `fast_mode`). |
| `GET` | `/api/chat/health/llm` | Backend + model info. |
| `POST` | `/api/export/markdown` | Export notes. |
| `GET` | `/api/health` | API liveness. |

---

## Environment variables

See **`backend/.env.example`** for the full list. Commonly tuned:

| Variable | Role |
|----------|------|
| `LLM_BACKEND` | `hf_local` (default) or `ollama` |
| `HF_LOCAL_MODEL` | Hugging Face model id for local generation |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Ollama endpoint and tag |
| `EMBEDDING_MODEL` | Default `BAAI/bge-small-en-v1.5` |
| `RERANK_ENABLED` | `true` to cross-encoder rerank hybrid text hits (extra model download) |
| `PDF_OCR_*` | Full-page Tesseract OCR for weak PDF text layers |
| `OLLAMA_VISION_MODEL` | Optional vision tag for **figure captions** at ingest (Ollama must support images) |
| `CORS_ORIGINS` | Frontend origins (e.g. `http://localhost:3000`) |
| `API_PUBLIC_URL` | Optional base URL of this API for **absolute** figure links in exported Markdown |

Frontend: **`frontend/.env.local.example`** — set `NEXT_PUBLIC_API_URL` to wherever the browser must call the API (default `http://localhost:8000`).

---

## Docker (Ollama only)

```powershell
docker compose up -d
```

Exposes Ollama on **11434**. Set `OLLAMA_BASE_URL` accordingly; run FastAPI and Next.js on the host (or containerize them separately if you extend the setup).

---

## Troubleshooting

| Symptom | Things to try |
|---------|----------------|
| **Empty answers / no evidence** | Clear library checkboxes; confirm **chunk count > 0** on cards; re-upload if ingest failed. |
| **Upload rejected** | PDF must start with **`%PDF`**; empty files are rejected; unusable PDFs are rolled back (no ghost rows). |
| **Ollama errors** | CorpusLens uses **`POST /api/generate`** (not `/api/chat`). Check `GET /api/chat/health/llm`. |
| **CORS** | Add your frontend origin to `CORS_ORIGINS` in `backend/.env`. |
| **UI looks broken** (plain HTML, default fonts, gray buttons) | Next dev served a **404** for `/_next/static/css/app/layout.css` (stale `.next`). Stop the dev server, then from `frontend` run **`npm run dev:fresh`** (or delete the `frontend/.next` folder and run **`npm run dev`** again). Hard-refresh the browser (**Ctrl+Shift+R**). |
| **Stale Chroma** | After abnormal shutdowns, if retrieval is inconsistent, try **reset library** and re-ingest. |

---

## Project layout

```
backend/          # FastAPI app, ingest, retrieval, LLM adapters
  app/
  data/           # Created at runtime (ignored by git)
frontend/         # Next.js UI (CorpusLens console)
```

---

## Contributing

Issues and PRs are welcome: retrieval tuning, UI, deployment guides, or optional GPU paths—keep changes focused and documented.

---

## Acknowledgements

Built with **FastAPI**, **Next.js**, **Chroma**, **sentence-transformers**, **PyMuPDF**, and the broader open-source ML ecosystem.

---

## License

Released under the [MIT License](LICENSE).

---

**CorpusLens** — *local retrieval, cited answers, your data on your machine.*
