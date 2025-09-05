# notifications/resolvers.py
"""
Resolver registry for the notifications app.

- A resolver transforms a raw NotificationTarget (namespace, target_type, identifier, meta)
  into a list of concrete recipient dicts.

Resolver contract:
    resolver(target_type: str, identifier: str, meta: dict) -> List[Dict[str, Any]]

Each recipient dict must contain:
    - "recipient_namespace": str  # e.g. 'users' or 'default'
    - "recipient_identifier": str # e.g. user.pk as string or external id
Optional keys:
    - "email": str | None
    - "channel": str | None     # channel/group name to send WebSocket message to

Examples of returned recipient:
    {
        "recipient_namespace": "users",
        "recipient_identifier": "12",
        "email": "bob@example.com",
        "channel": "user_users_12"
    }

Design goals:
- Keep this module tiny and dependency-free so notifications package stays agnostic.
- Backends register resolvers for their namespace during AppConfig.ready().
"""

from typing import Callable, Dict, List, Any, Optional

# registry: namespace -> resolver function
_RESOLVER_REGISTRY: Dict[str, Callable[[str, str, dict], List[Dict[str, Any]]]] = {}


def register_resolver(namespace: str, func: Callable[[str, str, dict], List[Dict[str, Any]]]) -> None:
    """
    Register a resolver function for a given namespace.

    The resolver will be called as: func(target_type, identifier, meta)
    It must return a list of recipient dictionaries (see module docstring).
    """
    if not callable(func):
        raise TypeError("resolver must be callable")
    _RESOLVER_REGISTRY[namespace] = func


def get_resolver(namespace: str) -> Optional[Callable[[str, str, dict], List[Dict[str, Any]]]]:
    """Return the resolver registered for `namespace`, or None if none exists."""
    return _RESOLVER_REGISTRY.get(namespace)


def unregister_resolver(namespace: str) -> None:
    """Remove a resolver from the registry (useful for tests)."""
    _RESOLVER_REGISTRY.pop(namespace, None)


def list_registered_namespaces() -> List[str]:
    """Return a list of all registered namespaces."""
    return list(_RESOLVER_REGISTRY.keys())


# --------------------------
# Helper: safe resolver caller
# --------------------------
def resolve_target(namespace: str, target_type: str, identifier: str, meta: Optional[dict] = None) -> List[Dict[str, Any]]:
    """
    Resolve a single target using the resolver for `namespace`.
    - Returns an empty list if no resolver is registered.
    - Ensures returned recipient dicts contain required keys and normalizes types.
    """
    meta = meta or {}
    resolver = get_resolver(namespace)
    if resolver is None:
        # No resolver registered for this namespace -> nothing to do
        return []

    # Call resolver and validate output
    raw_recipients = []
    try:
        raw_recipients = resolver(target_type, identifier, meta) or []
    except Exception:
        # Protect caller from resolver exceptions; log externally if needed
        # Resolvers should be well-behaved; failing resolver => no recipients
        return []

    recipients: List[Dict[str, Any]] = []
    for r in raw_recipients:
        # validate minimal contract
        if not isinstance(r, dict):
            continue
        rn = r.get("recipient_namespace") or namespace
        rid = r.get("recipient_identifier")
        # If resolver forgot to set recipient_identifier, try to coerce from identifier
        if rid is None:
            rid = str(identifier)
        recipients.append({
            "recipient_namespace": str(rn),
            "recipient_identifier": str(rid),
            "email": r.get("email"),
            "channel": r.get("channel"),
        })
    return recipients


def resolve_targets_batch(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convenience to resolve many raw targets (like NotificationTarget rows).
    Each `target` in `targets` must be a dict containing at least:
        - 'namespace', 'target_type', 'identifier', optional 'meta'
    Returns a flat list of recipient dicts (normalized).
    """
    results: List[Dict[str, Any]] = []
    for t in targets:
        ns = t.get("namespace", "default")
        ttype = t.get("target_type")
        ident = t.get("identifier")
        meta = t.get("meta", {}) or {}
        if ttype is None or ident is None:
            continue
        results.extend(resolve_target(ns, ttype, str(ident), meta))
    return results


# --------------------------
# Default resolver for 'default' namespace
# --------------------------
def _default_resolver(target_type: str, identifier: str, meta: dict) -> List[Dict[str, Any]]:
    """
    Minimal default resolver that understands:
      - target_type == 'email'  -> returns a single recipient with given email
      - target_type == 'external' -> returns a single recipient with identifier as external id
    This resolver does NOT import project models and is safe as a fallback.
    Backends should register their own resolver for more advanced resolution.
    """
    if target_type == "email":
        return [{
            "recipient_namespace": "default",
            "recipient_identifier": str(identifier),
            "email": str(identifier),
            "channel": None,
        }]
    if target_type == "external":
        # external IDs are opaque; let downstream systems handle them
        return [{
            "recipient_namespace": "external",
            "recipient_identifier": str(identifier),
            "email": None,
            "channel": None,
        }]
    # Not recognized by default resolver => no recipients
    return []


# register built-in default resolver
register_resolver("default", _default_resolver)


# --------------------------
# Example: decorator helper for backend use (optional)
# --------------------------
def resolver_for(namespace: str):
    """
    Decorator to register a resolver function for a namespace.

    Usage in a backend app:
        @resolver_for('rbac')
        def rbac_resolver(target_type, identifier, meta):
            ...
            return recipients_list
    """
    def _decorator(func: Callable[[str, str, dict], List[Dict[str, Any]]]):
        register_resolver(namespace, func)
        return func
    return _decorator
