"""Import-safe iOS contract inventory; discovery never asserts native readiness."""
from copy import deepcopy

from .common import digest
from .operation_catalog import OPERATIONS


NATIVE_REQUIREMENTS = (
    'embedded_python', 'protected_storage', 'keychain', 'local_identity',
    'scoped_authority', 'media_intake', 'timeline_renderer', 'local_studio',
    'provider_transport', 'local_scheduler', 'reports', 'accessible_navigation',
)


def inventory():
    """Preserve every current shared operation without inventing an iOS mapping."""
    value = {
        'schema': 'growth.ios-capability-inventory.v1',
        'transport': 'IN_PROCESS_JSON',
        'execution_authority': False,
        'native_acceptance': 'NOT_RUN',
        'full_parity': False,
        'required_native_adapters': list(NATIVE_REQUIREMENTS),
        'operations': deepcopy(OPERATIONS),
        'operation_count': len(OPERATIONS),
        'mapping_state': 'NATIVE_IMPLEMENTATION_REQUIRED',
        'denied': ['shell_execution', 'downloaded_executable_code',
                   'desktop_companion_requirement', 'agent_self_approval'],
    }
    return dict(value, inventory_sha256=digest(value))
