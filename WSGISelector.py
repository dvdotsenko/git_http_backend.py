# -*- coding: utf8 -*-
"""selector - WSGI delegation based on URL path and method.

(See the docstring of selector.Selector.)

Copyright (C) 2006 Luke Arno - http://lukearno.com/

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version 2.1 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this library; if not, write to 
the Free Software Foundation, Inc., 51 Franklin Street, 
Fifth Floor, Boston, MA  02110-1301  USA

Luke Arno can be found at http://lukearno.com/

"""

import re

class CannedHTTPHandlers(object):
	collection = {
		'404': "404 Not Found",
		'405': "405 Method Not Allowed",
		'200': "200 Ok",
		'100': "100 Continue"
	}

	def __call__(self, code, environ, start_response):
		'''
		This is NOT a WSGI-compliant app. We convert an error code into
		certain action over start_response and return a WSGI-compliant payload.
		'''
		# TODO: support  [('Allow', ', '.join(environ['selector.methods'])), for 405

		start_response(self.collection[code], [('Content-Type', 'text/plain')])
		return ['']


class WSGIHandlerSelector(object):
	"""
	WSGI middleware for URL paths and HTTP method based delegation.

	Based on Selector from http://lukearno.com/projects/selector/
	"""
	
	def __init__(self, **kw):
		"""
		WSGIHandlerSelector instance initializer.

		WSGIHandlerSelector(WSGI_env_key = 'WSGIHandlerSelector')

		Inputs:
		 WSGI_env_key - name of the key selector injects into WSGI's environ.
		  The key will be the base for other dicts, like .matches - the key-value pairs of
		  name-matchedtext matched groups. Defaults to 'WSGIHandlerSelector'

		 error_handlers - dictionary of error-code-mapped handler instances

		"""
		self.mappings = []
		self.WSGI_env_key = 'WSGIHandlerSelector'
		self.error_handler = CannedHTTPHandlers()
		self.__dict__.update(kw)

	def add(self, *arg, **http_methods):
		"""
		Add a selector mapping.

		add(path, default_handler, **named_handlers)

		Inputs:
		 path - A regex string. We will compile it.
		  Highly recommend using grouping of type: "(?P<groupname>.+)"
		  These will be exposed to WSGI app through environment key.

		 default_handler - (optional) A pointer to the function / iterable
		  class instance that will handle ALL HTTP methods (verbs)

		 named_handlers - (optional) A dict of handlers specifically allocated
		  to handle specific HTTP methods (verbs). See "Examples" below.

		Matched named method handlers override default handler.

		If neither default_handler nor named_handlers point to any methods,
		"Method not implemented" is returned for all requests.

		Examples:
			.add('^(?P<working_path>.*)$',generic_handler, POST=post_handler, HEAD=head_handler)

		If you want to expand "custom_assembled" mapping dict like {'GET':a,'POST':b}:
			.add('^(?P<working_path>.*)$', **custom_assembled_dict)

		Matched groups will be in a dictionary under WSGIHandlerSelector.matched_groups
		"""
		if len(arg) > 0:
			path = arg[0]
		methods = http_methods.copy()
		if len(arg) > 1:
			methods['__ANY__'] = arg[1]
		self.mappings.append((re.compile(path.decode('utf8')), methods))

	def __call__(self, environ, start_response):
		"""Delegate request to the appropriate WSGI app."""
		path = environ.get('PATH_INFO', '').decode('utf8')

		# sanitizing the path:
		# turns garbage like this: r'//qwre/asdf/..*/*/*///.././../qwer/./..//../../.././//yuioghkj/../wrt.sdaf'
		# into something like this: /../../wrt.sdaf
		path = urlparse.urljoin(u'/', re.sub('//+','/',path.strip('/')))
		if not path_info.startswith('/..'):
			for regex, methods in self.mappings:
				matches = regex.search(path)
				if matches:
					handler = methods.get(environ['REQUEST_METHOD'] , None) or methods.get('__ANY__', None)
					if handler:
						environ['PATH_INFO'] = path.encode('utf8')
						environ[self.WSGI_env_key+'.matched_groups'] = environ.get(
								self.WSGI_env_key+'.matched_groups', {}
							).update(matches.groupdict())
						environ[self.WSGI_env_key+'.error_handler'] = self.error_handler
						return handler(environ, start_response)
					else:
						return self.error_handler('405', environ, start_response)
		return self.error_handler('404', environ, start_response)

