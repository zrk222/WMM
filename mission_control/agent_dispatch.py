"""Scoped agent dispatch for the existing owner-approved publication service."""

AGENT_OPERATIONS = frozenset(
    {
        "publication.list",
        "publication.get",
        "publication.draft",
        "publication.prepare",
        "publication.execute",
    }
)


def dispatch(service, envelope, *, caller="SCOPED_AGENT"):
    """Agents may prepare and enqueue only; owner-only controls stay out of catalog."""
    from .operation_catalog import request_data
    from .publication_service import dispatch as publication_service_dispatch, list_publications

    request_data(envelope)
    operation = envelope["operation"]
    if caller != "SCOPED_AGENT" or operation not in AGENT_OPERATIONS:
        raise PermissionError("This publication action requires its owner-only route")
    app_id = envelope["app_id"]
    body = envelope["input"]
    from .operation_authority import protected

    with protected(service.store, envelope):
        if operation == "publication.list":
            return list_publications(service.store, app_id)
        if operation == "publication.get":
            from .publication_reports import report

            return report(service.store, app_id, body["id"])
        action = operation.removeprefix("publication.")
        return publication_service_dispatch(service.store, app_id, action, body)
