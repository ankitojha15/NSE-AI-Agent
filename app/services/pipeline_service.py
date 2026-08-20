"""
Fully automated NSE earnings analysis pipeline.

Orchestrates the complete earnings flow end-to-end:

    1.  Discover/sync NSE listed companies
    2.  Discover integrated financial filings
    3.  Store new filings (duplicate-safe)
    4.  Extract and normalize XBRL financial data
    5.  Check four-quarter eligibility and backfill
    6.  Calculate QoQ/YoY metrics and insights
    7.  Build the FinancialAnalysisContract
    8.  Run the LangGraph AI analysis workflow
    9.  Persist the structured AI analysis and score
    10. Store the analysis in Qdrant

Every stage reuses the existing services and repositories; no
business logic is duplicated here. The pipeline is idempotent
(every write path is duplicate-safe) and isolated per company and
per filing, so one failure never stops the whole run.
"""

import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.financial_result_repository import (
    FinancialResultRepository,
)
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.financial_contract_service import (
    FinancialAnalysisContractService,
)
from app.services.financial_insight_service import FinancialInsightService
from app.services.nse_service import NseService
from app.services.one_year_pipeline_service import OneYearPipelineService
from app.services.vector_service import VectorService
from app.services.xbrl_parser import XBRLParser
from app.services.xbrl_service import XBRLService
from app.utils.logger import logger
from app.workflows.analysis_workflow import AnalysisWorkflow

MIN_QUARTERS = 4


