"""Exceptions raised by :mod:`jino_domains_sdk`."""


class JinoError(RuntimeError):
    """Base class for SDK errors."""
    code = "JINO_ERROR"


class AuthenticationError(JinoError):
    """The login form did not establish an authenticated control-panel session."""
    code = "AUTH_REQUIRED"

    def __init__(self, message: str, *, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable


class ProtocolError(JinoError):
    code = "UPSTREAM_FORMAT_CHANGED"


class NotFoundError(JinoError):
    code = "NOT_FOUND"


class OperationRejectedError(JinoError):
    code = "UPSTREAM_REJECTED"


class PartialUpdateError(JinoError):
    code = "PARTIAL_UPDATE"

    def __init__(self, steps: dict, cause: Exception):
        super().__init__("Settings update stopped; inspect the completed steps before retrying.")
        self.steps = steps
        self.cause = cause


class JinoHTTPError(JinoError):
    """A direct HTTP request returned an unsuccessful response."""

    def __init__(self, status: int, message: str):
        super().__init__(f"Jino returned HTTP {status}: {message}")
        self.status = status
        self.code = "RATE_LIMITED" if status == 429 else "PERMISSION_DENIED" if status == 403 else "HTTP_ERROR"


class JinoGraphQLError(JinoError):
    """GraphQL returned one or more operation errors."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("Jino returned GraphQL operation errors.")

    code = "GRAPHQL_ERROR"
