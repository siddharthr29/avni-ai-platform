"""RAG (Retrieval-Augmented Generation) pipeline for Avni AI Platform.

Implements Anthropic's Contextual Retrieval approach with pgvector-backed
hybrid search (semantic + BM25) and Reciprocal Rank Fusion.

Architecture:
    embeddings.py          - Local sentence-transformers embedding client
    vector_store.py        - pgvector store with hybrid search + RRF
    contextual_retrieval.py - Contextual prefix generation + unified search
    ingestion.py           - Knowledge ingestion pipeline for all collections
    fallback.py            - Unified RAG service with graceful degradation

When PostgreSQL with pgvector is available, the pipeline uses hybrid
vector + keyword search. Otherwise, it falls back to the existing
in-memory keyword search in knowledge_base.py.
"""
