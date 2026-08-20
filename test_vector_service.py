import math

from app.services.vector_service import (
    LocalHashEmbeddingProvider,
    VectorService,
)


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (
        (math.sqrt(sum(x * x for x in a)) or 1.0)
        * (math.sqrt(sum(y * y for y in b)) or 1.0)
    )


class FakeQdrantClient:
    """In-memory stand-in for the real Qdrant client."""

    def __init__(self):
        self.collections = {}
        self.points = {}
        self.created = []
        self.last_query = None

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, collection_name, vectors_config=None):
        self.collections[collection_name] = vectors_config
        self.points.setdefault(collection_name, {})
        self.created.append(collection_name)

    def upsert(self, collection_name, points):
        store = self.points.setdefault(collection_name, {})
        for point in points:
            store[point.id] = {
                "vector": point.vector,
                "payload": point.payload,
            }
        return None

    def query_points(self, collection_name, query, limit=10,
                     score_threshold=None, with_payload=True):
        self.last_query = query

        store = self.points.get(collection_name, {})

        scored = []
        for point_id, record in store.items():
            similarity = cosine(query, record["vector"])
            if score_threshold is None or similarity >= score_threshold:
                scored.append((similarity, point_id, record["payload"]))

        scored.sort(key=lambda item: item[0], reverse=True)

        class FakePoint:
            pass

        class FakeResponse:
            points = []

        response = FakeResponse()
        for similarity, point_id, payload in scored[:limit]:
            point = FakePoint()
            point.id = point_id
            point.score = similarity
            point.payload = payload
            response.points.append(point)

        return response


def make_service():
    client = FakeQdrantClient()
    service = VectorService(
        client=client,
        embedding_provider=LocalHashEmbeddingProvider(dimension=384),
        collection_name="company_analyses",
    )
    return client, service


def analysis(symbol, score=78, seq="101"):
    return {
        "symbol": symbol,
        "summary": (
            "Revenue grew strongly this quarter and profit increased "
            "on higher operating income."
        ),
        "positive_factors": [
            "Revenue growth strong",
            "Profit increased",
        ],
        "negative_factors": [
            "Operating margin slightly lower",
        ],
        "growth_analysis": [
            "Revenue up strongly quarter on quarter",
        ],
        "margin_analysis": [
            "Operating margin steady",
        ],
        "risk_factors": [
            "High costs may pressure future margins",
        ],
        "company_score": score,
        "score_explanation": (
            "Strong revenue and profit growth supported by steady margins."
        ),
    }


def main():

    # ========== 1. COLLECTION CREATION (auto) ==========
    print("== 1. COLLECTION CREATION ==")
    client, service = make_service()

    assert service.collection_name == "company_analyses"
    assert "company_analyses" in client.created
    assert client.collection_exists("company_analyses") is True
    assert client.collections["company_analyses"].size == 384

    print("  OK -> collection auto-created with correct vector size")
    client = None

    # ========== 2. VECTOR UPSERT + METADATA ==========
    print("== 2. VECTOR UPSERT + METADATA ==")
    client, service = make_service()

    stored = service.store_analysis(
        "ABC",
        analysis("ABC", score=78, seq="101"),
        seq_number="101",
        company_score=78,
    )

    assert stored["point_id"] == "ABC"
    assert stored["company_score"] == 78

    point = client.points["company_analyses"]["ABC"]
    assert len(point["vector"]) == 384
    assert math.isclose(
        math.sqrt(sum(v * v for v in point["vector"])), 1.0
    )

    payload = point["payload"]
    assert payload["symbol"] == "ABC"
    assert payload["seq_number"] == "101"
    assert payload["company_score"] == 78
    assert payload["analyzed_at"]
    assert payload["summary"].startswith("Revenue grew strongly")

    print("  OK -> vector + metadata stored (symbol, seq, score, timestamp)")
    client = None

    # ========== 3. DUPLICATE / UPDATE BEHAVIOR ==========
    print("== 3. DUPLICATE / UPDATE BEHAVIOR ==")
    client, service = make_service()

    service.store_analysis("ABC", analysis("ABC", score=78), company_score=78)
    service.store_analysis("ABC", analysis("ABC", score=91), company_score=91)

    points = client.points["company_analyses"]
    assert len(points) == 1, f"expected 1 point, got {len(points)}"
    assert points["ABC"]["payload"]["company_score"] == 91
    assert points["ABC"]["payload"]["analyzed_at"]

    service.store_analysis("DEF", analysis("DEF", score=55), company_score=55)
    assert len(points) == 2

    print("  OK -> same symbol updates the same point; new symbol adds")
    client = None

    # ========== 4. SEMANTIC SEARCH ==========
    print("== 4. SEMANTIC SEARCH ==")
    client, service = make_service()

    service.store_analysis("ABC", analysis("ABC"), company_score=78)
    service.store_analysis("DEF", {
        "symbol": "DEF",
        "summary": "Company faced losses due to falling demand.",
        "positive_factors": [],
        "negative_factors": ["Losses widened"],
        "growth_analysis": ["Revenue declined sharply"],
        "margin_analysis": ["Margin compressed"],
        "risk_factors": ["Demand decline"],
        "company_score": 30,
        "score_explanation": "Weak results with rising losses.",
    }, company_score=30)

    results = service.search(
        "revenue growth profit increased",
        limit=5,
    )

    assert len(results) == 2, results
    assert results[0]["point_id"] == "ABC", results
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["payload"]["company_score"] == 78

    # score_threshold filtering
    filtered = service.search(
        "revenue growth profit increased",
        limit=5,
        score_threshold=results[0]["score"] - 0.001,
    )
    assert filtered and filtered[0]["point_id"] == "ABC"

    print("  OK -> semantic search returns ranked analyses with payload")
    client = None

    # ========== 5. MISSING / INVALID ANALYSIS DATA ==========
    print("== 5. MISSING / INVALID ANALYSIS DATA ==")
    client, service = make_service()

    try:
        service.store_analysis("", analysis("ABC"))
        assert False, "empty symbol must raise"
    except ValueError:
        pass

    try:
        service.store_analysis("ABC", {})
        assert False, "empty analysis must raise"
    except ValueError:
        pass

    try:
        service.store_analysis("ABC", {"summary": "   "})
        assert False, "blank analysis must raise"
    except ValueError:
        pass

    try:
        service.search("")
        assert False, "empty query must raise"
    except ValueError:
        pass

    try:
        service.search(None)
        assert False, "None query must raise"
    except ValueError:
        pass

    try:
        LocalHashEmbeddingProvider().embed("")
        assert False, "empty embed text must raise"
    except ValueError:
        pass

    print("  OK -> missing/invalid analysis data rejected safely")

    print("\nALL STEP 11 CHECKS PASSED")


if __name__ == "__main__":
    main()