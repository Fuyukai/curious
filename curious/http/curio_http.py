"""
The HTTP module for Curious.

This code is 100% portable - it will work anywhere that h11 and multidict are also installed.
"""


import logging
import mimetypes
import random
import string
from functools import partial
try:
    import ujson as py_json
except ImportError:
    import json as py_json
import cgi

import multidict
import yarl
import h11
from curio import io
from h11._events import _EventBundle
from multidict import MultiDict
import curio

__version__ = "0.1.0-curious"

logger = logging.getLogger(__name__)


class HTTPError(Exception):
    def __init__(self, *args, **kwargs):
        self.response = kwargs.pop('response')
        super().__init__(*args, **kwargs)


_BOUNDARY_CHARS = string.digits + string.ascii_letters


def encode_multipart(fields, files, boundary=None):
    r"""Encode dict of form fields and dict of files as multipart/form-data.
    Return tuple of (body_string, headers_dict). Each value in files is a dict
    with required keys 'filename' and 'content', and optional 'mimetype' (if
    not specified, tries to guess mime type or uses 'application/octet-stream').

    >>> body, headers = encode_multipart({'FIELD': 'VALUE'},
    ...                                  {'FILE': {'filename': 'F.TXT', 'content': 'CONTENT'}},
    ...                                  boundary='BOUNDARY')
    >>> print('\n'.join(repr(l) for l in body.split('\r\n')))
    '--BOUNDARY'
    'Content-Disposition: form-data; name="FIELD"'
    ''
    'VALUE'
    '--BOUNDARY'
    'Content-Disposition: form-data; name="FILE"; filename="F.TXT"'
    'Content-Type: text/plain'
    ''
    'CONTENT'
    '--BOUNDARY--'
    ''
    >>> print(sorted(headers.items()))
    [('Content-Length', '193'), ('Content-Type', 'multipart/form-data; boundary=BOUNDARY')]
    >>> len(body)
    193

    Copied from: https://code.activestate.com/recipes/578668-encode-multipart-form-data-for-uploading-files-via/
    """

    def escape_quote(s):
        return s.replace(b'"', b'\\"')

    if boundary is None:
        boundary = b''.join(random.choice(_BOUNDARY_CHARS).encode() for i in range(30))
    lines = []

    for name, value in fields.items():
        if isinstance(name, str):
            name = name.encode()
        else:
            name = str(name).encode()

        if isinstance(value, str):
            value = value.encode()
        else:
            value = str(value).encode()

        lines.extend((
            b'--%s' % boundary,
            b'Content-Disposition: form-data; name="%s"' % escape_quote(name),
            b'',
            value,
        ))

    for name, value in files.items():
        filename = value['filename']
        if 'mimetype' in value:
            mimetype = value['mimetype']
        else:
            mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        lines.extend((
            b'--%s' % boundary,
            b'Content-Disposition: form-data; name="%s"; filename="%s"' % (
                escape_quote(name.encode()), escape_quote(filename.encode())),
            b'Content-Type: %s' % mimetype.encode(),
            b'',
            value['content'],
        ))

    lines.extend((
        b'--%s--' % boundary,
        b'',
    ))
    body = b'\r\n'.join(lines)

    headers = {
        'Content-Type': 'multipart/form-data; boundary=%s' % boundary.decode(),
        'Content-Length': str(len(body)),
    }

    return body, headers


def get_encoding_from_headers(headers: MultiDict):
    """
    Attempts to get the encoding of the request based on the headers.
    """
    content_type = headers.get('content-type')

    if not content_type:
        return None

    content_type, params = cgi.parse_header(content_type)

    if 'charset' in params:
        return params['charset'].strip("'\"")

    if 'text' in content_type:
        return 'ISO-8859-1'


class _EventIterator:
    """
    An iterator that allows you to receive events from a connection.
    """

    def __init__(self, event_source):
        self.event_source = event_source

    async def __aiter__(self):
        return self

    async def __anext__(self):
        event = await self.event_source()

        if type(event) is h11.Data:
            return event.data
        elif type(event) is h11.EndOfMessage:
            raise StopAsyncIteration
        else:
            raise ValueError('Unknown h11 event: %r', event)


