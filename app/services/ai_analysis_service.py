from langchain_groq import ChatGroq

from app.core.config import settings


class AIAnalysisService:
    """
    Uses an LLM to analyze structured financial data.
    """

    def __init__(self):
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            api_key=settings.GROQ_API_KEY
        )

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