"""
Long-term memory layer using ChromaDB.

Stores freeform preference notes per user ("doesn't like early flights",
"prefers walkable neighborhoods") and retrieves the most relevant ones for
a new planning session via semantic similarity search.
"""
from __future__ import annotations
import os
import uuid
from typing import List
import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma_store")

_client = chromadb.PersistentClient(path=CHROMA_PATH)

# Uses Chroma's built-in default embedding function (all-MiniLM-L6-v2, runs
# locally, no API key needed) so memory works even before any LLM key is set.
_embedder = embedding_functions.DefaultEmbeddingFunction()

_collection = _client.get_or_create_collection(
    name="trip_preferences",
    embedding_function=_embedder,
)


def add_preference(user_id: str, note: str) -> None:
    """Store a new preference note, e.g. after a trip is finalized or the
    user gives explicit feedback like 'I hate 6am flights'."""
    _collection.add(
        ids=[str(uuid.uuid4())],
        documents=[note],
        metadatas=[{"user_id": user_id}],
    )


def get_relevant_preferences(user_id: str, query: str, n_results: int = 5) -> List[str]:
    """Semantic search over this user's stored preferences relevant to the
    current planning query (e.g. 'planning a trip to Japan')."""
    try:
        results = _collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id},
        )
        docs = results.get("documents", [[]])
        return docs[0] if docs else []
    except Exception:
        # Empty collection or first-ever run for this user - not an error.
        return []


def list_all_preferences(user_id: str) -> List[str]:
    results = _collection.get(where={"user_id": user_id})
    return results.get("documents", [])
