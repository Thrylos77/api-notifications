# WebSocket consumer for real-time notifications
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "notification"
        # Join to group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave the group
        await self.channel_layer.group_discard(
            self.group_name, 
            self.channel_name
        )

    # Receive message from websocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        # Handle incoming messages here
        message = data.get("message", "")

        event = {
            "type": "send_notification",
            "message": message
        }
        # Send message to the group
        await self.channel_layer.group_send(self.group_name, event)

    async def send_notification(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({
            "message": message
        }))