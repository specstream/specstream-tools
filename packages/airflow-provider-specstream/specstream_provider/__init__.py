"""SpecStream provider for Apache Airflow."""

__version__ = "0.1.0"


def get_provider_info() -> dict:
    """Read by Airflow through the apache_airflow_provider entry point."""
    return {
        "package-name": "airflow-provider-specstream",
        "name": "SpecStream",
        "description": "SpecStream is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.",
        "versions": [__version__],
        "connection-types": [
            {"connection-type": "specstream", "hook-class-name": "specstream_provider.hooks.specstream.SpecStreamHook"},
        ],
        "hook-class-names": ["specstream_provider.hooks.specstream.SpecStreamHook"],
        "operators": [
            {"integration-name": "SpecStream", "python-modules": ["specstream_provider.operators.specstream"]},
        ],
        "hooks": [
            {"integration-name": "SpecStream", "python-modules": ["specstream_provider.hooks.specstream"]},
        ],
        "integrations": [
            {"integration-name": "SpecStream", "external-doc-url": "https://specstream.ai/docs", "tags": ["service"]},
        ],
    }
