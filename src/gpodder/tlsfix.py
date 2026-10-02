# -*- coding: utf-8 -*-
#
# tlsfix - modern TLS for gPodder on MeeGo Harmattan (Python 2.6)
#
# The stock Python 2.6 "_ssl" module on Harmattan is linked against
# OpenSSL 0.9.8 and only speaks TLS 1.0 without SNI; practically no
# podcast host accepts that any more.  This module drives a newer
# libssl (1.1.1, TLS 1.2/1.3) through ctypes and replaces
# httplib.HTTPSConnection.connect, which is the one place every HTTPS
# path in gPodder (urllib2, urllib.FancyURLopener, feedparser,
# mygpoclient) goes through.  If no newer libssl is found, nothing is
# changed.
#
# Licensed under the GNU GPL v3 or later, like the rest of gPodder.

import os
import sys
import socket
import select
import ctypes
import logging

logger = logging.getLogger(__name__)

# Candidate libraries, newest first.  The first pair that loads wins.
_CANDIDATES = (
    ('/opt/wunderw/lib/libcrypto.so.1.1', '/opt/wunderw/lib/libssl.so.1.1'),
    ('libcrypto.so.1.1', 'libssl.so.1.1'),
)

# share/gpodder/ca-bundle.crt relative to the installed package dir
# (<prefix>/lib/pythonX.Y/dist-packages/gpodder), with the Harmattan
# optification paths as fallbacks.
_HERE = os.path.dirname(os.path.realpath(__file__))
_CA_CANDIDATES = (
    os.path.join(_HERE, '..', '..', '..', '..', 'share', 'gpodder', 'ca-bundle.crt'),
    os.path.join(_HERE, '..', '..', 'share', 'gpodder', 'ca-bundle.crt'),
    '/opt/gpodder/share/gpodder/ca-bundle.crt',
    '/usr/share/gpodder/ca-bundle.crt',
)
_CA_BUNDLE = None
for _p in _CA_CANDIDATES:
    if os.path.exists(_p):
        _CA_BUNDLE = os.path.normpath(_p)
        break
del _p

# OpenSSL constants
SSL_ERROR_WANT_READ = 2
SSL_ERROR_WANT_WRITE = 3
SSL_ERROR_SYSCALL = 5
SSL_ERROR_ZERO_RETURN = 6
SSL_CTRL_MODE = 33
SSL_CTRL_SET_TLSEXT_HOSTNAME = 55
TLSEXT_NAMETYPE_host_name = 0
SSL_MODE_ENABLE_PARTIAL_WRITE = 0x1
SSL_MODE_ACCEPT_MOVING_WRITE_BUFFER = 0x2
SSL_VERIFY_NONE = 0
SSL_VERIFY_PEER = 1

try:
    from ssl import SSLError
except ImportError:
    class SSLError(socket.error):
        pass

_crypto = None
_ssl = None
_ctx = None
_verify = True


def _load():
    global _crypto, _ssl
    for crypto_path, ssl_path in _CANDIDATES:
        try:
            crypto = ctypes.CDLL(crypto_path, mode=ctypes.RTLD_LOCAL,
                                 use_errno=True)
            lib = ctypes.CDLL(ssl_path, mode=ctypes.RTLD_LOCAL,
                              use_errno=True)
        except OSError:
            continue
        # Make sure this really is a 1.1-style library
        if not hasattr(lib, 'TLS_client_method'):
            continue
        _crypto, _ssl = crypto, lib
        return True
    return False


