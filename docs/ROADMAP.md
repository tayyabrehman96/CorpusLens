# CorpusLens — product & AI roadmap

This document tracks **implemented** advanced capabilities and **future** extensions. For system layout, see [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## Implemented in this repository

| Feature | Description | Configuration |
|---------|-------------|---------------|
| **Cross-encoder reranking** | After BM25 + vector fusion, top candidates are re-scored with a small cross-encoder so the LLM sees better-aligned passages. | `RERANK_ENABLED=true`, `RERANK_MODEL`, `RERANK_POOL_MULTIPLIER` in `backend/.env` |
| **Full-page PDF OCR** | For PDFs classified as scan-heavy or low-text, pages are rendered and passed through **Tesseract** to build searchable chunks (requires `tesseract` on `PATH`). | `PDF_OCR_PAGES_ENABLED` (default on), `PDF_OCR_MAX_PAGES` |
| **Optional VLM figure captions** | When `OLLAMA_VISION_MODEL` is set (e.g. LLaVA), each extracted figure is sent to **Ollama** for a short description merged into figure index text and the asset `description` field. | `OLLAMA_VISION_MODEL` non-empty; Ollama running with a vision-capable tag |

---

## Future extensions (not implemented)

### Retrieval & indexing

- HyDE / query expansion via LLM before embedding  
- Multi-query retrieval with merged results  
- Hierarchical parent–child chunks  
- Metadata filters (date, tags, section)  
- Layout-aware PDF parsing (column/table structure)  
- Late-interaction (ColBERT-style) indexes  

### Generation & grounding

- Second-pass citation verification  
- Structured JSON / schema-constrained answers  
- Bounded agentic re-retrieval loops  
- Per-mode model routing (different Ollama/HF models)  

### Multimodal

- Local HF vision models (heavier than Ollama HTTP)  
- Audio/video via transcription → same RAG pipeline  

### Product & quality

- Conversation threads + memory  
- Suggested follow-up questions  
- Per-chunk “why ranked” debug UI  
- Offline eval harness (recall@k, citation overlap)  
- PII redaction at ingest  
- API keys / rate limits for shared hosting  

---

## Suggested priority for future work

1. Reranking / multi-query (reranking is now available—toggle on when quality matters more than first-run download size).  
2. Scan OCR path (**implemented** for classified PDFs—ensure Tesseract is installed).  
3. Citation verification or structured JSON modes.  
4. Local or hosted VLM beyond Ollama (highest complexity).

---

*See [README.md](../README.md) for setup and [ARCHITECTURE.md](./ARCHITECTURE.md) for module boundaries.*
