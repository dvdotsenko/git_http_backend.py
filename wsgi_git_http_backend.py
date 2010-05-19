#!/usr/bin/env python
'''
#
#	Copyright (c) 2010  Daniel Dotsenko <dotsa@hotmail.com>
#
#	This file is part of git_http_backend.py Project.
#
#    git_http_backend.py Project is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 2.1 of the License, or
#    (at your option) any later version.
#
#    git_http_backend.py Project is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
'''


from wsgiref import simple_server
from cStringIO import StringIO # for custom iterator
import selector

# Test code. Listing env variables. Taken from some tutorial. Will need to be gone.
#def simple_app(environ, start_response):
#	setup_testing_defaults(environ)
#	status = '200 OK'
#	headers = [('Content-type', 'text/plain')]
#	start_response(status, headers)
#	keys = environ.keys()
#	keys.sort()
#	ret = ["%s: %s\n" % (key, environ[key]) for key in keys]
#	return ret

class git_http_backend():
	def __init__(self):
		pass

	def __call__(self, environ, start_response):
		length= int(environ.get('CONTENT_LENGTH', '0') or '0')
		body= StringIO()
		body.write(environ['wsgi.input'].read(length))
		body.write('\nLast line\n')
		# environ['wsgi_input'] = body
		body.seek(0)
		start_response("200 Ok", [('Content-type', 'text/plain')])
		return body

app = FooApp('teststring')

## Test code for Selector middleware.
#	s = selector.Selector()
#	s.parser = lambda x: x
#	# s.prefix = '/myapp'
#	s.add('^/(?P<name>.*)$', {'GET':app, 'POST':app})

httpd = simple_server.WSGIServer(('',80),simple_server.WSGIRequestHandler)
httpd.set_app(git_http_backend())
httpd.serve_forever()
