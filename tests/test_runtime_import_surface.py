"""Regression guard for runtime split/import integrity.

These imports must remain valid after Drive/Dropbox DEV-SYNC operations.
The test intentionally imports the public runtime composition points only.
"""

def test_runtime_import_surface():
    from core.runtime import Runtime  # noqa: F401
    from core.runtime_ops import RuntimeOps  # noqa: F401
    from core.runtime_process import RuntimeProcess  # noqa: F401
    from core.rp_context import RPContextMixin  # noqa: F401
    from core.rp_lifecycle import RPLifecycleMixin  # noqa: F401
