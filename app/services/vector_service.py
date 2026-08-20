import hashlib
import math
import re
from datetime import datetime, timezone

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings


class LocalHashEmbeddingProvider:
    """
    Dependency-free, deterministic embedding provider.

    Converts text into a fixed-dimension unit vector using hashed
    terms. No external API or credentials are required, which keeps
    the project fully offline-capable.

    For production-grade semantic similarity, swap this provider for
    a real embedding model/API (e.g. an OpenAI-compatible endpoint).
    The VectorService accepts any provider exposing embed(text) -> list
    of floats with the same dimension.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    @staticmethod
    def _terms(text: str):
        words = re.findall(r"[a-z0-9]+", text.lower())

        terms = list(words)

        for word in words:
            if len(word) >= 3:
                terms.append(word[:3])  # prefix helps surface stems

        return terms

    def embed(self, text: str):
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        vector = [0.0] * self.dimension

        for term in self._terms(text):
            digest = hashlib.md5(term.encode("utf-8")).digest()

            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0

            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))

        if norm == 0:
            raise ValueError("Could not embed analysis text")

        return [value / norm for value in vector]


class VectorService:
    """
    Stores and searches company analysis documents in Qdrant.

    - Embeddings are generated from the structured AI analysis text.
    - The stable point ID is the company symbol, so re-running an
      analysis updates the existing vector instead of duplicating it.
    - The collection is created automatically when it does not exist.
    """

    def __init__(
        self,
        client=None,
        embedding_provider=None,
        collection_name: str | None = None,
    ):
        self.collection_name = (
            collection_name or settings.QDRANT_COLLECTION_NAME
        )

        self.client = client or QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY or None,
        )

        self.embedding_provider = (
            embedding_provider
            or LocalHashEmbeddingProvider(
                dimension=settings.QDRANT_DIMENSION
            )
        )

        self.dimension = self.embedding_provider.dimension

        self._ensure_collection()

    # ----------------------------------------------------------
    # Collection management
    # ----------------------------------------------------------

    def _ensure_collection(self):
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE,
                ),
            )

        return True

    # ----------------------------------------------------------
    # Embedding text
    # ----------------------------------------------------------

    @staticmethod
    def _analysis_text(structured_analysis: dict) -> str:
        """
        Flatten the structured analysis into a single embeddable text.
        """

        if not structured_analysis or not isinstance(
            structured_analysis, dict
        ):
            return ""

        parts = [
            structured_analysis.get("summary") or "",
            " ".join(structured_analysis.get("positive_factors") or []),
            " ".join(structured_analysis.get("negative_factors") or []),
            " ".join(structured_analysis.get("growth_analysis") or []),
            " ".join(structured_analysis.get("margin_analysis") or []),
            " ".join(structured_analysis.get("risk_factors") or []),
            structured_analysis.get("score_explanation") or "",
        ]

        return " ".join(part for part in parts if part).strip()

    # ----------------------------------------------------------
    # Storage
    # ----------------------------------------------------------

    def store_analysis(
        self,
        symbol: str,
        structured_analysis: dict,
        seq_number: str | None = None,
        company_score: int | None = None,
        analyzed_at: str | None = None,
    ):
        """
        Store a structured analysis as a vector document.

        Uses the symbol as the stable point ID: storing the same
        company again updates the existing vector in place.
        """

        if not symbol:
            raise ValueError("symbol is required")

        text = self._analysis_text(structured_analysis)

        if not text:
            raise ValueError(
                "structured analysis contains no embeddable text"
            )

        vector = self.embedding_provider.embed(text)

        analyzed_at = (
            analyzed_at
            or datetime.now(timezone.utc).isoformat()
        )

        payload = {
            "symbol": symbol,
            "seq_number": seq_number,
            "company_score": company_score,
            "analyzed_at": analyzed_at,
            "summary": structured_analysis.get("summary"),
        }

        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=symbol,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

        return {
            "point_id": symbol,
            "symbol": symbol,
            "seq_number": seq_number,
            "company_score": company_score,
            "analyzed_at": analyzed_at,
        }

    # ----------------------------------------------------------
    # Search
    # ----------------------------------------------------------

    def search(
        self,
        query_text: str,
        limit: int = 5,
        score_threshold: float | None = None,
    ):
        """
        Semantic similarity search over stored analyses.
        """

        if not query_text or not query_text.strip():
            raise ValueError("query_text is required")

        vector = self.embedding_provider.embed(query_text)

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        results = []

        for hit in (response.points or []):
            results.append(
                {
                    "point_id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload or {},
                }
            )

        return results