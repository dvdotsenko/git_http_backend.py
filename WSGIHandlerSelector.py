# -*- coding: utf8 -*-
#!/usr/bin/env python
"""WSGIHandlerSelector
	WSGI delegation matching based on URL path and method.

Copyright (c) 2010 Daniel Dotsenko <dotsa@hotmail.com>
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
"""

import re
import urlparse
from collections import defaultdict

class WSGIHandlerSelector(object):
	"""
	WSGI middleware for URL paths and HTTP method based delegation.

	Based on Selector from http://lukearno.com/projects/selector/
	"""

	def __init__(self, canned_handlers, WSGI_env_key = 'WSGIHandlerSelector'):
		"""
		WSGIHandlerSelector instance initializer.

		WSGIHandlerSelector(WSGI_env_key = 'WSGIHandlerSelector')

		Inputs:
		 canned_handlers (mandatory)
		  A pointer to an instance of a class or a function that fills the role
		  of WSGOCannedHTTPHandlers.CannedHTTPHandlers class.

		 WSGI_env_key (optional) (must be named arg)
		  name of the key selector injects into WSGI's environ.
		  The key will be the base for other dicts, like .matches - the key-value pairs of
		  name-matchedtext matched groups. Defaults to 'WSGIHandlerSelector'

		"""
		self.mappings = []
		self.WSGI_env_key = WSGI_env_key
		self.canned_handlers = canned_handlers

	def add(self, path, default_handler = None, **http_methods):
		"""
		Add a selector mapping.

		add(path, default_handler, **named_handlers)

		Inputs:
		 path - A regex string. We will compile it.
		  Highly recommend using grouping of type: "(?P<groupname>.+)"
		  These will be exposed to WSGI app through environment key.

		 default_handler - (optional) A pointer to the function / iterable
		  class instance that will handle ALL HTTP methods (verbs)

		 **named_handlers - (optional) An unpacked dict of handlers allocated
		  to handle specific HTTP methods (HTTP verbs). See "Examples" below.

		Matched named method handlers override default handler.

		If neither default_handler nor named_handlers point to any methods,
		"Method not implemented" is returned for the requests.

		Examples:
			.add('^(?P<working_path>.*)$',generic_handler,
			                  POST=post_handler, HEAD=head_handler)

		If you want to expand "custom_assembled" mapping dict
		 like {'GET':a,'POST':b}:
			.add('^(?P<working_path>.*)$', **custom_assembled_dict)

		If the string contains '\?' - which translates to '?' for non-regex
		strings, we understand that as "match on QUERY_PATH + '?' + QUERY_STRING"

		When lookup matches are met, results are injected into
		environ['wsgiorg.routing_args'] per
		http://www.wsgi.org/wsgi/Specifications/routing_args
		"""
		if default_handler:
			methods = defaultdict(default_handler, http_methods.copy())
		else:
			methods = http_methods.copy()
		self.mappings.append((re.compile(path.decode('utf8')), methods, (path.find(r'\?')>-1) ))

	def __call__(self, environ, start_response):
		"""
		Delegate request to the appropriate WSGI app.

		The following keys will be added to the WSGI's environ:

		wsgiorg.routing_args
			It's a tuple of a list and a dict. The structure is per this spec:
			http://www.wsgi.org/wsgi/Specifications/routing_args

		WSGIHandlerSelector.matched_request_methods
			It's a list of strings denoting other HTTP methods the matched URI
			(not chosen handler!) accepts for processing.

		WSGIHandlerSelector.canned_handlers
			Pointer to WSGI-like app. It serves "canned," WSGI-compatible HTTP
			responses based on specified codes. See CannedHTTPHandlers class for
			list of supported error codes, or query (a static dict) call like:
				CannedHTTPHandlers.collection.keys()

			Example:
			a = environ['WSGIHandlerSelector.canned_handlers']
			return a('404', environ, start_response, headers = headerList)
		"""
		path = environ.get('PATH_INFO', '').decode('utf8')

		matches = None
		handler = None
		alternate_HTTP_verbs = set()
		query_string = (environ.get('QUERY_STRING') or '')

		# sanitizing the path:
		# turns garbage like this: r'//qwre/asdf/..*/*/*///.././../qwer/./..//../../.././//yuioghkj/../wrt.sdaf'
		# into something like this: /../../wrt.sdaf
		path = urlparse.urljoin(u'/', re.sub('//+','/',path.strip('/')))
		if not path.startswith('/../'):
			for _regex, _registered_methods, _use_query_string in self.mappings:
				if _use_query_string:
					matches = _regex.search(path + '?' + query_string)
				else:
					matches = _regex.search(path)

				if matches:
					if _registered_methods.get(environ['REQUEST_METHOD']):
						# note, there is a chance that 'methods' is an instance of
						# collections.defaultdict, which means if default handler was
						# defined it will be returned for all unmatched HTTP methods.
						handler = _registered_methods.get(environ['REQUEST_METHOD'])
						break
					else:
						alternate_HTTP_verbs.update(_registered_methods.keys())
		if handler:
			environ['PATH_INFO'] = path.encode('utf8')

			mg = list(environ.get('wsgiorg.routing_args') or ([],{}))
			mg[0] = list(mg[0]).append(matches.groups()),
			mg[1].update(matches.groupdict())
			environ['wsgiorg.routing_args'] = tuple(mg)

			environ[self.WSGI_env_key+'.canned_handlers'] = self.canned_handlers

#			with open('envlog.txt','a') as _f:
#				_k = environ.keys()
#				_k.sort()
#				_f.writelines(["%s: %s\n" % (key, environ[key]) for key in _k])
#				_f.write('\n')

			return handler(environ, start_response)
		elif alternate_HTTP_verbs:
			# uugh... narrow miss. Regex matched some path, but the method was off.
			# let's advertize what methods we can do with this URI.
			return self.canned_handlers('method_not_allowed', environ,
				start_response, headers = [('Allow', ', '.join(alternate_HTTP_verbs))])
		else:
			return self.canned_handlers('not_found', environ, start_response)