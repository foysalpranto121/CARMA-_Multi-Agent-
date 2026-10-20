"""CARMA — WebSocket consumer for real-time review notifications."""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class ReviewConsumer(AsyncWebsocketConsumer):
    """
    WebSocket: /ws/reviews/
    Pushes new escalation notifications to connected reviewers.
    """
    GROUP_NAME = 'review_queue'

    async def connect(self):
        token_key = self._get_token()
        if not await self._authenticate(token_key):
            await self.close(code=4001)
            return
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)
        await self.accept()
        await self.send(json.dumps({'type': 'connected', 'message': 'Review queue live.'}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass  # read-only push stream

    async def review_notification(self, event):
        await self.send(text_data=json.dumps(event['data']))

    def _get_token(self):
        qs = self.scope.get('query_string', b'').decode()
        for part in qs.split('&'):
            if part.startswith('token='):
                return part[6:]
        return None

    @database_sync_to_async
    def _authenticate(self, token_key):
        if not token_key:
            return False
        try:
            UntypedToken(token_key)
            return True
        except (InvalidToken, TokenError):
            return False
