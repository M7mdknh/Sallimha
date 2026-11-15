"""OpenAPI extensions for the console contract."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CsrfSessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "console.auth.CsrfSessionAuthentication"
    name = "sessionCookie"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid",
                "description": "Same-origin Django session; unsafe methods also need the X-CSRFToken header."}
