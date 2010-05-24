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
import mimetypes
import email.utils
import time
import os
from wsgiref.headers import Headers

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
	def __lt__(self, *args, **kw): return self.dictObj.__lt__(*args, **kw)
	def __contains__(self, *args, **kw): return self.dictObj.__contains__(*args, **kw)
	def __cmp__(self, *args, **kw): return self.dictObj.__cmp__(*args, **kw)
	def itervalues(self, *args, **kw): return self.dictObj.itervalues(*args, **kw)
	def __len__(self, *args, **kw): return self.dictObj.__len__(*args, **kw)
	def __ne__(self, *args, **kw): return self.dictObj.__ne__(*args, **kw)
	def keys(self, *args, **kw): return self.dictObj.keys(*args, **kw)
	def update(self, *args, **kw): return self.dictObj.update(*args, **kw)
	def __iter__(self, *args, **kw): return self.dictObj.__iter__(*args, **kw)
	def __gt__(self, *args, **kw): return self.dictObj.__gt__(*args, **kw)
	def popitem(self, *args, **kw): return self.dictObj.popitem(*args, **kw)
	def copy(self, *args, **kw): return self.dictObj.copy(*args, **kw)
	def __eq__(self, *args, **kw): return self.dictObj.__eq__(*args, **kw)
	def iterkeys(self, *args, **kw): return self.dictObj.iterkeys(*args, **kw)
	def __delitem__(self, *args, **kw): return self.dictObj.__delitem__(*args, **kw)
	def fromkeys(self, *args, **kw): return self.dictObj.fromkeys(*args, **kw)
	def setdefault(self, *args, **kw): return self.dictObj.setdefault(*args, **kw)
	def items(self, *args, **kw): return self.dictObj.items(*args, **kw)
	def clear(self, *args, **kw): return self.dictObj.clear(*args, **kw)
	def __setitem__(self, *args, **kw): return self.dictObj.__setitem__(*args, **kw)
	def __le__(self, *args, **kw): return self.dictObj.__le__(*args, **kw)
	def values(self, *args, **kw): return self.dictObj.values(*args, **kw)
	def __ge__(self, *args, **kw): return self.dictObj.__ge__(*args, **kw)

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
		'404': "404 Not Found",
		'not_found': "404 Not Found",
		'405': "405 Method Not Allowed",
		'method_not_allowed': "405 Method Not Allowed",
		'200': "200 OK",
	}

	def __call__(self, code, environ, start_response, **kw):
		'''
		This is NOT a WSGI-compliant app. We convert an error code into
		certain action over start_response and return a WSGI-compliant payload.
		'''
		headers = [('Content-Type', 'text/plain')]
		if 'headers' in kw.keys():
			hObj = Headers(headers)
			for header in kw['headers']:
				# key, value = header[0], '; '.join(header[1:])
				hObj[header[0]] = '; '.join(header[1:])
		start_response(self.collection[code], headers)
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
		self.canned_handlers = CannedHTTPHandlers()
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
		if len(arg) > 1:
			methods = dict_with_default(arg[1], http_methods.copy())
		else:
			methods = http_methods.copy()
		self.mappings.append((re.compile(path.decode('utf8')), methods))

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

		# sanitizing the path:
		# turns garbage like this: r'//qwre/asdf/..*/*/*///.././../qwer/./..//../../.././//yuioghkj/../wrt.sdaf'
		# into something like this: /../../wrt.sdaf
		path = urlparse.urljoin(u'/', re.sub('//+','/',path.strip('/')))
		if not path.startswith('/../'):
			for _regex, _registered_methods in self.mappings:
				_matches = _regex.search(path)
				if _matches:
					# note, there is a chance that 'methods' is an instance of our custom
					# dict_with_default class, which means if default handler was
					# defined it will be returned for all unmatched HTTP methods.
					_handler = _registered_methods.get(environ['REQUEST_METHOD'])
					break

		if _handler:
			environ['PATH_INFO'] = path.encode('utf8')
			environ[self.WSGI_env_key+'.matched_groups'] = \
				environ.get(self.WSGI_env_key+'.matched_groups', {}).update(_matches.groupdict())
			environ[self.WSGI_env_key+'.matched_request_methods'] = \
				_registered_methods.keys() or [ environ['REQUEST_METHOD'] ]
			environ[self.WSGI_env_key+'.canned_handlers'] = self.canned_handlers
			return _handler(environ, start_response)
		elif _matches:
			# uugh... narrow miss. The regex matched, but the method is off.
			# let's advertize what methods we can do with this URI.
			return self.canned_handlers('method_not_allowed', environ,
				start_response, [('Allow', ', '.join(_registered_methods.keys()))])
		else:
			return self.canned_handlers('not_found', environ, start_response)

class StaticContentServer(object):
	"""
	A simple WSGI-based static content server app.

	Relies on WSGIHandlerSelector for prepopulating some needed environ
	variables, cleaning up the URI, setting up default error handlers.

	Inputs:
		path_prefix
			String containing a file-system level path.

		canned_handlers (optional)
			Function or class instance that can take WSGI-like arguments
			and capable or emitting WSGI-compatible output.
			(See CannedHTTPHandlers class above for details.)
			If omitted the code will try to pick the handler from environ's
			WSGIHandlerSelector.canned_handlers key - product of WSGIHandlerSelector
			If not set anywhere will be creating an instance on the fly for every request.

		block_size (optional)
			File reader's buffer size. Defaults to 65536. Must be "named" arg.

	Normally would be serving the same path as PATH_INFO with self.root as prefix.
	"""

	def __init__(self, pathprefix, canned_handlers = None, block_size = 65536, **kw):
		self.root = pathprefix
		self.canned_handlers = canned_handlers
		self.block_size = block_size
		self.__dict__.update(kw)

	def __call__(self, environ, start_response):
		if self.canned_handlers:
			canned_handlers = self.canned_handlers
		elif 'WSGIHandlerSelector.canned_handlers' in environ:
			canned_handlers = environ.get('WSGIHandlerSelector.canned_handlers')
		else:
			canned_handlers = CannedHTTPHandlers()

		selector_vars = environ.get('WSGIHandlerSelector.matched_groups',{})
		if 'working_path' in selector_vars:
			# working_path is a custom key that I just happened to decide to use
			# for marking the portion of the URI that is palatable for this static server.
			path_info = selector_vars['working_path'].decode('utf8')
		else:
			path_info = environ.get('PATH_INFO', '').decode('utf8') 

		# this, i hope, safely turns the relative path into OS-specific, absolute.
		full_path = os.path.abspath(os.path.join(self.root, path_info.strip('/')))
		if not os.path.isfile(full_path):
			return canned_handlers('not_found', environ, start_response)

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
				return canned_handlers('not_modified', environ, start_response, headers=customHeaders)

			if_none = environ.get('HTTP_IF_NONE_MATCH')
			if if_none and (if_none == '*' or etag in if_none):
				return canned_handlers('not_modified', environ, start_response, headers=customHeaders)

			content_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
			customHeaders.append(('Content-Type', content_type))
			start_response("200 OK", customHeaders)
			return self._package_body(full_path, environ)
#		except:
#			return canned_handlers('not_found', environ, start_response)

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

#if __name__ == '__main__':
#	from wsgiref import simple_server
#	httpd = simple_server.WSGIServer(('',80),simple_server.WSGIRequestHandler)
#	httpd.set_app(StaticContentServer('\\tmp\\testgitrepo.git\\'))
#	httpd.serve_forever()
