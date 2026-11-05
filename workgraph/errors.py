class WorkgraphError(Exception):
    """A stable, machine-readable error, with optional recovery context."""

    def __init__(self, code, message, details=None):
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def as_dict(self):
        return {"error": self.code, "message": str(self), "details": self.details}
