from datetime import datetime


DATE_FORMAT = "%d-%b-%Y"

# ------------------------------------------------------------------
# Quarter / FY label — single canonical definition for the project.
# ------------------------------------------------------------------

# Mapping from calendar month to fiscal quarter number.
# Indian FY: Apr-Mar.  Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.
_QUARTER_BY_MONTH = {
    1: 4, 2: 4, 3: 4,
    4: 1, 5: 1, 6: 1,
    7: 2, 8: 2, 9: 2,
    10: 3, 11: 3, 12: 3,
}


def quarter_label(from_date: str, to_date: str) -> dict:
    """
    Derive a human-readable quarter / FY label from a period range.

    Returns
    -------
    dict with keys:
        quarter   e.g. "Q1"
        fy        e.g. "FY2026-27"
        label     e.g. "Q1 FY2026-27"
        from_date e.g. "01-Apr-2026"
        to_date   e.g. "30-Jun-2026"
        range     e.g. "01-Apr-2026 → 30-Jun-2026"

    The FY is the Indian financial year (Apr-Mar).  For Q4 the FY
    straddles two calendar years, e.g. Jan-Mar 2026 belongs to
    FY2025-26 even though ``to_date`` is in 2026.
    """

    try:
        to_dt = datetime.strptime(to_date, DATE_FORMAT)
    except (ValueError, TypeError):
        return {
            "quarter": "?",
            "fy": "?",
            "label": "?",
            "from_date": from_date,
            "to_date": to_date,
            "range": f"{from_date} → {to_date}",
        }

    q = _QUARTER_BY_MONTH.get(to_dt.month, 1)

    # FY start year: Apr-Dec belongs to that calendar year,
    # Jan-Mar belongs to the previous calendar year.
    if to_dt.month >= 4:
        fy_start = to_dt.year
    else:
        fy_start = to_dt.year - 1

    fy = f"FY{fy_start}-{str(fy_start + 1)[-2:]}"

    return {
        "quarter": f"Q{q}",
        "fy": fy,
        "label": f"Q{q} {fy}",
        "from_date": from_date,
        "to_date": to_date,
        "range": f"{from_date} → {to_date}",
    }


def get_quarter_dates(qe_date: str):
    date = datetime.strptime(qe_date, DATE_FORMAT)

    if date.month in (1, 2, 3):
        start_month = 1
        start_day = 1

    elif date.month in (4, 5, 6):
        start_month = 4
        start_day = 1

    elif date.month in (7, 8, 9):
        start_month = 7
        start_day = 1

    else:
        start_month = 10
        start_day = 1

    start_date = date.replace(
        month=start_month,
        day=start_day
    )

    return (
        start_date.strftime(DATE_FORMAT),
        date.strftime(DATE_FORMAT)
    )


def get_quarter_from_qe_date(qe_date):
    """
    Derive the quarter range (from_date, to_date) from a period-end
    date.

    Returns None when the period-end date is missing or invalid.
    """

    if not qe_date:
        return None

    try:
        return get_quarter_dates(qe_date)
    except ValueError:
        return None


def is_valid_period(from_date, to_date):
    """
    Return True when both period dates are present and valid.
    """

    if not from_date or not to_date:
        return False

    try:
        datetime.strptime(from_date, DATE_FORMAT)
        datetime.strptime(to_date, DATE_FORMAT)
        return True
    except ValueError:
        return False


def derive_period(raw_data):
    """
    Derive (from_date, to_date) for a filing from its raw data.

    Priority:
      1. valid fromDate / toDate in the raw data
      2. qe_Date (quarter period-end date)
      3. period

    The existing get_quarter_dates() logic is used so the derived
    quarter is always identical to what repository.create() would
    store. Returns None when no valid period can be derived.
    """

    if not raw_data:
        return None

    from_date = raw_data.get("fromDate")
    to_date = raw_data.get("toDate")

    if is_valid_period(from_date, to_date):
        return (from_date, to_date)

    qe_date = raw_data.get("qe_Date")

    if qe_date:
        period = get_quarter_from_qe_date(qe_date)

        if period is not None:
            return period

    period_value = raw_data.get("period")

    if period_value:
        period = get_quarter_from_qe_date(period_value)

        if period is not None:
            return period

    return None