class Response:
    """
    A wrapper around the Response from the server.
    """

    def __init__(self, raw_response: h11.Response, h11_request: h11.Request, conn: 'HTTPConnection'):
        self.status_code = raw_response.status_code
        self.http_version = raw_response.http_version.decode('utf-8')

        self.headers = multidict.CIMultiDict(
            (key.decode("utf-8"), value.decode("utf-8")) for key, value in raw_response.headers
        )

        self.h11_request = h11_request
        self.conn = conn

        self.history = None

    def __repr__(self):
        return '<Response [%s]>' % (self.status_code)

    @property
    def url(self):
        """The final URL that was requested."""
        return '{host}:{port}{target}'.format(
            host=self.conn.host,
            port=self.conn.port,
            target=self.h11_request.target.decode('utf-8'),
        )

    async def close(self):
        """
        Closes the current request.

        This should always be called.
        """
        await self.conn.close()

    def raise_for_status(self):
        """Raises HTTPError, if one occurred."""
        http_error_msg = ''

        if 400 <= self.status_code < 500:
            http_error_msg = '%s Client Error for url: %s' % (
                self.status_code, self.url)

        elif 500 <= self.status_code < 600:
            http_error_msg = '%s Server Error for url: %s' % (
                self.status_code, self.url)

        if http_error_msg:
            raise HTTPError(http_error_msg, response=self)

    @property
    def is_redirect(self):
        """Whether the response is a well-formed redirect."""
        return 'location' in self.headers and 301 <= self.status_code < 400

    def iter_chunked(self, maxsize=None):
        """Stream raw response body, maxsize bytes at a time."""
        return _EventIterator(partial(self.conn._next_event, maxsize))

    async def binary(self) -> bytes:
        """Return the full response body as a bytearray."""
        data = b""
        async for chunk in self.iter_chunked():
            data += chunk

        return data

    async def text(self):
        """Return the full response body as a string."""
        data = await self.binary()
        if data is None:
            return None

        # encoding = get_encoding_from_headers(self.headers)

        return data.decode("utf-8")

    async def json(self):
        """Return the full response body as parsed JSON."""
        data = await self.binary()
        if data is None:
            return None

        return py_json.loads(data.decode('utf-8'))


class HTTPConnection:
    """Maries an async socket with an HTTP handler."""

    def __init__(self, host: str, port: int, ssl):
        """
        :param host: The host to connect to.
        :param port: The port to connect to.
        :param ssl: Any SSL context to use.
        """
        self.host = host
        self.port = port
        self.ssl = ssl

        #: The current socket connection.
        self.sock = None  # type: io.Socket
        #: The H11 connection state.
        self.state = None  # type: h11.Connection

    def __repr__(self):
        return '%s(host=%r, port=%r)' % (
            self.__class__.__name__, self.host, self.port)

    async def open(self):
        """
        Opens a connection to the server.
        """
        sock_args = dict(
            host=self.host,
            port=self.port,
        )

        if self.ssl:
            sock_args.update(dict(
                ssl=self.ssl,
                server_hostname=self.host
            ))

        self.sock = await curio.open_connection(**sock_args)
        self.state = h11.Connection(our_role=h11.CLIENT)

        logger.debug('Opened %r', self)

    async def close(self):
        """
        Closes a connection to the server.
        """
        await self.sock.close()

        self.sock = None
        self.state = None

        logger.debug('Closed %r', self)

    async def _send(self, event: _EventBundle):
        """
        Sends an event to the server.

        :param event: The event to send.
        """
        # logger.debug("Sending event: %s", event)

        data = self.state.send(event)
        await self.sock.sendall(data)

    async def _next_event(self, maxsize: int=None) -> _EventBundle:
        """
        Gets the next event from the connection.

        This will automatically read data off of the connection.

        :param maxsize: The maximum size to read off the socket.
            If not specified, 2048 will be used.
        :return:
        """

        if not maxsize:
            maxsize = 2048

        while True:
            event = self.state.next_event()

            # logger.debug("Received event: %s", event)

            if event is h11.NEED_DATA:
                data = await self.sock.recv(maxsize)
                self.state.receive_data(data)
                continue

            return event

    async def request(self, h11_request: h11.Request, data=None) -> h11.Response:
        """
        Makes a request.

        :param h11_request: The :class:`h11.Request` object to use.
        :param data: Any request data to send to the server.
        """
        # First, send the base request.
        await self._send(h11_request)

        # Send data chunks.
        if data is not None:
            await self._send(h11.Data(data=data))

        # Finally, send the EOF.
        await self._send(h11.EndOfMessage())

        # Read the response off of the server now.
        event = await self._next_event()

        assert isinstance(event, h11.Response)

        return event


