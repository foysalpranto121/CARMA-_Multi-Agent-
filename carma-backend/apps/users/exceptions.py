"""CARMA — Custom exception handler"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

log = logging.getLogger('carma')

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        # Normalize all error responses to { detail, errors, code }
        if isinstance(response.data, dict):
            if 'detail' not in response.data:
                response.data = {
                    'detail': 'Validation error.',
                    'errors': response.data,
                    'code':   response.status_code,
                }
        elif isinstance(response.data, list):
            response.data = {
                'detail': 'Validation error.',
                'errors': response.data,
                'code':   response.status_code,
            }
    else:
        # Unhandled exception → 500
        log.exception('Unhandled exception in view: %s', exc)
        response = Response(
            {'detail': 'An internal server error occurred.', 'code': 500},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
