#!/usr/bin/env python2.4
"""static - A simple WSGI-based web server to serve static content.

Copyright (c) 2010  Daniel Dotsenko <dotsa@hotmail.com>
Copyright (C) 2006-2009 Luke Arno - http://lukearno.com/

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version 2.1 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this library; if not, write to:

The Free Software Foundation, Inc., 
51 Franklin Street, Fifth Floor, 
Boston, MA  02110-1301, USA.

Luke Arno can be found at http://lukearno.com/
"""

import mimetypes
import email.utils
import time
import os
import re
from wsgiref.headers import Headers
import urlparse # TODO: check if this module exists in P3.x.

class StatusApp:
	"""Used by WSGI apps to return some HTTP status."""

	def __init__(self, status, message=None):
		self.status = status
		if message is None:
			self.message = status
		else:
			self.message = message

	def __call__(self, environ, start_response, headers=[]):
		if self.message:
			Headers(headers).add_header('Content-type', 'text/plain')
		start_response(self.status, headers)
		if environ['REQUEST_METHOD'] == 'HEAD':
			return [""]
		else:
			return [self.message]

class StaticContentServer(object):
	"""
	A simple way to serve static content via WSGI.

	Serve the file of the same path as PATH_INFO in self.root

	Look up the Content-type in self.content_types by extension
	or use 'text/plain' if the extension is not found.

	Serve up the contents of the file or delegate to self.not_found.

	Copyright (C) 2010 Daniel Dotsenko <dotsa @ hotmail.com>
	Copyright (C) 2006-2009 Luke Arno - http://lukearno.com/
	"""

	block_size = 65536

	not_found = StatusApp('404 Not Found')
	not_modified = StatusApp('304 Not Modified', "")
	moved_permanently = StatusApp('301 Moved Permanently')
	method_not_allowed = StatusApp('405 Method Not Allowed')

	def __init__(self, pathprefix, **kw):
		self.root = pathprefix
		for k, v in kw.iteritems():
			setattr(self, k, v)

	def __call__(self, environ, start_response):
		if environ['REQUEST_METHOD'] not in ('GET', 'HEAD', 'POST'):
			customHeaders = [('Allow', 'GET, HEAD, POST')]
			return self.method_not_allowed(environ, start_response, customHeaders)

		# this code is here specifically to deal with path's inserted by
		# WSGISelector middleware. It adds to environ. If this fails, it means
		# WSGISelector module was not used and we will fall back to PATH_INFO
		selector_vars = environ.get('selector.vars',{})
		if 'working_path' in selector_vars: # working_path is custom key used for git-http-backend. May conflict.
			path_info = selector_vars['working_path'].decode('utf8')
		else:
			path_info = environ.get('PATH_INFO', '').decode('utf8') # needs to be unicode in order to be able to look up non-latin file names.

		# sanitizing the path:
		# turns garbage like this: r'//qwre/asdf/..*/*/*///.././../qwer/./..//../../.././//yuioghkj/../wrt.sdaf'
		# into something like this: /../../wrt.sdaf
		path_info = urlparse.urljoin(u'/', re.sub('//+','/',path_info.strip('/')))
		# at this point all relative links should be resolved. 
		# If they are still there, we have someone playing with URIs.
		if path_info.startswith('/..'):
			return self.not_found(environ, start_response)

		# this, i hope, safely turns the relative path into OS-specific, absolute.
		full_path = os.path.abspath(os.path.join(self.root, path_info.strip('/')))
		content_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
		# 	"Content-Transfer-Encoding: binary"

		# print "local path is %s\n" % full_path
#		try:
		if True:
			etag, last_modified = self._file_stats(full_path)
			customHeaders = [
					('Date', email.utils.formatdate(time.time())),
					('Last-Modified', last_modified),
					('ETag', etag)
				]

			if_modified = environ.get('HTTP_IF_MODIFIED_SINCE')
			if if_modified and (email.utils.parsedate(if_modified) >= email.utils.parsedate(last_modified)):
				return self.not_modified(environ, start_response, customHeaders)

			if_none = environ.get('HTTP_IF_NONE_MATCH')
			if if_none and (if_none == '*' or etag in if_none):
				return self.not_modified(environ, start_response, customHeaders)

			customHeaders.append(('Content-Type', content_type))
			start_response("200 OK", customHeaders)
			return self._package_body(full_path, environ)
#		except:
#			return self.not_found(environ, start_response)

	def _file_stats(self, full_path):
		"""Return a tuple of etag, last_modified by mtime from stat."""
		mtime = os.stat(full_path).st_mtime
		return str(mtime), email.utils.formatdate(mtime)

	def _package_body(self, full_path, environ):
		"""Return an iterator over the body of the response."""
		file_like = open(full_path, 'rb')
		if 'wsgi.file_wrapper' in environ:
			return environ['wsgi.file_wrapper']( file_like, self.block_size )
		else:
			return iter( lambda: file_like.read(self.block_size), '' )

if __name__ == '__main__':
	from wsgiref import simple_server
	httpd = simple_server.WSGIServer(('',80),simple_server.WSGIRequestHandler)
	httpd.set_app(StaticContentServer('\\tmp\\testgitrepo.git\\'))
	httpd.serve_forever()
