# Environments and configuration

Local, test, staging, and production use the same validated settings schema with environment-specific values/secrets. Maintain a configuration inventory with owner, sensitivity, rotation/reload, default, and environment requirement.

Staging mirrors production topology/policies at smaller scale and uses synthetic or approved test data. No production secret/data is copied to lower environments. Feature flags have lifecycle metadata and are observable. Effective non-secret configuration/version fingerprint appears in health/release evidence.
