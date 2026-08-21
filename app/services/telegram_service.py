"""
Telegram notification service for the NSE AI pipeline.

Sends a readable summary message for every company whose financial
analysis completes successfully. The bot token and chat id come from
configuration and are never logged.
"""

from datetime import datetime, timezone

import requests
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.telegram_notification import TelegramNotification
from app.utils.logger import logger
from app.utils.quarter_utils import quarter_label

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096

METRIC_LABELS = {
    "sales": "Revenue/Sales",
    "revenue": "Revenue/Sales",
    "ebitda": "EBITDA",
    "operating_profit": "Operating Profit",
    "net_profit": "Net Profit",
    "basic_eps": "EPS",
    "diluted_eps": "Diluted EPS",
    "opm": "OPM (%)",
    "net_profit_margin": "Net Profit Margin (%)",
}

FINANCIAL_LABELS = {
    "sales": "Revenue/Sales",
    "revenue": "Revenue/Sales",
    "ebitda": "EBITDA",
    "net_profit": "Net Profit",
    "basic_eps": "EPS",
    "opm": "OPM",
    "net_profit_margin": "Net Profit Margin",
}

# LLM phrases that contradict available structured data.
# Each entry: (metric key, trigger phrases that claim "missing/unknown")
MISSING_PHRASES = {
    "sales": ["revenue missing", "sales missing", "revenue not available", "sales not available",
              "revenue unavailable", "sales unavailable", "revenue data missing", "no revenue data"],
    "revenue": ["revenue missing", "revenue not available", "revenue unavailable"],
    "ebitda": ["ebitda missing", "ebitda not available", "ebitda unavailable"],
    "net_profit": ["net profit missing", "net profit not available", "net profit unavailable", "profit missing"],
    "basic_eps": ["eps missing", "eps not available", "eps unavailable", "earnings per share missing"],
    "opm": ["opm missing", "operating margin missing", "opm not available"],
    "net_profit_margin": ["net profit margin missing", "net profit margin not available"],
}


def _fmt_number(value):
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _fmt_percent(value):
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def _fmt_pts(value):
    if value is None:
        return "n/a"
    return f"{value:+.2f} pts"


def _sanitize_llm_fields(structured: dict, analysis: dict) -> dict:
    """
    Remove LLM claims that contradict the structured contract.

    The contract is the source of truth for numeric facts. If the LLM
    says a metric is missing but the contract contains it, that claim
    is stripped. QoQ/YoY values are never taken from the LLM — they
    always come from FinancialAnalysisService.
    """
    if not structured:
        return structured

    sanitized = dict(structured)
    latest = (analysis or {}).get("latest") or {}

    for metric_key, phrases in MISSING_PHRASES.items():
        if latest.get(metric_key) is None:
            continue
        for field in ("summary", "growth_analysis", "margin_analysis",
                      "positive_factors", "negative_factors", "risk_factors"):
            val = sanitized.get(field)
            if val is None:
                continue
            if isinstance(val, list):
                clean = []
                for item in val:
                    lower = str(item).lower()
                    if any(p in lower for p in phrases):
                        continue
                    clean.append(item)
                sanitized[field] = clean
            elif isinstance(val, str):
                lower = val.lower()
                if any(p in lower for p in phrases):
                    sanitized[field] = ""

    return sanitized


def _filing_identity(symbol: str, analysis: dict) -> str:
    """
    Stable identity for dedup: symbol + seq when available,
    otherwise symbol + period range.
    """
    seq = (analysis or {}).get("latest_seq")
    if seq:
        return str(seq)
    periods = (analysis or {}).get("periods") or {}
    latest = periods.get("latest") or {}
    from_d = latest.get("from")
    to_d = latest.get("to")
    if from_d and to_d:
        return f"{from_d}→{to_d}"
    # Ultimate fallback (should not happen for eligible companies)
    return f"{symbol}-unknown"


