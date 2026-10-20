"""CARMA — WebSocket Consumer for live experiment log streaming."""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

User = get_user_model()


class ExperimentLogConsumer(AsyncWebsocketConsumer):
    """
    WebSocket endpoint: /ws/experiments/<run_id>/logs/
    Streams audit log entries in real time as the experiment runs.
    JWT token expected in query string: ?token=<access_token>
    """

    async def connect(self):
        # Authenticate via token in query string
        token_key = self._get_token()
        if not await self._authenticate(token_key):
            await self.close(code=4001)
            return

        self.run_id    = self.scope['url_route']['kwargs']['run_id']
        self.group_name = f'run_{self.run_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(json.dumps({
            'type':    'connected',
            'run_id':  self.run_id,
            'message': 'Streaming experiment logs.',
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Clients don't send anything — read-only stream
        pass

    async def experiment_log(self, event):
        """Receives from channel layer and forwards to WebSocket client."""
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
