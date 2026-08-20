from datetime import datetime


DATE_FORMAT = "%d-%b-%Y"


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