class PipelineService:
    """
    Fully automated pipeline that turns raw NSE data into a
    stored, vectorised AI analysis for every eligible company.
    """

    def __init__(
        self,
        db: Session,
        nse_service=None,
        ai_service=None,
        contract_service=None,
        vector_client=None,
        embedding_provider=None,
    ):
        self.db = db

        self.nse_service = nse_service or NseService()
        self.contract_service = (
            contract_service or FinancialAnalysisContractService(db)
        )

        # The workflow lazily builds a live LLM only when no
        # ai_service is injected, so tests can mock it safely.
        self.workflow = AnalysisWorkflow(
            db,
            contract_service=self.contract_service,
            ai_service=ai_service,
        )

        self.one_year_service = OneYearPipelineService(self.nse_service, db)
        self.analysis_service = FinancialAnalysisService(db)
        self.insight_service = FinancialInsightService()
        self.financial_repo = FinancialResultRepository(db)

        self.vector_client = vector_client
        self.embedding_provider = embedding_provider
        self._vector_service = None

        self._filings = []

    # ----------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------

    def run(self, max_pages: int = 50, max_companies: int | None = None):
        """
        Run the full pipeline once.

        Returns a summary dict with one entry per stage and one
        entry per processed company, plus overall success flags.
        """

        started = time.monotonic()

        summary = {
            "success": False,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "stages": {},
            "companies": [],
            "companies_success": 0,
            "companies_insufficient": 0,
            "companies_failed": 0,
        }

        # Stage 1 - sync listed companies
        company_sync, company_sync_err = self._run_stage(
            "sync_companies", self._sync_companies
        )
        summary["stages"]["sync_companies"] = (
            company_sync if company_sync_err is None else company_sync_err
        )

        # Stage 2 - discover integrated filings
        filings, filings_err = self._run_stage(
            "discover_filings", self._discover_filings, max_pages
        )
        summary["stages"]["discover_filings"] = (
            {"fetched": len(self._filings)}
            if filings_err is None
            else filings_err
        )

        # Stage 3 - store new filings (duplicate-safe)
        store, store_err = self._run_stage(
            "store_filings", self._store_filings
        )
        summary["stages"]["store_filings"] = (
            store if store_err is None else store_err
        )

        # Stage 4 - extract and normalize XBRL financial data
        xbrl, xbrl_err = self._run_stage(
            "extract_financial_data", self._extract_financial_data
        )
        summary["stages"]["extract_financial_data"] = (
            xbrl if xbrl_err is None else xbrl_err
        )

        # Stages 5-10 - per company
        symbols = self._candidate_symbols()

        if max_companies is not None:
            symbols = symbols[:max_companies]

        for symbol in symbols:
            company = self._process_company(symbol, max_pages)
            summary["companies"].append(company)

            if company["status"] == "ok":
                summary["companies_success"] += 1
            elif company["status"] == "insufficient_quarters":
                summary["companies_insufficient"] += 1
            else:
                summary["companies_failed"] += 1

        fatal_errors = [
            error for error in (
                company_sync_err,
                filings_err,
                store_err,
                xbrl_err,
            ) if error is not None
        ]

        summary["ended_at"] = datetime.now(timezone.utc).isoformat()
        summary["duration_seconds"] = round(time.monotonic() - started, 2)
        summary["fatal_stage_errors"] = fatal_errors
        summary["success"] = not fatal_errors

        logger.info(
            "PIPELINE SUMMARY | success: %s | companies: "
            "success=%s insufficient=%s failed=%s | duration: %ss",
            summary["success"],
            summary["companies_success"],
            summary["companies_insufficient"],
            summary["companies_failed"],
            summary["duration_seconds"],
        )

        return summary

    # ----------------------------------------------------------
    # Stage helpers
    # ----------------------------------------------------------

    def _run_stage(self, stage, fn, *args):
        self._stage_log(stage, status="started")

        try:
            result = fn(*args)
            self._stage_log(stage, status="ok")
            return result, None

        except Exception:
            logger.exception("PIPELINE STAGE | %s | status: failed", stage)
            return None, {"stage": stage, "error": "stage failed"}

    def _stage_log(self, stage, **fields):
        detail = " | ".join(f"{key}: {value}" for key, value in fields.items())
        logger.info("PIPELINE STAGE | %s | %s", stage, detail)

    # ----------------------------------------------------------
    # Stage 1 - discover/sync NSE listed companies
    # ----------------------------------------------------------

    def _sync_companies(self):
        summary = self.nse_service.sync_listed_companies(self.db)

        self._stage_log(
            "sync_companies",
            new=summary.get("new"),
            updated=summary.get("updated"),
            unchanged=summary.get("unchanged"),
            skipped=summary.get("skipped"),
            failed=summary.get("failed"),
        )

        return summary

    # ----------------------------------------------------------
    # Stage 2 - discover integrated financial filings
    # ----------------------------------------------------------

    def _discover_filings(self, max_pages: int):
        self._filings = []

        records = self.nse_service.get_all_integrated_filings(
            max_pages=max_pages
        )
        self._filings = records

        self._stage_log("discover_filings", fetched=len(records))

        return records

    # ----------------------------------------------------------
    # Stage 3 - store new filings (duplicate-safe)
    # ----------------------------------------------------------

    def _store_filings(self):
        counts = {"created": 0, "existing": 0, "skipped": 0, "failed": 0}

        for record in self._filings:
            seq_id = record.get("seq_Id") or record.get("seqNumber")
            symbol = record.get("symbol")

            if not seq_id:
                counts["skipped"] += 1
                continue

            try:
                if self.financial_repo.get_by_seq_number(seq_id):
                    counts["existing"] += 1
                else:
                    self.financial_repo.create(record)
                    counts["created"] += 1

            except Exception:
                logger.exception(
                    "PIPELINE STAGE | store_filings | "
                    "filing failed | symbol: %s | seq: %s",
                    symbol,
                    seq_id,
                )
                counts["failed"] += 1

        self._stage_log(
            "store_filings",
            created=counts["created"],
            existing=counts["existing"],
            skipped=counts["skipped"],
            failed=counts["failed"],
        )

        return counts

    # ----------------------------------------------------------
    # Stage 4 - extract and normalize XBRL financial data
    # ----------------------------------------------------------

    def _extract_financial_data(self):
        counts = {"attempted": 0, "updated": 0, "skipped": 0, "failed": 0}

        xbrl_service = XBRLService()
        parser = XBRLParser()

        for record in self._filings:
            seq_id = record.get("seq_Id") or record.get("seqNumber")

            if not seq_id or not record.get("xbrl"):
                counts["skipped"] += 1
                continue

            existing = self.financial_repo.get_by_seq_number(seq_id)

            if not existing or existing.financial_data:
                counts["skipped"] += 1
                continue

            counts["attempted"] += 1

            try:
                xml = xbrl_service.download_xbrl(record["xbrl"])
                root = parser.parse(xml)
                financial_data = parser.extract_financial_data(root)

                self.financial_repo.update_financial_data(
                    seq_id, financial_data
                )

                counts["updated"] += 1

            except Exception:
                logger.exception(
                    "PIPELINE STAGE | extract_financial_data | "
                    "xbrl failed | symbol: %s | seq: %s",
                    record.get("symbol"),
                    seq_id,
                )
                counts["failed"] += 1

        self._stage_log(
            "extract_financial_data",
            attempted=counts["attempted"],
            updated=counts["updated"],
            skipped=counts["skipped"],
            failed=counts["failed"],
        )

        return counts

    # ----------------------------------------------------------
    # Per-company stages 5-10
    # ----------------------------------------------------------

    def _candidate_symbols(self):
        symbols = set()

        for record in self._filings:
            symbol = record.get("symbol")
            if symbol:
                symbols.add(symbol)

        return sorted(symbols)

    def _process_company(self, symbol: str, max_pages: int):
        result = {
            "symbol": symbol,
            "status": "failed",
            "error": None,
        }

        # Stage 5 - four-quarter eligibility with automatic backfill
        try:
            quarters = self.one_year_service.ensure_company_quarters(
                symbol,
                min_quarters=MIN_QUARTERS,
                max_pages=max_pages,
            )

        except Exception:
            logger.exception(
                "PIPELINE COMPANY | %s | stage: four_quarter_eligibility | "
                "status: failed",
                symbol,
            )
            result["error"] = "four-quarter eligibility check failed"
            return result

        result["quarter_count"] = quarters.get("quarter_count")
        result["backfilled"] = quarters.get("backfilled")

        if not quarters.get("eligible"):
            self._stage_log(
                "four_quarter_eligibility",
                symbol=symbol,
                status="insufficient_quarters",
                quarter_count=quarters.get("quarter_count"),
            )
            result["status"] = "insufficient_quarters"
            return result

        # Stages 6-9 - metrics, contract, AI workflow, persistence
        try:
            analysis = self._metrics_and_insights(symbol)
            contract = self._build_contract(symbol)
            state = self._run_ai_workflow(symbol)
            persisted_id = self._persist_analysis(symbol, state)

        except Exception:
            logger.exception(
                "PIPELINE COMPANY | %s | status: failed | "
                "stage: metrics/contract/workflow/persist",
                symbol,
            )
            result["error"] = "analysis stages failed"
            return result

        result["quarter_count"] = quarters.get("quarter_count")
        result["backfilled"] = quarters.get("backfilled")
        result["qoq_metrics"] = len(analysis.get("qoq") or {})
        result["yoy_metrics"] = len(analysis.get("yoy") or {})
        result["contract_completeness"] = {
            "has_qoq": contract.completeness.has_qoq,
            "has_yoy": contract.completeness.has_yoy,
            "missing_metrics": contract.completeness.missing_metrics,
        }
        result["score"] = state.get("score")
        result["llm_analysis_valid"] = state.get("llm_analysis_valid")
        result["persisted_id"] = persisted_id
        result["status"] = "ok"

        # Stage 10 - store the analysis in Qdrant (isolated so a
        # vector-store outage never loses the persisted analysis).
        try:
            vector = self._store_in_qdrant(symbol, state)
            result["vector_point_id"] = (
                vector.get("point_id") if vector else None
            )

        except Exception:
            logger.exception(
                "PIPELINE COMPANY | %s | stage: store_in_qdrant | "
                "status: failed (analysis already persisted)",
                symbol,
            )
            result["vector_point_id"] = None

        return result

    def _metrics_and_insights(self, symbol: str):
        analysis = self.analysis_service.compare_latest_results(symbol)
        insights = self.insight_service.analyze(analysis)

        self._stage_log(
            "metrics_and_insights",
            symbol=symbol,
            qoq_metrics=len(analysis.get("qoq") or {}),
            yoy_metrics=len(analysis.get("yoy") or {}),
            insights=sum(len(value) for value in insights.values()),
        )

        return analysis

    def _build_contract(self, symbol: str):
        contract = self.contract_service.build(symbol)

        self._stage_log(
            "build_contract",
            symbol=symbol,
            has_qoq=contract.completeness.has_qoq,
            has_yoy=contract.completeness.has_yoy,
            missing_metrics=len(contract.completeness.missing_metrics),
        )

        return contract

    def _run_ai_workflow(self, symbol: str):
        state = self.workflow.run(symbol)

        self._stage_log(
            "ai_workflow",
            symbol=symbol,
            status=state.get("status"),
            llm_analysis_valid=state.get("llm_analysis_valid"),
            score=state.get("score"),
        )

        return state

    def _persist_analysis(self, symbol: str, state: dict):
        persisted_id = state.get("persisted_id")

        self._stage_log(
            "persist_analysis",
            symbol=symbol,
            persisted_id=persisted_id,
            status=state.get("status"),
        )

        return persisted_id

    def _store_in_qdrant(self, symbol: str, state: dict):
        structured = state.get("structured_analysis")

        if not structured:
            self._stage_log(
                "store_in_qdrant",
                symbol=symbol,
                status="skipped",
                reason="no_structured_analysis",
            )
            return None

        latest = self.financial_repo.get_latest_result(symbol)
        seq_number = latest.seq_number if latest else None

        vector_service = self._get_vector_service()

        stored = vector_service.store_analysis(
            symbol=symbol,
            structured_analysis=structured,
            seq_number=seq_number,
            company_score=state.get("score"),
        )

        self._stage_log(
            "store_in_qdrant",
            symbol=symbol,
            point_id=stored.get("point_id"),
            score=stored.get("company_score"),
        )

        return stored

    def _get_vector_service(self):
        if self._vector_service is None:
            self._vector_service = VectorService(
                client=self.vector_client,
                embedding_provider=self.embedding_provider,
                collection_name=settings.QDRANT_COLLECTION_NAME,
            )

        return self._vector_service