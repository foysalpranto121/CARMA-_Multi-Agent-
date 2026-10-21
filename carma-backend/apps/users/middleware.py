"""CARMA — Request Logging Middleware"""
import time
import logging

log = logging.getLogger('carma')

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # Only log API calls
        if request.path.startswith('/api/'):
            user = getattr(request, 'user', None)
            uid  = str(user.id) if user and user.is_authenticated else 'anon'
            log.info(
                '%s %s -> %s [%sms] user=%s ip=%s',
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                uid,
                self._get_ip(request),
            )
        return response

    @staticmethod
    def _get_ip(request):
        fwd = request.META.get('HTTP_X_FORWARDED_FOR')
        return fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR', '')
