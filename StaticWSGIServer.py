# -*- coding: utf8 -*-
#!/usr/bin/env python
"""
static - A simple WSGI-based web server to serve static content.

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
"""

import time
import os
import email.utils
import mimetypes
mimetypes.add_type('application/x-git-packed-objects-toc','.idx')
mimetypes.add_type('application/x-git-packed-objects','.pack')

class StaticWSGIServer(object):
	"""
	A simple WSGI-based static content server app.

	Relies on WSGIHandlerSelector for prepopulating some needed environ
	variables, cleaning up the URI, setting up default error handlers.

	Inputs:
		path_prefix (mandatory)
			String containing a file-system level path behaving as served root.

		canned_handlers (optional*)
			Function or class instance that can take WSGI-like +2 arguments
			and capable or emitting WSGI-compatible output.
			(See CannedHTTPHandlers class for argument details.)
			If omitted the code will try to pick the handler from environ's
			WSGIHandlerSelector.canned_handlers key - product of WSGIHandlerSelector
			* If canned_handler is not passed in and not in environ, raise error.

		block_size (optional)
			File reader's buffer size. Defaults to 65536. 
	"""

	def __init__(self, pathprefix, canned_handlers, block_size = 65536):
		self.root = pathprefix
		self.canned_handlers = canned_handlers
		self.block_size = block_size

	def __call__(self, environ, start_response):
		selector_matches = (environ.get('wsgiorg.routing_args') or ([],{}))[1]
		if 'working_path' in selector_matches:
			# working_path is a custom key that I just happened to decide to use
			# for marking the portion of the URI that is palatable for static serving.
			# 'working_path' is the name of a regex group fed to WSGIHandlerSelector
			path_info = selector_matches['working_path'].decode('utf8')
		else:
			path_info = environ.get('PATH_INFO', '').decode('utf8')

		# this, i hope, safely turns the relative path into OS-specific, absolute.
		full_path = os.path.abspath(os.path.join(self.root, path_info.strip('/')))

		if not os.path.isfile(full_path):
			return self.canned_handlers('not_found', environ, start_response)

		try:
			mtime = os.stat(full_path).st_mtime
			etag, last_modified =  str(mtime), email.utils.formatdate(mtime)
			customHeaders = [
					('Date', email.utils.formatdate(time.time())),
					('Last-Modified', last_modified),
					('ETag', etag)
				]

			if_modified = environ.get('HTTP_IF_MODIFIED_SINCE')
			if if_modified and (email.utils.parsedate(if_modified) >= email.utils.parsedate(last_modified)):
				return self.canned_handlers('not_modified', environ, start_response, headers=customHeaders)

			if_none = environ.get('HTTP_IF_NONE_MATCH')
			if if_none and (if_none == '*' or etag in if_none):
				return self.canned_handlers('not_modified', environ, start_response, headers=customHeaders)

			content_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
			customHeaders.append(('Content-Type', content_type))
			start_response("200 OK", customHeaders)
			return self._package_body(full_path, environ)
		except:
			return self.canned_handlers('not_found', environ, start_response)

	def _package_body(self, full_path, environ):
		"""Return an iterator over the body of the response."""
		file_like = open(full_path, 'rb')
		if 'wsgi.file_wrapper' in environ:
			return environ['wsgi.file_wrapper']( file_like, self.block_size )
		else:
			return iter( lambda: file_like.read(self.block_size), '' )
