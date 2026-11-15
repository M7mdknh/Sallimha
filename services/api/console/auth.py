from rest_framework.authentication import SessionAuthentication


class CsrfSessionAuthentication(SessionAuthentication):
    """Same-origin session authentication; DRF enforces CSRF for authenticated unsafe requests."""
