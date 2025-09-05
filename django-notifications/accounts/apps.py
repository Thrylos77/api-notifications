from django.apps import AppConfig

import logging
logger = logging.getLogger(__name__)

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        """
        Register resolver(s) for the notifications package when the app is ready.
        Keep this light-weight; heavy imports are inside the resolver function itself.
        """
        try:
            from .resolvers import register
            register()
            logger.debug("Accounts: resolver registration complete")
        except Exception as exc:
            logger.exception("rbac: failed to register resolver: %s", exc)