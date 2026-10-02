"""Public release failures contain trusted stage/code constants, never payloads."""
from contextlib import contextmanager

from release_admission import strict_json

NODE_STAGES = frozenset({
    "node.preflight", "node.dependencies", "node.connector", "node.connect",
    "node.context", "node.sessions", "node.catalog-begin", "node.catalog-query",
    "node.catalog-validate", "node.catalog-rollback", "node.output", "node.cleanup",
    "node.disposal", "node.clean", "node.initialize", "node.postconditions",
})
SQL_READ_STAGES = frozenset({
    "google.sql-source-users-list", "google.sql-clone-users-list",
    "google.sql-source-instance-get", "google.sql-clone-instance-get",
    "google.sql-source-database-get", "google.sql-clone-database-get",
})
STAGES = NODE_STAGES | SQL_READ_STAGES | frozenset({
    "data.execute", "data.inputs", "data.admission", "data.plan", "data.receipt",
    "google.admission", "google.credentials-file", "google.credentials-validation",
    "google.credentials-load", "google.session", "google.project-request", "google.project-identity",
    "catalog.recipient", "catalog.metadata-request", "catalog.metadata-identity",
    "catalog.native-preflight", "catalog.native-execute", "catalog.native-result",
    "catalog.encryption", "catalog.receipt",
    "google.sql-initializer-user-create", "google.sql-initializer-operation-poll",
})
# Relevant PostgreSQL conditions only; arbitrary five-character codes can carry data.
SQLSTATES = frozenset({"08001", "08003", "08004", "08006", "08P01", "28000", "28P01",
                       "3D000", "42501", "53300", "53400", "55000", "57014", "57P01", "57P03"})


class HTTPFailure(ValueError):
    def __init__(self, status, *, read_stage=None):
        self.http_status = status if type(status) is int and 400 <= status <= 599 else None
        self.read_stage = read_stage if type(read_stage) is str and read_stage in SQL_READ_STAGES else None
        super().__init__("Google HTTP response rejected")


class DiagnosticError(ValueError):
    def __init__(self, stage, *, http_status=None, sqlstate=None):
        self.stage = stage if type(stage) is str and stage in STAGES else "data.execute"
        self.http_status = http_status if type(http_status) is int and 400 <= http_status <= 599 else None
        self.sqlstate = sqlstate if type(sqlstate) is str and sqlstate in SQLSTATES else None
        super().__init__(public_failure(self))


def public_failure(error):
    stage = error.stage if isinstance(error, DiagnosticError) and type(error.stage) is str and error.stage in STAGES else "data.execute"
    read_stage = getattr(error, "read_stage", None) if isinstance(error, HTTPFailure) else None
    if type(read_stage) is str and read_stage in SQL_READ_STAGES:
        stage = read_stage
    fields = ["stage=" + stage]
    status = getattr(error, "http_status", None) if isinstance(error, (DiagnosticError, HTTPFailure)) else None
    if type(status) is int and 400 <= status <= 599:
        fields.append("http_status=" + str(status))
    state = getattr(error, "sqlstate", None) if isinstance(error, DiagnosticError) else None
    if type(state) is str and state in SQLSTATES:
        fields.append("sqlstate=" + state)
    return "Data release blocked [" + "; ".join(fields) + "]."


@contextmanager
def http_stage(name):
    """Label only a native HTTP refusal; preserve existing non-HTTP exceptions."""
    allowed = {"google.sql-initializer-user-create", "google.sql-initializer-operation-poll"}
    try:
        yield
    except HTTPFailure as error:
        raise DiagnosticError(name if name in allowed else "data.execute", http_status=error.http_status) from None


@contextmanager
def stage(name):
    # A programmer typo cannot become public text supplied by an exception.
    name = name if type(name) is str and name in STAGES else "data.execute"
    try:
        yield
    except DiagnosticError:
        raise
    except Exception as error:
        status = error.http_status if isinstance(error, HTTPFailure) else None
        read_stage = getattr(error, "read_stage", None) if isinstance(error, HTTPFailure) else None
        if name == "data.execute" and type(read_stage) is str and read_stage in SQL_READ_STAGES:
            name = read_stage
        raise DiagnosticError(name, http_status=status) from None


def node_failure(stderr):
    """Parse only a complete bounded record; no substring or raw-output fallback."""
    fallback = DiagnosticError("catalog.native-execute")
    if type(stderr) is not bytes or len(stderr) > 256:
        return fallback
    try:
        value = strict_json(stderr)
        if (type(value) is not dict or set(value) not in ({"version", "stage"}, {"version", "stage", "sqlstate"})
                or value["version"] != "release-diagnostic/v1" or type(value["stage"]) is not str
                or value["stage"] not in NODE_STAGES
                or ("sqlstate" in value and (type(value["sqlstate"]) is not str or value["sqlstate"] not in SQLSTATES))):
            return fallback
        return DiagnosticError(value["stage"], sqlstate=value.get("sqlstate"))
    except Exception:
        return fallback
