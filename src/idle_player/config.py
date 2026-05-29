"""Load and validate configuration.

Reads credentials and settings from environment (.env) and an optional
config.yaml. Credentials are never hardcoded. Exposes a validated config
object consumed by the rest of the package.
"""
