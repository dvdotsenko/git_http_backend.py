# -*- coding: utf8 -*-
#!/usr/bin/env python
'''
Copyright (c) 2010  Daniel Dotsenko <dotsa@hotmail.com>

This file is part of git_http_backend.py Project.

git_http_backend.py Project is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 2.1 of the License, or
(at your option) any later version.

git_http_backend.py Project is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with git_http_backend.py Project.  If not, see <http://www.gnu.org/licenses/>.
'''

from wsgiref.headers import Headers

class CannedHTTPHandlers(object):
	'''
	Semi-useless helper class that makes it possible to issue HTTP error + status
	responses in one simple line of code.

	Should probably be a simple function.
	'''
	collection = {
		'304': '304 Not Modified',
		'not_modified': '304 Not Modified',
		'301': '301 Moved Permanently',
		'moved': '301 Moved Permanently',
		'400':'400 Bad request',
		'bad_request':'400 Bad request',
		'401':'401 Access denied',
		'access_denied':'401 Access denied',
		'401.4': '401.4 Authorization failed by filter',
		'403':'403 Forbidden',
		'forbidden':'403 Forbidden',
		'404': "404 Not Found",
		'not_found': "404 Not Found",
		'405': "405 Method Not Allowed",
		'method_not_allowed': "405 Method Not Allowed",
		'417':'417 Execution failed',
		'execution_failed':'417 Execution failed',
		'200': "200 OK",
	}

	def __call__(self, code, environ, start_response, headers = []):
		'''
		This is NOT a WSGI-compliant app. We convert an error code into
		certain action over start_response and return a WSGI-compliant payload.
		'''
		headerbase = [('Content-Type', 'text/plain')]
		if headers:
			hObj = Headers(headerbase)
			for header in headers:
				hObj[header[0]] = '; '.join(header[1:])
		start_response(self.collection[code], headerbase)
		return ['']