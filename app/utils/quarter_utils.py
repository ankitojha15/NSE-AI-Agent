from datetime import datetime


def get_quarter_dates(qe_date: str):
    date = datetime.strptime(qe_date, "%d-%b-%Y")

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
        start_date.strftime("%d-%b-%Y"),
        date.strftime("%d-%b-%Y")
    )