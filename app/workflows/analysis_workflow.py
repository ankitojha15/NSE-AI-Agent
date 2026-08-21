import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.repositories.analysis_result_repository import AnalysisResultRepository
from app.repositories.financial_result_repository import FinancialResultRepository
from app.schemas.ai_analysis import LLMAnalysisResult
from app.schemas.financial_analysis import FinancialAnalysisContract
from app.services.ai_analysis_service import AIAnalysisService
from app.services.financial_contract_service import FinancialAnalysisContractService


class AnalysisState(TypedDict):
    """
    Typed state for the financial analysis workflow.

    - symbol: the company being analyzed
    - data_available: whether any financial filings exist
    - contract: the validated financial data contract (None if unusable)
    - filing_data: filing metadata prepared for the LLM
    - structured_analysis: validated structured LLM output (None if invalid)
    - llm_analysis_valid: whether the LLM produced a valid structured result
    - llm_analysis: JSON text of the structured result (for persistence)
    - score: company score (LLM score, or rule-based fallback)
    - score_explanation: human-readable reason for the score
    - status: "completed" | "insufficient_data"
    - error: failure detail, if any
    - persisted_id: id of the saved analysis result row
    """

    symbol: str
    data_available: bool
    contract: FinancialAnalysisContract | None
    filing_data: dict
    structured_analysis: dict | None
    llm_analysis_valid: bool
    llm_analysis: str | None
    score: int | None
    score_explanation: str | None
    status: str
    error: str | None
    persisted_id: int | None


