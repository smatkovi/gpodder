# -*- coding: utf-8 -*-
#
# gPodder - A media aggregator and podcast client
# Copyright (c) 2005-2015 Thomas Perl and the gPodder Team
#
# gPodder is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# gPodder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Local HTTP relay so the media player can stream HTTPS episodes.

Harmattan's gstreamer-0.10 was built without SSL support: souphttpsrc
answers any https:// URI with "SSL support not available", so the QML
player cannot stream an episode even though gPodder itself downloads it
happily (see gpodder.tlsfix).

This module runs a small HTTP server bound to 127.0.0.1 with an ephemeral
port. Episodes are registered with register(url), which hands back a plain
http://127.0.0.1:<port>/<token> URL. A request to that URL is forwarded to
the real one through urllib2 -- which speaks TLS 1.2/1.3 thanks to tlsfix --
and the response is streamed back unencrypted over the loopback interface.
Range requests are passed through in both directions, so seeking keeps
working.

The server is started lazily on the first register() call and only listens
on the loopback interface.
"""

import os
import sys
import socket
import select
import logging
import threading
import urllib2
import urlparse
import hashlib

import BaseHTTPServer
import SocketServer

import gpodder

logger = logging.getLogger(__name__)

# Headers we copy from the client request to the upstream request
_FORWARD_REQUEST_HEADERS = ('range', 'if-range', 'if-modified-since',
                            'if-none-match')

# Headers we copy from the upstream response back to the client
_FORWARD_RESPONSE_HEADERS = ('content-type', 'content-length', 'content-range',
                             'accept-ranges', 'last-modified', 'etag')

_CHUNK_SIZE = 64 * 1024

# Only these schemes are ever relayed
_ALLOWED_SCHEMES = ('http', 'https')


class _Handler(BaseHTTPServer.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'gPodder-streamproxy'

    def log_message(self, format, *args):
        logger.debug('streamproxy: ' + format, *args)

    def _target(self):
        token = self.path.lstrip('/').split('?')[0]
        url = self.server.lookup(token)
        if url is None:
            self.send_error(404, 'Unknown stream')
            return None
        return url

    def _upstream(self, url):
        request = urllib2.Request(url)
        request.add_header('User-Agent', gpodder.user_agent)
        for header in _FORWARD_REQUEST_HEADERS:
            value = self.headers.getheader(header)
            if value is not None:
                request.add_header(header, value)
        return urllib2.urlopen(request, timeout=30)

    def _relay(self, body):
        try:
            response = self._upstream(self._url)
        except urllib2.HTTPError as error:
            # Pass the upstream status on, the player may know what to do
            logger.warn('streamproxy: upstream %s for %s', error.code,
                        self._url)
            try:
                self.send_response(error.code)
                self.send_header('Content-Length', '0')
                self.end_headers()
            except socket.error:
                pass
            return
        except Exception as error:
            logger.warn('streamproxy: cannot open %s: %s', self._url, error)
            try:
                self.send_error(502, 'Upstream error')
            except socket.error:
                pass
            return

        try:
            code = getattr(response, 'code', 200) or 200
            self.send_response(code)
            seen = set()
            for header in _FORWARD_RESPONSE_HEADERS:
                value = response.info().getheader(header)
                if value is not None:
                    self.send_header(header, value)
                    seen.add(header)
            if 'accept-ranges' not in seen:
                # gstreamer only offers seeking when it sees this
                self.send_header('Accept-Ranges', 'bytes')
            if 'content-length' not in seen:
                # Without a length we must close to signal the end
                self.send_header('Connection', 'close')
                self.close_connection = 1
            self.end_headers()

            if not body:
                return

            while True:
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except socket.error:
            # The player seeked or stopped; this is the normal way a
            # stream ends here, so do not make noise about it.
            self.close_connection = 1
        finally:
            try:
                response.close()
            except Exception:
                pass

    def do_GET(self):
        self._url = self._target()
        if self._url is not None:
            self._relay(True)

    def do_HEAD(self):
        self._url = self._target()
        if self._url is not None:
            self._relay(False)


class _Server(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address):
        BaseHTTPServer.HTTPServer.__init__(self, address, _Handler)
        self._streams = {}
        self._lock = threading.Lock()

    def add(self, token, url):
        with self._lock:
            self._streams[token] = url

    def lookup(self, token):
        with self._lock:
            return self._streams.get(token)

    def handle_error(self, request, client_address):
        # The default implementation prints a traceback for every player
        # disconnect, which happens constantly while seeking.
        exc_type = sys.exc_info()[0]
        if exc_type is socket.error:
            return
        logger.warn('streamproxy: request failed', exc_info=True)


_server = None
_server_lock = threading.Lock()


def _ensure_server():
    global _server
    with _server_lock:
        if _server is not None:
            return _server
        try:
            server = _Server(('127.0.0.1', 0))
        except socket.error as error:
            logger.warn('streamproxy: cannot listen: %s', error)
            return None
        thread = threading.Thread(target=server.serve_forever)
        thread.name = 'StreamProxy'
        thread.setDaemon(True)
        thread.start()
        _server = server
        logger.info('streamproxy: listening on port %d', server.server_port)
        return _server


def register(url):
    """Return a loopback http:// URL that relays the given URL.

    Returns the original URL unchanged if relaying is not needed (the URL
    is already plain http) or not possible (the server cannot be started).
    """
    if not url:
        return url

    scheme = urlparse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        return url
    if scheme != 'https':
        # Plain HTTP goes straight to the player
        return url
    if os.environ.get('GPODDER_NO_STREAM_PROXY'):
        return url

    server = _ensure_server()
    if server is None:
        return url

    token = hashlib.md5(url.encode('utf-8')).hexdigest()
    server.add(token, url)
    return 'http://127.0.0.1:%d/%s' % (server.server_port, token)


def port():
    """The port the relay listens on, or None if it is not running."""
    if _server is None:
        return None
    return _server.server_port
