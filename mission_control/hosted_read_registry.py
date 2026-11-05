"""Startup-owned client services; HTTP callers never choose database paths."""
from dataclasses import dataclass
import os
from pathlib import Path
import stat
from types import MappingProxyType

from .common import Invalid, identifier


class RegistryUnavailable(RuntimeError):
    """A provisioned file changed; no request may initialize its replacement."""


def exact_id(value):
    if identifier(value) != value:
        raise Invalid('Use an exact identifier')
    return value


def physical_file(path, root):
    """Reject linked components before resolving an existing regular file."""
    original = Path(path).absolute()
    try:
        # Windows legacy 8.3 names can differ from the resolved private root.
        # Inspect links on the original path, then compare canonical paths.
        for current in (*reversed(original.parents), original):
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise RegistryUnavailable('Client registry file is unavailable')
        resolved = original.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise RegistryUnavailable('Client registry file is unavailable')
        info = resolved.stat()
        return resolved, (info.st_dev, info.st_ino)
    except (OSError, ValueError) as exc:
        raise RegistryUnavailable('Client registry file is unavailable') from exc


@dataclass(frozen=True)
class Entry:
    tenant_id: str
    client_id: str
    path: Path
    identity: tuple
    service: object


class Registry:
    def __init__(self, root, services, control_path):
        self.root = Path(root).absolute()
        if (self.root.is_symlink() or not self.root.is_dir()
                or getattr(self.root.lstat(), 'st_file_attributes', 0) & 0x400):
            raise RegistryUnavailable('Private root is unavailable')
        self.root = self.root.resolve(strict=True)
        control, control_identity = physical_file(control_path, self.root)
        identities, paths, entries = {control_identity}, {os.path.normcase(str(control))}, {}
        for key, service in services.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise Invalid('Register exact tenant and client identifiers')
            tenant, client = map(exact_id, key)
            path, identity = physical_file(service.store.path, self.root)
            normalized = os.path.normcase(str(path))
            if identity in identities or normalized in paths:
                raise Invalid('Client databases must be distinct')
            identities.add(identity)
            paths.add(normalized)
            entries[key] = Entry(tenant, client, path, identity, service)
        self.entries = MappingProxyType(entries)

    def resolve(self, tenant, client):
        entry = self.entries[(tenant, client)]
        self.check(entry)
        return entry

    def check(self, entry):
        path, identity = physical_file(entry.path, self.root)
        service_path, service_identity = physical_file(entry.service.store.path, self.root)
        if (path != entry.path or identity != entry.identity
                or service_path != entry.path or service_identity != entry.identity
                or self.entries.get((entry.tenant_id, entry.client_id)) is not entry):
            raise RegistryUnavailable('Client registry binding changed')
