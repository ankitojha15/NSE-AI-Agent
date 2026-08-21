import json
import re

from langchain_groq import ChatGroq

from app.core.config import settings
from app.schemas.ai_analysis import LLMAnalysisResult
from app.schemas.financial_analysis import FinancialAnalysisContract
from app.utils.logger import logger


class AIAnalysisService:
    """
    Uses the configured Groq LLM (Step 0) to analyze structured
    financial data.

    analyze_structured produces a Pydantic-validated LLMAnalysisResult
    based only on the provided FinancialAnalysisContract.
    """

    def __init__(self, llm=None, cerebras_llm=None):
        self.llm = llm or ChatGroq(
            model=settings.GROQ_MODEL,
            temperature=0.0,
            api_key=settings.GROQ_API_KEY
        )
        # Injected Cerebras mock for tests, or None for lazy real client
        self._cerebras_llm = cerebras_llm
        self._cerebras_instance = None
        self.last_provider_used: str | None = None
        self.last_error: Exception | None = None

    @property
    def cerebras_llm(self):
        if self._cerebras_llm is not None:
            return self._cerebras_llm
        if self._cerebras_instance is not None:
            return self._cerebras_instance
        if not settings.CEREBRAS_API_KEY:
            return None
        try:
            from langchain_openai import ChatOpenAI

            self._cerebras_instance = ChatOpenAI(
                model=settings.CEREBRAS_MODEL,
                api_key=settings.CEREBRAS_API_KEY,
                base_url="https://api.cerebras.ai/v1",
                temperature=0.0,
            )
            return self._cerebras_instance
        except Exception as e:
            logger.warning(f"Failed to init Cerebras client: {e}")
            return None

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        # Do not treat auth errors as rate limits
        msg = str(exc).lower()
        # Auth errors must not trigger fallback (401/403)
        if "authentication" in msg and "429" not in msg:
            if "401" in msg or "403" in msg or "invalid api key" in msg or "api_key" in msg:
                return False
        cname = type(exc).__name__.lower()
        if "authenticationerror" in cname or "permissiondenied" in cname:
            return False
        # Check status_code attribute (groq / google APIs)
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 429:
            return True
        if "ratelimit" in cname:
            return True
        if "429" in msg or "rate limit" in msg or "too many requests" in msg or "quota exceeded" in msg or "resource_exhausted" in msg:
            # Ensure not auth masquerading as rate limit
            if "401" in msg or "403" in msg:
                return False
            return True
        return False

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        cname = type(exc).__name__.lower()
        if "authenticationerror" in cname or "unauthenticated" in cname:
            return True
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return True
        if "401" in msg or "403" in msg or "invalid api key" in msg or "authentication" in msg:
            # If also 429, treat as rate limit not auth (rate limit check takes precedence)
            if "429" not in msg:
                return True
        return False

    def prepare_filing_data(self, raw_data: dict):

        return {
            "company_name": raw_data.get("companyName"),
            "symbol": raw_data.get("symbol"),
            "isin": raw_data.get("isin"),
            "industry": raw_data.get("industry"),
            "financial_year": raw_data.get("financialYear"),
            "period": raw_data.get("period"),
            "relating_to": raw_data.get("relatingTo"),
            "audited": raw_data.get("audited"),
            "consolidated": raw_data.get("consolidated"),
            "result_description": raw_data.get("resultDescription"),
        }

    def analyze(self, company_data: dict):

        prompt = f"""
    You are a professional financial research analyst.

    Analyze the financial information provided below.

    Your analysis must be based ONLY on the information provided.

    There are three levels of information:

    1. FACT
    Information directly supported by the provided data.

    2. INTERPRETATION
    A reasonable conclusion that can be derived from
    the provided facts.

    3. UNKNOWN
    Information that cannot be determined from the data.

    IMPORTANT RULES:

    - Never invent facts.
    - Never invent financial numbers.
    - Never invent management plans.
    - Never assume a reason for a financial change unless
    evidence for that reason is provided.
    - If the cause of a change is not available, explicitly
    say that the cause cannot be determined from the
    provided data.
    - Do not present assumptions as facts.
    - Clearly distinguish facts from interpretation.
    - Do not make guaranteed future predictions.
    - Do not provide investment advice.

    ==============================
    FINANCIAL INFORMATION
    ==============================

    {company_data}

    ==============================
    ANALYSIS
    ==============================

    1. COMPANY OVERVIEW

    Provide a company overview only if reliable company
    information is available in the provided data.

    Otherwise say:

    "Company overview information is not available
    in the provided data."

    2. LATEST QUARTER

    Explain the latest financial performance using
    the actual numbers provided.

    Discuss:
    - Sales
    - EBITDA
    - Operating profit
    - Net profit
    - EPS
    - Operating margin
    - Net profit margin

    3. QoQ ANALYSIS

    Compare the latest quarter with the previous quarter.

    Identify:
    - Major increases
    - Major decreases
    - Margin changes
    - Important profitability changes

    Explain what these changes indicate.

    Do not invent reasons for the changes.

    4. YoY ANALYSIS

    Compare the latest quarter with the same quarter
    of the previous year.

    Identify:
    - Revenue/sales growth
    - EBITDA growth
    - Operating profit growth
    - Net profit growth
    - EPS growth
    - Margin changes

    Explain what these changes indicate.

    5. PROFITABILITY

    Analyze:
    - EBITDA
    - Operating profit
    - Net profit
    - EPS
    - Operating margin
    - Net profit margin

    Explain whether profitability is improving,
    declining, or mixed.

    6. KEY POSITIVE FACTORS

    List the strongest positive developments supported
    by the financial data.

    7. KEY NEGATIVE FACTORS

    List the important negative developments supported
    by the financial data.

    8. MANAGEMENT / FUTURE PLANS

    Discuss management plans ONLY if they are explicitly
    available in the provided information.

    If they are not available, say so.

    9. POTENTIAL FUTURE IMPACT

    Discuss possible future implications only when they
    can reasonably be connected to the provided facts.

    Use cautious language such as:

    "could support..."
    "may indicate..."
    "could create pressure..."
    "the impact will depend on..."

    Do not make precise future financial predictions.

    10. RISKS

    Identify risks that are supported by the available
    information.

    If a risk is only a possibility, clearly state that
    it is a potential risk rather than a confirmed fact.

    11. OVERALL ASSESSMENT

    Provide a balanced conclusion.

    Mention:
    - Major strengths
    - Major weaknesses
    - Important uncertainties

    Do not give a buy/sell/hold recommendation.
    """


        response = self.llm.invoke(prompt)

        return response.content

    # ----------------------------------------------------------
    # Structured analysis
    # ----------------------------------------------------------

    @staticmethod
    def _extract_json_content(content: str):
        """
        Extract a JSON payload from an LLM response.

        Tolerates markdown code fences and surrounding whitespace.
        """

        if content is None:
            return None

        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        return cleaned.strip()

    def _build_structured_prompt(self, contract: FinancialAnalysisContract):
        contract_json = contract.model_dump_json()

        return f"""
    You are a professional financial research analyst.

    Analyze the financial data below. The data is a
    FinancialAnalysisContract.

    STRICT RULES:
    - Base your analysis ONLY on the data provided in the contract.
    - NEVER invent financial numbers, metrics, reasons, events or
    plans that are not present in the data.
    - If a metric or comparison is unavailable, state that it is
    unavailable.
    - Do NOT recalculate growth percentages, margin changes, period
    dates, or financial values — use ONLY the numbers in the contract.
    - Do NOT claim a metric is missing when the contract contains it.
    - Your role is qualitative commentary only; all numeric facts come
    from the contract.
    - Do not provide investment advice.
    - Do not make future predictions.

    The contract contains:
    - latest: the latest quarter metrics (in crore, except EPS per-share)
    - previous / same_quarter_last_year: the comparison periods
    - qoq / yoy: per-metric comparisons with growth_percent
    (absolute metrics) or change (margin metrics) — use these directly
    - periods: validated reporting period ranges with exact dates
    - completeness: which data is present or missing

    Respond with ONLY a single JSON object using exactly this schema:
    {{
      "summary": "2-3 sentence summary of the quarter",
      "positive_factors": ["..."],
      "negative_factors": ["..."],
      "growth_analysis": ["..."],
      "margin_analysis": ["..."],
      "risk_factors": ["..."]
    }}

    Do NOT include any score or numeric recalculation fields.

    FINANCIAL CONTRACT (JSON):
    {contract_json}

    JSON OUTPUT:
    """

    def analyze_structured(
        self,
        contract: FinancialAnalysisContract
    ) -> LLMAnalysisResult | None:
        """
        Generate a validated structured analysis for a contract.

        Primary: Groq. On HTTP 429 rate/quota error, falls back once to
        Cerebras with the identical prompt and validation. Other errors
        (auth, validation, programming) do not trigger fallback.

        Returns None when the LLM response is invalid/malformed or when
        both providers are rate-limited/billing-blocked so callers can
        fall back to deterministic rule-based analysis and still deliver
        QoQ/YoY on Telegram. Only auth/programming errors outside
        rate-limits raise.
        """

        prompt = self._build_structured_prompt(contract)
        self.last_provider_used = None
        self.last_error = None

        # ---- Primary: Groq ----
        try:
            response = self.llm.invoke(prompt)

            content = self._extract_json_content(
                getattr(response, "content", None)
            )

            if not content:
                return None

            result = LLMAnalysisResult.model_validate_json(content)
            self.last_provider_used = "groq"
            return result

        except Exception as exc:
            # Rate/quota -> try Cerebras once, do not retry Groq
            if self._is_rate_limit_error(exc):
                logger.warning(
                    f"GROQ RATE LIMIT | symbol={contract.symbol} | error={exc} | falling back to Cerebras ({settings.CEREBRAS_MODEL})"
                )
                self.last_error = exc
                cerebras = self.cerebras_llm
                if cerebras is None:
                    logger.warning(f"Cerebras fallback not configured (missing CEREBRAS_API_KEY) | symbol={contract.symbol} | using rule-based fallback")
                    return None
                try:
                    response2 = cerebras.invoke(prompt)
                    content2 = self._extract_json_content(
                        getattr(response2, "content", None)
                    )
                    if not content2:
                        logger.error("Cerebras returned empty content")
                        raise ValueError("Cerebras empty response")
                    result2 = LLMAnalysisResult.model_validate_json(content2)
                    self.last_provider_used = "cerebras"
                    logger.info(f"CEREBRAS FALLBACK SUCCESS | symbol={contract.symbol}")
                    return result2
                except Exception as exc2:
                    # Cerebras failed (rate-limit, billing 402, validation) -> graceful fallback to rule-based
                    if isinstance(exc2, (ValueError, TypeError, json.JSONDecodeError)):
                        logger.warning(f"Cerebras structured validation failed, using rule-based fallback | symbol={contract.symbol} | error={exc2}")
                    else:
                        logger.warning(f"Cerebras fallback also failed, using rule-based fallback | symbol={contract.symbol} | error={exc2} | groq_error={exc}")
                    self.last_error = exc2
                    # Return None so workflow uses deterministic score and still completes (QoQ/YoY delivered)
                    return None
            # Auth errors must not fallback
            if self._is_auth_error(exc):
                logger.error(f"GROQ AUTH ERROR (no fallback) | symbol={contract.symbol} | error={exc}")
                raise
            # Validation / programming errors -> safe None, no fallback
            if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError)):
                return None
            # Other unexpected errors -> propagate (no fallback, company failed)
            raise