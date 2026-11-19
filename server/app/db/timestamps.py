from datetime import UTC, datetime


def timestamp(moment: datetime | None = None) -> str:
    """The one format every stored timestamp uses: YYYY-MM-DDTHH:MM:SS.sssZ."""
    if moment is None:
        moment = datetime.now(UTC)
    elif moment.tzinfo is None:
        raise ValueError("timestamp needs a timezone-aware datetime")
    moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
