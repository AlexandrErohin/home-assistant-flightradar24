from typing import Any


def to_int(element: Any) -> None | int:
    if element is None:
        return None
    try:
        return int(element)
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
