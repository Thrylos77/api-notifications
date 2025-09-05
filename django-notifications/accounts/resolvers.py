# rbac/resolvers.py
"""
RBAC resolver for the notifications package.

This module registers a resolver for the "rbac" namespace.
The resolver transforms incoming targets (user / group / email) into
a list of concrete recipient dictionaries understood by the notifications system.

Resolver signature (as required by notifications.resolvers):
    resolver(target_type: str, identifier: str, meta: dict) -> List[Dict[str, Any]]

Each recipient dict must contain:
    - recipient_namespace (str)
    - recipient_identifier (str)
Optionally:
    - email (str | None)
    - channel (str | None)  # channel group name for WebSocket delivery
"""

import logging
from typing import List, Dict, Any

from notifications.resolvers import register_resolver

logger = logging.getLogger(__name__)


def accounts_resolver(target_type: str, identifier: str, meta: dict) -> List[Dict[str, Any]]:
    """
    Resolve RBAC targets into concrete recipients.

    - user: identifier is a user PK
    - group: identifier is a group PK (Group must expose a relation to users, e.g. `users`)
    - email: identifier is an e-mail address (fallback)
    - meta: optional dict provided at target creation (can be used to alter behavior)

    Note: imports are local to avoid startup import-order problems.
    """
    recipients: List[Dict[str, Any]] = []
    # normalize inputs
    ttype = (target_type or "").lower()
    ident = str(identifier)

    # ---------- user target ----------
    if ttype == "user":
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.filter(pk=ident).first()
            if not user:
                return []
            recipients.append({
                "recipient_namespace": "users",             # target namespace for resolved recipient
                "recipient_identifier": str(user.pk),      # recipient id as string
                "email": getattr(user, "email", None),     # optional email
                "channel": f"user_users_{user.pk}",        # channel/group name for websockets
            })
        except Exception as exc:
            logger.exception("rbac_resolver(user=%s) failed: %s", ident, exc)
            return []

        return recipients

    # ---------- group target ----------
    if ttype == "group":
        try:
            # import Group model locally to avoid circular imports at startup
            # try to fetch group and its users with a prefetch to avoid N+1
            # NB : user_set is used because it's the default related name for django Group
            from django.contrib.auth.models import Group  # adjust if Group model path differs
            group = Group.objects.prefetch_related("user_set").filter(pk=ident).first()
            if not group:
                return []

            for u in group.user_set.all():
                recipients.append({
                    "recipient_namespace": "users",
                    "recipient_identifier": str(u.pk),
                    "email": getattr(u, "email", None),
                    "channel": f"user_users_{u.pk}",
                })

        except Exception as exc:
            logger.exception("rbac_resolver(group=%s) failed: %s", ident, exc)
            return []

        return recipients

    # ---------- email fallback ----------
    if ttype == "email":
        # treat identifier as an email address
        return [{
            "recipient_namespace": "default",
            "recipient_identifier": ident,
            "email": ident,
            "channel": None,
        }]

    # ---------- unknown target type ----------
    logger.debug("rbac_resolver: unknown target_type=%s identifier=%s", ttype, ident)
    return []


def register():
    """
    Register the Accounts resolver under the 'accounts' namespace.
    Called from AppConfig.ready() in rbac/apps.py.
    """
    register_resolver("accounts", accounts_resolver)
    logger.info("Registered Accounts resolver for namespace 'accounts'")
