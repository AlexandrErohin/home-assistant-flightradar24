from typing import Any

from curl_cffi.requests.exceptions import Timeout

from ..const import CURL_TIMEOUT_CODE


def http_status(error: BaseException) -> int | None:
    """Return the HTTP status carried by *error*, or None if it carries none.

    curl_cffi raises HTTPError with the response attached, so the status is
    readable without matching on the message text. A status on the exception
    itself (legacy) is also accepted when it is an int.
    """
    code = getattr(error, 'status_code', None)
    if isinstance(code, int):
        return code
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    return status if isinstance(status, int) else None


def is_timeout(error: BaseException) -> bool:
    """True when the request ran into the HTTP timeout (curl error 28)."""
    return isinstance(error, Timeout) or getattr(error, 'code', None) == CURL_TIMEOUT_CODE


def is_login_auth_error(error: BaseException) -> bool:
    """True when login failed because credentials were rejected."""
    return http_status(error) in (401, 403)


def to_int(element: Any) -> None | int:
    if element is None:
        return None
    try:
        return int(element)
    except ValueError:
        return None


def to_float(element: Any) -> None | float:
    if element is None:
        return None
    try:
        return float(element)
    except ValueError:
        return None


def get_value(dictionary: dict, keys: list) -> Any | None:
    nested_dict = dictionary

    for key in keys:
        try:
            nested_dict = nested_dict[key]
        except Exception:
            return None
    return nested_dict