def _declare():
    c_void_p, c_int, c_long, c_char_p = (ctypes.c_void_p, ctypes.c_int,
                                         ctypes.c_long, ctypes.c_char_p)
    s, c = _ssl, _crypto
    s.TLS_client_method.restype = c_void_p
    s.SSL_CTX_new.restype = c_void_p
    s.SSL_CTX_new.argtypes = [c_void_p]
    s.SSL_CTX_ctrl.restype = c_long
    s.SSL_CTX_ctrl.argtypes = [c_void_p, c_int, c_long, c_void_p]
    s.SSL_CTX_set_verify.restype = None
    s.SSL_CTX_set_verify.argtypes = [c_void_p, c_int, c_void_p]
    s.SSL_CTX_load_verify_locations.restype = c_int
    s.SSL_CTX_load_verify_locations.argtypes = [c_void_p, c_char_p, c_char_p]
    s.SSL_CTX_set_default_verify_paths.restype = c_int
    s.SSL_CTX_set_default_verify_paths.argtypes = [c_void_p]
    s.SSL_new.restype = c_void_p
    s.SSL_new.argtypes = [c_void_p]
    s.SSL_free.restype = None
    s.SSL_free.argtypes = [c_void_p]
    s.SSL_set_fd.restype = c_int
    s.SSL_set_fd.argtypes = [c_void_p, c_int]
    s.SSL_ctrl.restype = c_long
    s.SSL_ctrl.argtypes = [c_void_p, c_int, c_long, c_void_p]
    s.SSL_set1_host.restype = c_int
    s.SSL_set1_host.argtypes = [c_void_p, c_char_p]
    s.SSL_connect.restype = c_int
    s.SSL_connect.argtypes = [c_void_p]
    s.SSL_read.restype = c_int
    s.SSL_read.argtypes = [c_void_p, c_void_p, c_int]
    s.SSL_write.restype = c_int
    s.SSL_write.argtypes = [c_void_p, c_char_p, c_int]
    s.SSL_shutdown.restype = c_int
    s.SSL_shutdown.argtypes = [c_void_p]
    s.SSL_get_error.restype = c_int
    s.SSL_get_error.argtypes = [c_void_p, c_int]
    s.SSL_get_verify_result.restype = c_long
    s.SSL_get_verify_result.argtypes = [c_void_p]
    s.SSL_get_version.restype = c_char_p
    s.SSL_get_version.argtypes = [c_void_p]
    s.SSL_get_current_cipher.restype = c_void_p
    s.SSL_get_current_cipher.argtypes = [c_void_p]
    s.SSL_CIPHER_get_name.restype = c_char_p
    s.SSL_CIPHER_get_name.argtypes = [c_void_p]
    c.ERR_get_error.restype = ctypes.c_ulong
    c.ERR_clear_error.restype = None
    c.ERR_error_string_n.restype = None
    c.ERR_error_string_n.argtypes = [ctypes.c_ulong, c_char_p, ctypes.c_size_t]
    c.X509_verify_cert_error_string.restype = c_char_p
    c.X509_verify_cert_error_string.argtypes = [c_long]
    c.OpenSSL_version.restype = c_char_p
    c.OpenSSL_version.argtypes = [c_int]


def _make_context():
    global _verify
    ctx = _ssl.SSL_CTX_new(_ssl.TLS_client_method())
    if not ctx:
        raise SSLError('SSL_CTX_new failed')
    _ssl.SSL_CTX_ctrl(ctx, SSL_CTRL_MODE,
                      SSL_MODE_ENABLE_PARTIAL_WRITE |
                      SSL_MODE_ACCEPT_MOVING_WRITE_BUFFER, None)
    if os.environ.get('GPODDER_TLS_NOVERIFY'):
        _verify = False
    elif _CA_BUNDLE is not None:
        if not _ssl.SSL_CTX_load_verify_locations(ctx, _CA_BUNDLE, None):
            logger.warn('tlsfix: could not load %s, trying system paths',
                        _CA_BUNDLE)
            _ssl.SSL_CTX_set_default_verify_paths(ctx)
    else:
        logger.warn('tlsfix: no ca-bundle.crt found, trying system paths')
        _ssl.SSL_CTX_set_default_verify_paths(ctx)
    if _verify:
        _ssl.SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, None)
    else:
        _ssl.SSL_CTX_set_verify(ctx, SSL_VERIFY_NONE, None)
    return ctx


def _openssl_errors():
    msgs = []
    while True:
        code = _crypto.ERR_get_error()
        if not code:
            break
        buf = ctypes.create_string_buffer(256)
        _crypto.ERR_error_string_n(code, buf, 256)
        msgs.append(buf.value)
    return msgs


