from datetime import datetime
from zoneinfo import ZoneInfo


def get_current_time(timezone_name: str | None = None) -> str:
    """
    Return the current time in the given timezone, or the system local time if none is provided.    
    """
    try:
        if timezone_name:
            current_time = datetime.now(ZoneInfo(timezone_name))
        else:
            current_time = datetime.now().astimezone()
        return current_time.strftime("%d %B %Y, %I:%M %p")
    except Exception:
        return datetime.now().strftime("%d %B %Y, %I:%M %p")
