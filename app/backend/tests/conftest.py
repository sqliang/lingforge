"""Test-wide environment defaults.

`lingforge.settings` instantiates at import time and requires secrets; tests that import
settings-dependent modules (agents, API) must see harmless placeholder values instead of
real credentials. `setdefault` keeps any real environment in control.
"""

import os

_DEFAULTS = {
    "SUPABASE_URL": "http://localhost:54321",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/postgres",
    "MODEL_API_KEY": "test-model-key",
    "MODEL_NAME": "test-model",
    "PREVIEW_TICKET_SECRET": "test-ticket-secret",
}

for _key, _value in _DEFAULTS.items():
    os.environ.setdefault(_key, _value)
