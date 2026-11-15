import re
import uuid

from core.context import correlation_id

_VALID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Correlation-ID", "")
        value = incoming if _VALID.match(incoming) else uuid.uuid4().hex
        token = correlation_id.set(value)
        try:
            response = self.get_response(request)
        finally:
            correlation_id.reset(token)
        response["X-Correlation-ID"] = value
        return response


class ServiceUnavailableMiddleware:
    """Database unavailable → 503 with a stable code; never a false success (AT-31). The failed command's
    transaction rolled back, so nothing was stored and the client may retry with the same Idempotency-Key."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        import logging

        from django.db import InterfaceError, OperationalError
        from django.http import JsonResponse

        if isinstance(exception, OperationalError | InterfaceError):
            logging.getLogger(__name__).error("database unavailable: %s", type(exception).__name__)
            return JsonResponse({"code": "service_unavailable"}, status=503)
        return None
