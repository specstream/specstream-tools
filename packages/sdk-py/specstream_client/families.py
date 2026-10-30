"""Record kinds the service names today, from the finder.cross-source.v1 OpenAPI.

A record kind is an open string. FAMILIES lists the known kinds as examples; any
other non-empty kind name a reading gives is valid too.
"""

from __future__ import annotations

FAMILIES: tuple[str, ...] = (
    "local_business",
    "creator",
    "organization",
    "storefront_product",
    "app_listing",
    "job_posting",
    "scholarly_work",
    "tender",
    "grant",
    "software_repository",
    "software_package",
    "dataset",
    "clinical_trial",
    "regulatory_document",
    "vulnerability",
    "book",
    "podcast",
    "web_page",
    "knowledge_entity",
    "person",
)

FAMILY_SET = frozenset(FAMILIES)


def assert_family(entity_type: str) -> str:
    if not isinstance(entity_type, str) or not entity_type.strip():
        raise ValueError("entity_type must be a non-empty string")
    return entity_type
