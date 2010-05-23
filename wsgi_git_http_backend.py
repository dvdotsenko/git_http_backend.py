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


	This file incorporates work covered by the following copyright and
	permission notice:

		(The MIT License)

		Copyright (c) 2009 Scott Chacon <schacon@gmail.com>

		Permission is hereby granted, free of charge, to any person obtaining
		a copy of this software and associated documentation files (the
		'Software'), to deal in the Software without restriction, including
		without limitation the rights to use, copy, modify, merge, publish,
		distribute, sublicense, and/or sell copies of the Software, and to
		permit persons to whom the Software is furnished to do so, subject to
		the following conditions:

		The above copyright notice and this permission notice shall be
		included in all copies or substantial portions of the Software.

		THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
		EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
		MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
		IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
		CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
		TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
		SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

# local modules
from StaticWSGIServer import StaticContentServer
from WSGISelector import Selector as WSGISelector
from GitHttpBackend import RPCHandler as GitRPCHandler, InfoRefsHandler as GitInfoRefsHandler

def show_session_vars(environ, start_response):
	'''
	Test code. Listing env variables.
	Taken from some tutorial.
	Will need to be gone later.
	'''
	status = '200 OK'
	headers = [('Content-type', 'text/plain')]
	start_response(status, headers)
	keys = environ.keys()
	keys.sort()
	ret = ["%s: %s\n" % (key, environ[key]) for key in keys]
	return ret

def get_WSGI_app(path_prefix = '.', repo_uri_marker = 'repos'):
	# path_prefix (example: r'/tmp'
	# this is the root filesystem folder for served files / content.

	# repo_uri_marker (example 'repos')
	# this is the keyword, after which the remaining URI path is considered
	# to be an actual repo or file path *relative* to path_prefix
	# Example: with repo_url_marker = 'repos'
	#  This regex '^.*?(?:/'+repo_url_marker+'/)(?P<detected_path>.*)$'
	#  turns this: '/asdf/repos/zxcv/qwer/repos/asdf/zxvc.xyz'
	#  into 'zxcv/qwer/repos/asdf/zxvc.xyz' (note, we ignore subsequent occurance of 'repos'
	# File path in this case would expected to be:
	#  path_prefix + / + zxcv/qwer/repos/asdf/zxvc.xyz

	git_rpc_handler = GitRPCHandler(path_prefix)
	git_inforefs_handler = GitInfoRefsHandler(path_prefix)
	generic_handler = StaticContentServer(path_prefix)
	# app = show_session_vars

	# Test code for Selector middleware.
	selector = WSGISelector()
	selector.parser = lambda x: x
	# selector.prefix = '/custom/prefix'
	selector.add('^.*?(?:/'+repo_uri_marker+'/)(?P<working_path>.*)/git-(?P<git_command>.+)$', {'POST':git_rpc_handler})
	selector.add('^.*?(?:/'+repo_uri_marker+'/)(?P<working_path>.*)/info/refs$', {'GET':git_inforefs_handler})
	selector.add('^.*?(?:/'+repo_uri_marker+'/)(?P<working_path>.*)$', {'GET':generic_handler})

	return selector

if __name__ == "__main__":

	# default Python's WSGI server. Replace with your choice of WSGI server
	from wsgiref import simple_server
	#from wsgiref.validate import validator
	## use as wsgiapp = validator(app)

	httpd = simple_server.WSGIServer(('',80),simple_server.WSGIRequestHandler)
	httpd.set_app(get_WSGI_app(path_prefix = r'\tmp', repo_uri_marker = 'repos'))
	httpd.serve_forever()