class AnalysisWorkflow:
    """
    LangGraph workflow for company financial analysis.

    Stages:
        1. load_financial_data   - check the company has filings
        2. build_contract        - build the FinancialAnalysisContract
        3. generate_llm_analysis - run the LLM over the contract
        4. generate_company_score - rule-based score from comparisons
        5. persist_analysis_result - save the result to the database

    When financial data is missing or insufficient, the workflow
    routes to handle_insufficient_data and records the shortfall
    instead of calling the LLM.
    """

    def __init__(self, db, contract_service=None, ai_service=None):
        self.db = db
        self.contract_service = (
            contract_service or FinancialAnalysisContractService(db)
        )
        self.financial_repo = FinancialResultRepository(db)
        self.result_repo = AnalysisResultRepository(db)
        self._ai_service = ai_service
        self._default_ai_service = None
        self.graph = self._build_graph()

    # ----------------------------------------------------------
    # AI service (lazy so tests never construct a live LLM)
    # ----------------------------------------------------------

    @property
    def ai_service(self):
        if self._ai_service is not None:
            return self._ai_service

        if self._default_ai_service is None:
            self._default_ai_service = AIAnalysisService()

        return self._default_ai_service

    # ----------------------------------------------------------
    # Stages
    # ----------------------------------------------------------

    def _load_financial_data(self, state: AnalysisState):
        history = self.financial_repo.get_company_history(state["symbol"])

        if not history:
            return {
                "data_available": False,
                "status": "insufficient_data",
            }

        return {"data_available": True}

    def _build_contract(self, state: AnalysisState):
        contract = self.contract_service.build(state["symbol"])

        if contract is None or not contract.completeness.has_latest:
            return {
                "contract": contract,
                "status": "insufficient_data",
            }

        return {"contract": contract, "status": "processing"}

    def _should_continue(self, state: AnalysisState):
        if state.get("status") == "insufficient_data":
            return "insufficient"

        return "sufficient"

    def _generate_llm_analysis(self, state: AnalysisState):
        contract = state["contract"]

        structured = self.ai_service.analyze_structured(contract)

        if structured is None:
            return {
                "structured_analysis": None,
                "llm_analysis_valid": False,
                "llm_analysis": None,
            }

        if isinstance(structured, LLMAnalysisResult):
            structured_dict = structured.model_dump()
            structured_json = structured.model_dump_json()
        elif isinstance(structured, dict):
            structured_dict = structured
            structured_json = json.dumps(structured)
        else:
            return {
                "structured_analysis": None,
                "llm_analysis_valid": False,
                "llm_analysis": None,
            }

        # --- Structured validation: LLM must not contradict contract ---
        # The contract is the source of truth for numeric facts. Strip
        # any LLM claim that a metric is "missing" when the contract
        # contains it, and ensure QoQ/YoY numbers always come from the
        # deterministic comparison.
        structured_dict = self._sanitize_llm_output(structured_dict, contract)

        # Re-serialize after sanitization so persisted llm_analysis is clean
        try:
            structured_json = json.dumps(structured_dict)
        except Exception:
            pass

        return {
            "structured_analysis": structured_dict,
            "llm_analysis_valid": True,
            "llm_analysis": structured_json,
        }

    @staticmethod
    def _sanitize_llm_output(structured: dict, contract) -> dict:
        """
        Remove LLM statements that contradict the FinancialAnalysisContract.

        The LLM is explanatory only — numeric truth comes from the contract.
        """
        if not structured or contract is None:
            return structured

        # Map contract latest snapshot field -> phrases that claim "missing"
        metric_phrases = {
            "sales": ["revenue missing", "sales missing", "revenue not available"],
            "revenue": ["revenue missing", "revenue not available"],
            "ebitda": ["ebitda missing", "ebitda not available", "ebitda unavailable"],
            "net_profit": ["net profit missing", "net profit not available", "profit missing"],
            "basic_eps": ["eps missing", "eps not available", "earnings per share missing"],
            "opm": ["opm missing", "operating margin missing"],
            "net_profit_margin": ["net profit margin missing"],
        }

        # Check latest snapshot for available metrics
        latest = getattr(contract, "latest", None)
        if latest is None:
            return structured

        sanitized = dict(structured)

        for metric, phrases in metric_phrases.items():
            val = getattr(latest, metric, None)
            if val is None:
                continue
            for field in ("summary", "growth_analysis", "margin_analysis",
                          "positive_factors", "negative_factors", "risk_factors"):
                items = sanitized.get(field)
                if items is None:
                    continue
                if isinstance(items, list):
                    clean = []
                    for item in items:
                        low = str(item).lower()
                        if any(p in low for p in phrases):
                            continue
                        clean.append(item)
                    sanitized[field] = clean
                elif isinstance(items, str):
                    low = items.lower()
                    if any(p in low for p in phrases):
                        sanitized[field] = ""

        return sanitized

    def _generate_company_score(self, state: AnalysisState):
        structured = state.get("structured_analysis")

        # Prefer the LLM's score only when it actually provided one;
        # otherwise use the deterministic rule-based score. This keeps
        # numeric facts deterministic regardless of LLM wording.
        if structured is not None and state.get("llm_analysis_valid"):
            llm_score = structured.get("company_score")
            llm_expl = structured.get("score_explanation")
            if llm_score is not None:
                return {"score": llm_score, "score_explanation": llm_expl}

        # Deterministic fallback (and now primary for user-facing).
        score, explanation = self._score_company(state["contract"])

        return {"score": score, "score_explanation": explanation}

    def _persist_analysis_result(self, state: AnalysisState):
        contract = state["contract"]

        record, _ = self.result_repo.save(
            symbol=state["symbol"],
            status="completed",
            contract_data=(
                contract.model_dump() if contract else None
            ),
            llm_analysis=state.get("llm_analysis"),
            score=state.get("score"),
            score_explanation=state.get("score_explanation"),
            error=state.get("error"),
        )

        return {"status": "completed", "persisted_id": record.id}

    def _handle_insufficient_data(self, state: AnalysisState):
        contract = state.get("contract")

        record, _ = self.result_repo.save(
            symbol=state["symbol"],
            status="insufficient_data",
            contract_data=(
                contract.model_dump() if contract else None
            ),
            error="Not enough valid quarterly financial data to analyze.",
        )

        return {
            "status": "insufficient_data",
            "persisted_id": record.id,
        }

    # ----------------------------------------------------------
    # Rule-based company score
    # ----------------------------------------------------------

    @staticmethod
    def _score_company(contract: FinancialAnalysisContract):
        """
        Deterministic 0-100 score based on QoQ / YoY comparisons.

        Positive/negative growth and margin changes add or subtract
        points. The result is clamped to the 0-100 range and is
        always reproducible for the same contract.
        """

        score = 50
        reasons = []

        growth_rules = [
            ("sales", 15, "revenue"),
            ("net_profit", 20, "net profit"),
            ("ebitda", 10, "EBITDA"),
            ("basic_eps", 10, "EPS"),
        ]

        for metric, weight, label in growth_rules:

            for block_name, block, factor in (
                ("YoY", contract.yoy, 1.0),
                ("QoQ", contract.qoq, 0.5),
            ):

                item = block.get(metric)

                if item is None or item.growth_percent is None:
                    continue

                growth = item.growth_percent

                if growth > 10:
                    score += weight * factor * 0.5
                    reasons.append(
                        f"{label} {block_name} up {growth:.1f}%"
                    )
                elif growth > 0:
                    score += weight * factor * 0.25
                    reasons.append(
                        f"{label} {block_name} up {growth:.1f}%"
                    )
                elif growth < -10:
                    score -= weight * factor * 0.5
                    reasons.append(
                        f"{label} {block_name} down {abs(growth):.1f}%"
                    )
                elif growth < 0:
                    score -= weight * factor * 0.25
                    reasons.append(
                        f"{label} {block_name} down {abs(growth):.1f}%"
                    )

        margin_rules = [
            ("opm", "operating margin"),
            ("net_profit_margin", "net profit margin"),
        ]

        for metric, label in margin_rules:

            item = contract.yoy.get(metric) or contract.qoq.get(metric)

            if item is None or item.change is None:
                continue

            if item.change > 0.5:
                score += 5
                reasons.append(
                    f"{label} improved {item.change:.2f} pp"
                )
            elif item.change < -0.5:
                score -= 5
                reasons.append(
                    f"{label} declined {abs(item.change):.2f} pp"
                )

        score = max(0, min(100, round(score)))

        if not reasons:
            reasons.append("No comparable periods available.")

        return score, "; ".join(reasons)

    # ----------------------------------------------------------
    # Graph construction
    # ----------------------------------------------------------

    def _build_graph(self):
        builder = StateGraph(AnalysisState)

        builder.add_node("load_financial_data", self._load_financial_data)
        builder.add_node("build_contract", self._build_contract)
        builder.add_node("generate_llm_analysis", self._generate_llm_analysis)
        builder.add_node("generate_company_score", self._generate_company_score)
        builder.add_node("persist_analysis_result", self._persist_analysis_result)
        builder.add_node("handle_insufficient_data", self._handle_insufficient_data)

        builder.add_edge(START, "load_financial_data")
        builder.add_edge("load_financial_data", "build_contract")

        builder.add_conditional_edges(
            "build_contract",
            self._should_continue,
            {
                "sufficient": "generate_llm_analysis",
                "insufficient": "handle_insufficient_data",
            },
        )

        builder.add_edge("generate_llm_analysis", "generate_company_score")
        builder.add_edge("generate_company_score", "persist_analysis_result")
        builder.add_edge("persist_analysis_result", END)
        builder.add_edge("handle_insufficient_data", END)

        return builder.compile()

    def run(self, symbol: str):
        """
        Run the full workflow for a company and return the final state.

        The initial state is fully typed so every field is present in
        the final result regardless of which branch was taken.
        """
        return self.graph.invoke(
            {
                "symbol": symbol,
                "data_available": False,
                "contract": None,
                "filing_data": {},
                "structured_analysis": None,
                "llm_analysis_valid": False,
                "llm_analysis": None,
                "score": None,
                "score_explanation": None,
                "status": "pending",
                "error": None,
                "persisted_id": None,
            }
        )