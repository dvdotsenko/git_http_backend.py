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
from WSGICannedHTTPHandlers import CannedHTTPHandlers

class WSGIHandlerSelector(object):
	"""
	WSGI middleware for URL paths and HTTP method based delegation.

	Based on Selector from http://lukearno.com/projects/selector/
	"""

	class dict_with_default(object):
		'''
		Behaves like a regulare dict, but returns default by default.

		Normal dict can return default when asked like this: dict.get(key, default)
		I feel lazy and want the dict to store the default inside and just give it to me.

		Inputs:
		 defaultvalue - the value you want the dict to return when you call dict[key]
		  and key is not there.

		 obj - starting dict obj.

		Returns:
		 dictionary-like object with __getitem__() orverriden to return value always
		 and get() to return default when default argument is not defined in the
		 funciton call.
		'''
		def __init__(self, defaultvalue, obj = {}):
			self.defaultvalue = defaultvalue
			self.dictObj = obj

		def get(self, *args, **kw):
			if (args[0] not in self.dictObj) and (len(args) < 2):
				args = list(args)
				args.insert(1, self.defaultvalue)
			return self.dictObj.get(*args, **kw)
		def __getitem__(self, *args, **kw):
			args = list(args)
			args.insert(1, self.defaultvalue)
			return self.get(*args, **kw)

		def iteritems(self, *args, **kw): return self.dictObj.iteritems(*args, **kw)
		def pop(self, *args, **kw): return self.dictObj.pop(*args, **kw)
		def has_key(self, *args, **kw): return self.dictObj.has_key(*args, **kw)
		def __contains__(self, *args, **kw): return self.dictObj.__contains__(*args, **kw)
		def __cmp__(self, *args, **kw): return self.dictObj.__cmp__(*args, **kw)
		def itervalues(self, *args, **kw): return self.dictObj.itervalues(*args, **kw)
		def __len__(self, *args, **kw): return self.dictObj.__len__(*args, **kw)
		def __ne__(self, *args, **kw): return self.dictObj.__ne__(*args, **kw)
		def keys(self, *args, **kw): return self.dictObj.keys(*args, **kw)
		def update(self, *args, **kw): return self.dictObj.update(*args, **kw)
		def __iter__(self, *args, **kw): return self.dictObj.__iter__(*args, **kw)
		def popitem(self, *args, **kw): return self.dictObj.popitem(*args, **kw)
		def copy(self, *args, **kw): return self.dictObj.copy(*args, **kw)
		def __eq__(self, *args, **kw): return self.dictObj.__eq__(*args, **kw)
		def iterkeys(self, *args, **kw): return self.dictObj.iterkeys(*args, **kw)
		def __delitem__(self, *args, **kw): return self.dictObj.__delitem__(*args, **kw)
		def fromkeys(self, *args, **kw): return self.dictObj.fromkeys(*args, **kw)
		def items(self, *args, **kw): return self.dictObj.items(*args, **kw)
		def clear(self, *args, **kw): return self.dictObj.clear(*args, **kw)
		def __setitem__(self, *args, **kw): return self.dictObj.__setitem__(*args, **kw)
		def values(self, *args, **kw): return self.dictObj.values(*args, **kw)

	def __init__(self, **kw):
		"""
		WSGIHandlerSelector instance initializer.

		WSGIHandlerSelector(WSGI_env_key = 'WSGIHandlerSelector')

		Inputs:
		 WSGI_env_key (optional) (must be named arg)
		  name of the key selector injects into WSGI's environ.
		  The key will be the base for other dicts, like .matches - the key-value pairs of
		  name-matchedtext matched groups. Defaults to 'WSGIHandlerSelector'

		 canned_handlers (optional) (must be named arg)
		  A pointer to an instance of a class or a function that fills the role
		  of WSGOCannedHTTPHandlers.CannedHTTPHandlers class.

		"""
		self.mappings = []
		self.WSGI_env_key = 'WSGIHandlerSelector'
		self.__dict__.update(kw)

		if not self.canned_handlers:
			self.canned_handlers = CannedHTTPHandlers()

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

		If the string contains '\?' - which translates to '?' for non-regex strings,
		we understand that as "match on QUERY_PATH + '?' + QUERY_STRING"

		Matched groups will be in a dictionary under WSGIHandlerSelector.matched_groups
		"""
		if len(arg) > 0:
			path = arg[0]
		if len(arg) > 1:
			methods = self.dict_with_default(arg[1], http_methods.copy())
		else:
			methods = http_methods.copy()
		self.mappings.append((re.compile(path.decode('utf8')), methods, (path.find('\?')>-1) ))

	def __call__(self, environ, start_response):
		"""
		Delegate request to the appropriate WSGI app.

		The following keys will be added to the WSGI's environ:

		WSGIHandlerSelector.matched_groups
			It's a dict object pointer, containing key-value pairs for name-string
			groups regex matched in the URI.

		WSGIHandlerSelector.matched_request_methods
			It's a list of strings denoting other HTTP methods the matched URI
			(not handler!) accepts for processing.

		WSGIHandlerSelector.canned_handlers
			Pointer to WSGI-like app. It serves "canned," WSGI-compatible HTTP
			responses based on specified codes. See CannedHTTPHandlers class for
			list of supported error codes, or do (a static dict) call like:
				ThisModule'sName.CannedHTTPHandlers.collection.keys()

			Example:
			a = WSGIHandlerSelector.canned_handlers
			return a('404', environ, start_response, headers = headerList)
		"""
		path = environ.get('PATH_INFO', '').decode('utf8')

		_matches = None
		_handler = None
		_registered_methods = {}
		_query_string = (environ.get('QUERY_STRING') or '')

		# sanitizing the path:
		# turns garbage like this: r'//qwre/asdf/..*/*/*///.././../qwer/./..//../../.././//yuioghkj/../wrt.sdaf'
		# into something like this: /../../wrt.sdaf
		path = urlparse.urljoin(u'/', re.sub('//+','/',path.strip('/')))
		if not path.startswith('/../'):
			for _regex, _registered_methods, _use_query_string in self.mappings:
				_matches = _regex.search('?'.join([path,int(_use_query_string)*_query_string]))
				if _matches:
					# note, there is a chance that 'methods' is an instance of our custom
					# dict_with_default class, which means if default handler was
					# defined it will be returned for all unmatched HTTP methods.
					_handler = _registered_methods.get(environ['REQUEST_METHOD'])
					break
		if _handler:
			environ['PATH_INFO'] = path.encode('utf8')

			mg = environ.get(self.WSGI_env_key+'.matched_groups', {})
			mg.update(_matches.groupdict())
			environ[self.WSGI_env_key+'.matched_groups'] = mg

			environ[self.WSGI_env_key+'.matched_request_methods'] = \
				_registered_methods.keys() or [ environ['REQUEST_METHOD'] ]
			environ[self.WSGI_env_key+'.canned_handlers'] = self.canned_handlers
			return _handler(environ, start_response)
		elif _matches:
			# uugh... narrow miss. The regex matched, but the method is off.
			# let's advertize what methods we can do with this URI.
			return self.canned_handlers('method_not_allowed', environ,
				start_response, headers = [('Allow', ', '.join(_registered_methods.keys()))])
		else:
			return self.canned_handlers('not_found', environ, start_response)