#-------------------------------------------------------------------------------
#
#  WPS specific utilities.
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Martin Paces <martin.paces@eox.at>
#
#-------------------------------------------------------------------------------
# Copyright (C) 2016 EOX IT Services GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies of this Software or works derived from this Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#-------------------------------------------------------------------------------

from urllib2 import urlopen, Request, URLError
from contextlib import closing
from urlparse import urlparse
from logging import getLogger

try:
    # available in Python 2.7+
    from collections import OrderedDict
except ImportError:
    from django.utils.datastructures import SortedDict as OrderedDict

from eoxserver.core.util.multiparttools import iterate as iterate_multipart

def parse_named_parts(request):
    """ Extract named parts of the multi-part request
    and return them as dictionary
    """
    parts = {}
    if request.method == 'POST':
        content_type = request.META.get("CONTENT_TYPE", "")
        if content_type.startswith("multipart"):
            parts = dict(
                (content_id, data) for content_id, data in (
                    (headers.get("Content-Id"), data)
                    for headers, data in iterate_multipart(
                        request.body, headers={"Content-Type": content_type}
                    )
                ) if content_id
            )
    return parts


class InMemoryURLResolver(object):
    # pylint: disable=too-few-public-methods, no-self-use
    """ Simple in-memory URL resolver.
    The resolver resolves references and returns them as data strings.
    """

    def __init__(self, parts=None, logger=None):
        self.parts = parts or {}
        self.logger = logger or getLogger(__name__)

    def __call__(self, href, body, headers):
        """ Resolve reference URL. """
        self.logger.debug(
            "Resolving reference: %s%s", href, "" if body is None else " (POST)"
        )
        url = urlparse(href)
        if url.scheme == "cid":
            return self._resolve_multipart(url.path)
        elif url.scheme in ('http', 'https'):
            return self._resolve_http(href, body, headers)
        else:
            raise ValueError("Unsupported URL scheme %r!" % url.scheme)

    def _resolve_multipart(self, content_id):
        """ Resolve multipart-related."""
        try:
            return self.parts[content_id]
        except KeyError:
            raise ValueError("No part with content-id %r." % content_id)

    def _resolve_http(self, href, body=None, headers=None):
        """ Resolve the HTTP request."""
        try:
            with closing(urlopen(Request(href, body, dict(headers)))) as fobj:
                return fobj.read()
        except URLError as exc:
            raise ValueError(str(exc))
