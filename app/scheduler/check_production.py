"""
Safe production configuration / import check for Step 13.

Verifies that the REAL LangGraph workflow, the REAL Groq LLM and
the REAL Qdrant integration initialize correctly using the
configured .env settings, WITHOUT writing to MySQL and WITHOUT
modifying Qdrant data (no points are upserted and an absent
collection is never created here).

Run:

    python -m app.scheduler.check_production

Exits non-zero with a clear message when a required credential or
external service is missing or unreachable.
"""

import sys

from app.core.config import settings
from app.services.ai_analysis_service import AIAnalysisService
from app.services.pipeline_service import PipelineService
from app.workflows.analysis_workflow import AnalysisWorkflow


def check_credentials():
    """Return the names of any missing required credentials."""
    missing = []

    if not settings.DATABASE_URL:
        missing.append("DATABASE_URL")

    if not settings.GROQ_API_KEY:
        missing.append("GROQ_API_KEY")

    if not settings.QDRANT_HOST:
        missing.append("QDRANT_HOST")

    return missing


def check_real_langgraph():
    """Build the REAL LangGraph workflow graph (no DB writes)."""
    print("CHECK | LangGraph | building REAL AnalysisWorkflow graph ...")

    workflow = AnalysisWorkflow(db=None)

    nodes = sorted(getattr(workflow.graph, "nodes", {}).keys())

    print(f"CHECK | LangGraph | OK | graph built | nodes: {nodes}")

    if not nodes:
        print("FAIL | LangGraph | empty graph")
        sys.exit(1)


def check_real_groq_llm():
    """Construct the REAL Groq LLM service (no network call)."""
    print("CHECK | Groq LLM | constructing REAL AIAnalysisService ...")

    service = AIAnalysisService()

    print(
        "CHECK | Groq LLM | OK | "
        f"llm={type(service.llm).__name__} | "
        f"model={getattr(service.llm, 'model', 'unknown')}"
    )


def check_real_qdrant():
    """Verify connectivity to the REAL Qdrant instance (read-only)."""
    from app.services.vector_service import VectorService, build_qdrant_client

    print(
        "CHECK | Qdrant | connecting to "
        f"{settings.QDRANT_URL or settings.QDRANT_HOST}:"
        f"{settings.QDRANT_PORT} ..."
    )

    client = build_qdrant_client()

    collections = client.get_collections()
    names = sorted(c.name for c in collections.collections)

    print(f"CHECK | Qdrant | connected | existing collections: {names}")

    exists = client.collection_exists(settings.QDRANT_COLLECTION_NAME)

    print(
        "CHECK | Qdrant | collection "
        f"'{settings.QDRANT_COLLECTION_NAME}' exists: {exists}"
    )

    if exists:
        # Safe: the collection already exists, so constructing the REAL
        # VectorService performs no mutation at all.
        vector_service = VectorService(
            client=client,
            collection_name=settings.QDRANT_COLLECTION_NAME,
        )
        print(
            "CHECK | Qdrant | OK | REAL VectorService initialized "
            f"(collection: {vector_service.collection_name})"
        )
    else:
        print(
            "CHECK | Qdrant | NOTE: collection absent - REAL VectorService "
            "auto-creates it (empty) on the first pipeline run"
        )


def main():
    print("=== PRODUCTION CONFIGURATION / IMPORT CHECK ===")
    print("ENV | DATABASE_URL:", settings.DATABASE_URL or "MISSING")
    print(
        "ENV | GROQ_API_KEY:",
        "configured" if settings.GROQ_API_KEY else "MISSING",
    )
    print("ENV | QDRANT_HOST:", settings.QDRANT_HOST)
    print("ENV | QDRANT_PORT:", settings.QDRANT_PORT)
    print(
        "ENV | QDRANT_API_KEY:",
        "configured" if settings.QDRANT_API_KEY else "empty",
    )
    print("ENV | QDRANT_COLLECTION_NAME:", settings.QDRANT_COLLECTION_NAME)
    print("ENV | QDRANT_DIMENSION:", settings.QDRANT_DIMENSION)

    missing = check_credentials()

    if missing:
        print(
            "FAIL | missing required configuration: "
            + ", ".join(missing)
        )
        print("ACTION | set the missing values in .env and re-run")
        sys.exit(1)

    # Construct the REAL pipeline wiring without running it: this never
    # opens a database connection and never touches Qdrant, because the
    # VectorService is created lazily at the store stage only.
    print(
        "CHECK | PipelineService | constructing REAL components "
        "(no pipeline run) ..."
    )

    pipeline = PipelineService(db=None)

    print(
        "CHECK | PipelineService | OK | "
        f"workflow={type(pipeline.workflow).__name__} | "
        f"contract_service={type(pipeline.contract_service).__name__}"
    )

    try:
        check_real_langgraph()
    except Exception:
        print("FAIL | LangGraph | could not build the workflow")
        print("ACTION | check the langgraph installation in .venv")
        sys.exit(1)

    try:
        check_real_groq_llm()
    except Exception:
        print("FAIL | Groq LLM | could not construct AIAnalysisService")
        print(
            "ACTION | set a valid GROQ_API_KEY in .env "
            "(do not invent credentials)"
        )
        sys.exit(1)

    try:
        check_real_qdrant()
    except Exception as exc:
        print(f"FAIL | Qdrant | not reachable: {exc}")
        print(
            "ACTION | start a Qdrant instance at "
            f"{settings.QDRANT_HOST}:{settings.QDRANT_PORT} "
            "(docker run -p 6333:6333 qdrant/qdrant) and re-run"
        )
        sys.exit(1)

    print("=== PRODUCTION CHECK PASSED ===")


if __name__ == "__main__":
    main()