class TelegramService:
    """
    Sends company analysis summaries to Telegram.

    Safe by design:
    - Disabled (no-op) when the bot token or chat id is missing.
    - Every send is wrapped so an API error or timeout is caught and
      logged, never raised to the caller.
    - The bot token never appears in log output.
    - Duplicate notifications for the same filing are prevented using
      (symbol, filing_identity) in telegram_notifications.
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        db=None,
        post=None,
    ):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.db = db
        self._post = post or self._default_post

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    # ----------------------------------------------------------
    # HTTP layer (injectable for tests)
    # ----------------------------------------------------------

    def _default_post(self, url, json, timeout=10):
        response = requests.post(url, json=json, timeout=timeout)
        response.raise_for_status()
        return response

    def _send_message(self, text: str):
        url = f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage"

        response = self._post(
            url,
            {"chat_id": self.chat_id, "text": text},
        )

        data = response.json()
        return data.get("result", {}).get("message_id")

    # ----------------------------------------------------------
    # Duplicate prevention — filing identity, not content hash
    # ----------------------------------------------------------

    def _is_duplicate(self, symbol: str, filing_identity: str) -> bool:
        if self.db is None:
            return False

        existing = (
            self.db.query(TelegramNotification)
            .filter(
                TelegramNotification.symbol == symbol,
                TelegramNotification.filing_identity == filing_identity,
            )
            .first()
        )

        return existing is not None

    def _record_sent(self, symbol: str, filing_identity: str):
        if self.db is None:
            return

        row = TelegramNotification(symbol=symbol, filing_identity=filing_identity)
        self.db.add(row)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    # ----------------------------------------------------------
    # Message building — periods, no AI score, deterministic facts
    # ----------------------------------------------------------

    def _build_message(
        self,
        symbol: str,
        analysis: dict,
        structured_analysis: dict,
    ) -> str:
        # Sanitize LLM contradictions against contract truth
        structured_analysis = _sanitize_llm_fields(structured_analysis or {}, analysis or {})

        qoq = analysis.get("qoq") or {}
        yoy = analysis.get("yoy") or {}
        latest = analysis.get("latest") or {}
        periods = analysis.get("periods") or {}

        latest_p = periods.get("latest")
        prev_p = periods.get("previous")
        yoy_p = periods.get("yoy")

        # Reporting period block
        lines = []
        lines.append(f"📊 NSE AI Analysis | {symbol}")
        lines.append("")

        if latest_p and latest_p.get("from") and latest_p.get("to"):
            ql = quarter_label(latest_p["from"], latest_p["to"])
            lines.append("📅 Reporting Period")
            lines.append(f"{ql['label']}")
            lines.append(f"{ql['range']}")
        elif latest_p:
            lines.append("📅 Reporting Period")
            lines.append(f"{latest_p.get('from', '?')} → {latest_p.get('to', '?')}")
        else:
            latest_raw = analysis.get("latest_raw_data") or {}
            fd = latest_raw.get("fromDate") or "?"
            td = latest_raw.get("toDate") or latest_raw.get("qe_Date") or "?"
            lines.append("📅 Reporting Period")
            lines.append(f"{fd} → {td}")
        lines.append("")

        # QoQ
        lines.append("📈 QoQ")
        if latest_p and prev_p and latest_p.get("from") and prev_p.get("from"):
            cl = quarter_label(latest_p["from"], latest_p["to"])
            pl = quarter_label(prev_p["from"], prev_p["to"])
            lines.append(f"Current: {cl['label']} ({cl['range']})")
            lines.append(f"Previous: {pl['label']} ({pl['range']})")
        elif qoq:
            lines.append("Current vs Previous Quarter")
        if qoq:
            lines.append("")
            lines.extend(self._metric_lines(qoq))
        else:
            if not (latest_p and prev_p):
                lines.append("  Not available (no consecutive quarter)")
            else:
                lines.append("  Not available")
        lines.append("")

        # YoY
        lines.append("📉 YoY")
        if latest_p and yoy_p and latest_p.get("from") and yoy_p.get("from"):
            cl = quarter_label(latest_p["from"], latest_p["to"])
            yl = quarter_label(yoy_p["from"], yoy_p["to"])
            lines.append(f"Current: {cl['label']} ({cl['range']})")
            lines.append(f"Previous Year: {yl['label']} ({yl['range']})")
        elif yoy:
            lines.append("Current vs Same Quarter Last Year")
        if yoy:
            lines.append("")
            lines.extend(self._metric_lines(yoy))
        else:
            # Distinguish "no YoY data at all" from "YoY lookup exhausted"
            if analysis.get("yoy_search_exhausted"):
                reason = analysis.get("yoy_search_reason") or "historical filing not found after search"
                lines.append(f"  Not available — {reason}")
            else:
                lines.append("  Not available")
        lines.append("")

        # Financials — exact period
        if latest_p and latest_p.get("from"):
            ql = quarter_label(latest_p["from"], latest_p["to"])
            lines.append(f"💰 Financials — {ql['label']}")
        else:
            lines.append("💰 Financials")
        lines.extend(self._financial_lines(latest))
        lines.append("")

        positive = structured_analysis.get("positive_factors") or []
        negative = structured_analysis.get("negative_factors") or []
        risks = structured_analysis.get("risk_factors") or []

        lines.append("✅ Positive Factors")
        lines.extend(self._bullet_lines(positive))
        lines.append("")

        lines.append("⚠️ Negative Factors")
        lines.extend(self._bullet_lines(negative))
        lines.append("")

        lines.append("🛡️ Risk Factors")
        lines.extend(self._bullet_lines(risks))

        return "\n".join(lines)

    def _metric_lines(self, metrics: dict):
        lines = []

        for key, item in metrics.items():
            if not isinstance(item, dict):
                continue

            label = METRIC_LABELS.get(key, key)
            latest = item.get("latest")
            previous = item.get("previous")

            if "growth_percent" in item:
                detail = _fmt_percent(item.get("growth_percent"))
            elif "change" in item:
                detail = _fmt_pts(item.get("change"))
            else:
                detail = ""

            lines.append(
                f"• {label}: {_fmt_number(latest)} vs "
                f"{_fmt_number(previous)} ({detail})"
            )

        return lines

    def _financial_lines(self, latest: dict):
        lines = []

        for key, label in FINANCIAL_LABELS.items():
            if key in latest and latest[key] is not None:
                lines.append(f"• {label}: {_fmt_number(latest[key])}")

        return lines or ["  Not available"]

    def _bullet_lines(self, items: list):
        if not items:
            return ["  None"]

        return [f"• {item}" for item in items]

    # ----------------------------------------------------------
    # Message splitting (Telegram 4096-char limit)
    # ----------------------------------------------------------

    @staticmethod
    def _split_message(message: str, limit: int = MAX_MESSAGE_LENGTH):
        if len(message) <= limit:
            return [message]

        parts = []
        current = ""

        for line in message.splitlines():
            if len(line) > limit:
                if current:
                    parts.append(current)
                    current = ""
                for offset in range(0, len(line), limit):
                    parts.append(line[offset:offset + limit])
                continue

            if current and len(current) + 1 + len(line) > limit:
                parts.append(current)
                current = ""

            current = f"{current}\n{line}" if current else line

        if current:
            parts.append(current)

        return parts

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def send_analysis_notification(
        self,
        symbol: str,
        analysis: dict | None = None,
        structured_analysis: dict | None = None,
        score: int | None = None,
    ):
        """
        Send the analysis summary for one company.

        ``score`` is accepted for backwards compat but ignored — the
        Telegram message no longer contains an AI score.

        Returns a status dict. Never raises: any failure is caught and
        logged so the caller's analysis stays successful.
        """

        analysis = analysis or {}
        structured_analysis = structured_analysis or {}

        if not self.enabled:
            logger.info(
                "TELEGRAM NOTIFY | symbol: %s | status: skipped | "
                "reason: not_configured",
                symbol,
            )
            return {"status": "skipped", "symbol": symbol}

        # Filing identity for dedup (stable across LLM wording changes)
        filing_id = _filing_identity(symbol, analysis)

        try:
            if self._is_duplicate(symbol, filing_id):
                logger.info(
                    "TELEGRAM NOTIFY | symbol: %s | status: duplicate | filing: %s",
                    symbol,
                    filing_id,
                )
                return {"status": "duplicate", "symbol": symbol}
        except Exception:
            logger.warning(
                "TELEGRAM NOTIFY | symbol: %s | dedup check failed",
                symbol,
                exc_info=True,
            )

        # Deterministic message: facts from contract, commentary from LLM
        # (sanitized against contradictions).
        message = self._build_message(symbol, analysis, structured_analysis)

        parts = self._split_message(message)

        try:
            for part in parts:
                self._send_message(part)
        except Exception as exc:
            logger.error(
                "TELEGRAM NOTIFY | symbol: %s | status: failed | "
                "error: %s",
                symbol,
                type(exc).__name__,
                exc_info=True,
            )
            return {"status": "failed", "symbol": symbol}

        try:
            self._record_sent(symbol, filing_id)
        except Exception:
            logger.warning(
                "TELEGRAM NOTIFY | symbol: %s | dedup record failed",
                symbol,
                exc_info=True,
            )

        logger.info(
            "TELEGRAM NOTIFY | symbol: %s | status: sent | "
            "parts: %d | chars: %d | filing: %s",
            symbol,
            len(parts),
            len(message),
            filing_id,
        )

        return {
            "status": "sent",
            "symbol": symbol,
            "parts": len(parts),
            "chars": len(message),
        }