def _is_ip(host):
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, host)
            return True
        except (socket.error, ValueError):
            pass
    return False


class TLSSocket(socket.socket):
    """A socket.socket wrapped by libssl 1.1 via ctypes.

    Implements the subset of ssl.SSLSocket that httplib/urllib use.
    """

    def __init__(self, sock, server_hostname):
        socket.socket.__init__(self, _sock=sock._sock)
        # socket.__init__ installs delegates that bypass us; put ours back
        self.send = lambda data, flags=0: TLSSocket.send(self, data, flags)
        self.sendto = lambda *a, **k: TLSSocket.sendto(self, *a, **k)
        self.recv = lambda buflen=1024, flags=0: TLSSocket.recv(self, buflen, flags)
        self.recv_into = lambda buf, nbytes=0, flags=0: TLSSocket.recv_into(self, buf, nbytes, flags)
        self.recvfrom = lambda *a, **k: TLSSocket.recvfrom(self, *a, **k)
        self.recvfrom_into = lambda *a, **k: TLSSocket.recvfrom_into(self, *a, **k)
        self._makefile_refs = 0
        self._ssl = None
        self.server_hostname = server_hostname

        ssl = _ssl.SSL_new(_ctx)
        if not ssl:
            raise SSLError('SSL_new failed: %s' % '; '.join(_openssl_errors()))
        self._ssl = ssl
        if not _ssl.SSL_set_fd(ssl, self.fileno()):
            raise SSLError('SSL_set_fd failed')
        if server_hostname and not _is_ip(server_hostname):
            name = ctypes.c_char_p(server_hostname)
            _ssl.SSL_ctrl(ssl, SSL_CTRL_SET_TLSEXT_HOSTNAME,
                          TLSEXT_NAMETYPE_host_name, name)
            if _verify:
                _ssl.SSL_set1_host(ssl, server_hostname)
        self._handshake()

    # -- low level ---------------------------------------------------------

    def _wait(self, want):
        timeout = self.gettimeout()
        fd = self.fileno()
        if want == SSL_ERROR_WANT_READ:
            r, w, x = select.select([fd], [], [], timeout)
        else:
            r, w, x = select.select([], [fd], [], timeout)
        if not r and not w:
            raise socket.timeout('timed out')

    def _error(self, what):
        msgs = _openssl_errors()
        if self._ssl is not None:
            vr = _ssl.SSL_get_verify_result(self._ssl)
            if vr:
                msgs.append('certificate verify failed: %s' %
                            _crypto.X509_verify_cert_error_string(vr))
        if not msgs:
            msgs.append('unknown error')
        return SSLError('%s: %s' % (what, '; '.join(msgs)))

    def _do(self, what, func, *args):
        if self._ssl is None:
            raise SSLError('%s on closed TLS socket' % what)
        while True:
            _crypto.ERR_clear_error()
            ret = func(self._ssl, *args)
            if ret > 0:
                return ret
            err = _ssl.SSL_get_error(self._ssl, ret)
            if err in (SSL_ERROR_WANT_READ, SSL_ERROR_WANT_WRITE):
                self._wait(err)
                continue
            if err == SSL_ERROR_ZERO_RETURN:
                return 0
            if err == SSL_ERROR_SYSCALL:
                errno = ctypes.get_errno()
                if ret == 0 and errno == 0:
                    # peer closed without close_notify
                    return 0
                if errno:
                    raise socket.error(errno, os.strerror(errno))
            raise self._error(what)

    def _handshake(self):
        if self._do('handshake', _ssl.SSL_connect) == 0:
            raise self._error('handshake')

    def _free(self):
        if self._ssl is not None:
            ssl, self._ssl = self._ssl, None
            try:
                _ssl.SSL_shutdown(ssl)
            except Exception:
                pass
            _ssl.SSL_free(ssl)

    # -- socket-like API ---------------------------------------------------

    def read(self, len=1024):
        buf = ctypes.create_string_buffer(len)
        n = self._do('read', _ssl.SSL_read, buf, len)
        return buf.raw[:n]

    def write(self, data):
        return self._do('write', _ssl.SSL_write, data, len(data))

    def recv(self, buflen=1024, flags=0):
        return self.read(buflen)

    def recv_into(self, buffer, nbytes=None, flags=0):
        if not nbytes:
            nbytes = len(buffer)
        data = self.read(nbytes)
        buffer[:len(data)] = data
        return len(data)

    def recvfrom(self, *args, **kwargs):
        raise socket.error('recvfrom not allowed on TLS socket')

    def recvfrom_into(self, *args, **kwargs):
        raise socket.error('recvfrom_into not allowed on TLS socket')

    def send(self, data, flags=0):
        return self.write(data)

    def sendto(self, *args, **kwargs):
        raise socket.error('sendto not allowed on TLS socket')

    def sendall(self, data, flags=0):
        total = len(data)
        sent = 0
        while sent < total:
            sent += self.write(data[sent:])
        return None

    def makefile(self, mode='r', bufsize=-1):
        self._makefile_refs += 1
        return socket._fileobject(self, mode, bufsize)

    def unwrap(self):
        self._free()
        return self

    def shutdown(self, how):
        self._free()
        socket.socket.shutdown(self, how)

    def close(self):
        if self._makefile_refs < 1:
            self._free()
            socket.socket.close(self)
        else:
            self._makefile_refs -= 1

    def __del__(self):
        self._free()

    def cipher(self):
        if self._ssl is None:
            return None
        c = _ssl.SSL_get_current_cipher(self._ssl)
        return (_ssl.SSL_CIPHER_get_name(c), _ssl.SSL_get_version(self._ssl), None)

    def getpeercert(self, binary_form=False):
        return {}


def wrap_socket(sock, server_hostname=None, **kwargs):
    return TLSSocket(sock, server_hostname)


def _https_connect(self):
    sock = socket.create_connection((self.host, self.port), self.timeout)
    self.sock = TLSSocket(sock, self.host)


# Qt (PySide) loads OpenSSL lazily by soname "1.0.0".  On devices with
# OpenSSL 1.0.2 in /usr/local/lib that library gets bound against the
# OpenSSL 0.9.8 that is already linked into the python binary itself, and
# the process dies with SIGSEGV as soon as Qt touches SSL.  Loading the
# 1.0.2 pair first with RTLD_DEEPBIND keeps its symbols bound to itself;
# Qt's later dlopen() finds the already-loaded sonames and reuses them.
_QT_OPENSSL = ('/usr/local/lib/libcrypto.so.1.0.0',
               '/usr/local/lib/libssl.so.1.0.0')
_RTLD_DEEPBIND = 0x8
_qt_pinned = []


def pin_qt_openssl():
    if _qt_pinned:
        return True
    for path in _QT_OPENSSL:
        if not os.path.exists(path):
            return False
    try:
        for path in _QT_OPENSSL:
            _qt_pinned.append(ctypes.CDLL(path, mode=_RTLD_DEEPBIND))
    except OSError as e:
        logger.warn('tlsfix: could not pin Qt OpenSSL: %s', e)
        del _qt_pinned[:]
        return False
    logger.info('tlsfix: pinned %s for Qt (RTLD_DEEPBIND)', _QT_OPENSSL[1])
    return True


def install():
    """Patch httplib so that HTTPS uses the newer libssl. Returns a
    description string, or None if nothing was done."""
    global _ctx
    if _ctx is not None:
        return _crypto.OpenSSL_version(0)
    if not os.environ.get('GPODDER_NO_QT_SSL_PIN'):
        pin_qt_openssl()
    if not _load():
        return None
    _declare()
    _ctx = _make_context()
    import httplib
    httplib.HTTPSConnection.connect = _https_connect
    version = _crypto.OpenSSL_version(0)
    logger.info('tlsfix: HTTPS via %s (verify=%s)', version, _verify)
    return version


def openssl_version():
    if _crypto is None:
        return None
    return _crypto.OpenSSL_version(0)