def _prepare_request(method: str, url: yarl.URL, *,
                     params=None, headers=None,
                     body=None,
                     json: dict = None, files: dict = None):
    """
    Prepares a new request, creating a :class:`h11.Request` object to be sent.
    Additionally, this also serializes the body into a bytestring ready to be sent.

    :param method: The method of the request.
    :param url: The URL to request.
    :param headers: Optional. The headers of the request.
        This should be a dict or a MultiDict.
    :param body: Optional. Any body data to send.
        If this is a dict, it is encoded as multipart/form-data.
    :param json: Optional. A dict that should be JSON encoded and sent as the body.
    """
    url = yarl.URL(url)

    if params:
        query_vars = list(url.query.items()) + list(params.items())
        url = url.with_query(query_vars)

    target = str(url.relative())

    if headers is None:
        headers = MultiDict()
    elif not isinstance(headers, MultiDict):
        headers = MultiDict(headers)

    headers.setdefault('Host', url.raw_host)

    if json is not None:
        body = py_json.dumps(json).encode()
    else:
        # Check if the body is a dict.
        # If so, send it as `multipart/form-data`.
        if isinstance(body, dict):
            body, _h = encode_multipart(body, files)
            headers.update(_h)

    if body is not None:
        if "Content-Length" not in headers:
            headers["Content-Length"] = str(len(body)).encode('utf-8')

    if json is not None:
        headers["Content-Type"] = b"application/json"

    if "Content-Length" not in headers:
        headers["Content-Length"] = b"0"

    if "User-Agent" not in headers:
        headers["User-Agent"] = "curio_http/{} curio/{}".format(__version__, curio.__version__)

    if not all(isinstance(header, (str, bytes)) for header in headers.keys()):
        raise ValueError("Header keys must be str or bytes")

    if not all(isinstance(header, (str, bytes)) for header in headers.values()):
        raise ValueError("Header values must be str or bytes")

    h11_request = h11.Request(
        method=method,
        target=target,
        headers=list(headers.items())
    )

    return h11_request, body


class ClientSession:
    """
    The session class that is used to send data to the server.
    """
    def __init__(self):
        #: A dictionary of all open connections.
        self.open_connections = []

        #: Any headers that are to be sent on every request.
        self.headers = MultiDict()
        self.headers.setdefault("User-Agent", "curio-http/{} (bundled with curious)".format(__version__))

    async def __aenter__(self) -> 'ClientSession':
        return self

    async def __aexit__(self, exc_type, exc, tb):
        for conn in self.open_connections:
            await conn.close()

    async def _request(self, method, url, *args, **kwargs):
        """
        Makes a request to the server.

        This method is internal - use `request` instead.
        """
        headers = MultiDict(self.headers.copy())
        headers.extend(kwargs.get("headers", {}))
        kwargs["headers"] = headers

        h11_request, body = _prepare_request(
            method, url, *args, **kwargs)

        conn = HTTPConnection(
            host=url.raw_host,
            port=url.port,
            ssl=url.scheme == 'https',
        )

        await conn.open()

        self.open_connections.append(conn)

        raw_response = await conn.request(h11_request, body)

        return Response(raw_response, h11_request, conn)

    async def request(self, method: str, url: str, *args,
                      allow_redirects=False, **kwargs):
        """
        Performs a HTTP request.

        :param method: The HTTP method of the request.
        :param url: The URL of the request.
        :param allow_redirects: Should redirects be automatically followed?
        """
        url = yarl.URL(url)

        response = await self._request(method, url, *args, **kwargs)

        if allow_redirects:
            history = []

            while response.is_redirect:
                history.append(response)

                # Redirects can be relative.
                new_url = url.join(yarl.URL(response.headers['location']))

                response = await self._request(method, new_url)

            response.history = history

        return response

    def get(self, *args, allow_redirects=True, **kwargs):
        """Perform HTTP GET request."""
        return self.request(
            'GET', *args, allow_redirects=allow_redirects, **kwargs)

    def post(self, *args, **kwargs):
        """Perform HTTP POST request."""
        return self.request('POST', *args, **kwargs)

    def put(self, *args, **kwargs):
        return self.request("PUT", *args, **kwargs)

    def patch(self, *args, **kwargs):
        return self.request("PATCH", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.request("DELETE", *args, **kwargs)
