class DomainError(Exception):
    """A refused business command. `code` is stable and maps to user-facing copy."""

    def __init__(self, code: str, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail
