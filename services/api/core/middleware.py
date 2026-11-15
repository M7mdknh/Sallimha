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
