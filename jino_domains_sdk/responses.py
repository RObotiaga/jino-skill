"""Recognize explicit legacy failures without disclosing server messages."""
import json

from .exceptions import OperationRejectedError


def check_legacy(result):
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return
    if result is False:
        raise OperationRejectedError("Jino rejected the operation.")
    if isinstance(result, dict):
        if (result.get("errors") or result.get("error") or result.get("success") is False
                or result.get("status") in ("error", "failed")):
            raise OperationRejectedError("Jino returned operation errors.")
        for key, item in result.items():
            operation = key.startswith(("add", "update", "del", "reset", "set", "enable", "disable", "request"))
            if isinstance(item, (dict, str)) or item is False and operation:
                check_legacy(item)
