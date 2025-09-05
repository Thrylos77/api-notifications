# notifications/realtime/consumers.py
"""
WebSocket consumer for user notifications.

- On connect: require authenticated user, join a per-user channel group.
- The group name follows the pattern: "user_users_<user_id>" by default (matches example resolvers).
- Incoming client messages are ignored or can be used for ping/pong; server sends events with type 'send_notification'.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # the user should be populated by AuthMiddlewareStack
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            # reject anonymous connections
            await self.close()
            return

        # define channel group name convention used by resolvers
        # Example resolver used "user_users_<id>" — keep that naming for compatibility
        self.group_name = f"user_users_{user.pk}"

        # join the per-user group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # leave group on disconnect only if group_name exists
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Optionally handle messages from client.
        For now, we ignore client-sent payloads or echo simple heartbeats.
        """
        try:
            data = json.loads(text_data)
        except Exception:
            return

        # Example: support a 'ping' -> 'pong'
        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

    async def send_notification(self, event):
        """
        Handler for group_send events with type 'send_notification'.
        'event' should contain a 'message' payload that is JSON-serializable.
        """
        message = event.get("message", {})
        await self.send(text_data=json.dumps({
            "type": "notification",
            "payload": message
        }))
