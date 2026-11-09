"""Domain errors raised by services. app.main maps them to HTTP status codes,
so services stay independent of the web layer. Messages are safe to show."""


class ServiceError(Exception):
    """Base class. The message is safe to show to the user."""


class NotFoundError(ServiceError):
    """The resource does not exist, or belongs to someone else. The two are
    deliberately indistinguishable, so ids can't be probed across owners."""


class ConflictError(ServiceError):
    """The request clashes with current state (a taken slug, a shop that is live)."""


class ForbiddenError(ServiceError):
    """The user may see the resource but not do this to it."""


class InvalidInputError(ServiceError):
    """Input passed schema validation but breaks a business rule."""


class UnavailableError(ServiceError):
    """Something the request depends on (a model, an outside API) can't
    answer right now. Worth trying again later."""


class RateLimitedError(ServiceError):
    """The user hit a usage limit. `retry_after_s`, when known, becomes the
    Retry-After header."""

    def __init__(self, message: str, retry_after_s: int | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s
