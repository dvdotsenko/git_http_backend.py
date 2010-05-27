# -*- coding: utf8 -*-
#!/usr/bin/env python
'''
Module provides WSGI-based methods for handling HTTP Get and Post requests that
are specific only to git-http-backend's Smart HTTP protocol.

See __version__ statement below for indication of what version of Git's
Smart HTTP server this backend is (designed to be) compatible with.

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
import os
import os.path
from cStringIO import StringIO
import subprocess
import tempfile
import gzip
from wsgiref.headers import Headers

__version__=(1,7,0,4) # the number has no significance for this code's functionality.
# The number means "I was looking at sources of that version of Git while coding"

### Helper functions ###
def has_access(**kw):
	return True

def command_output(cmd, ioObj = StringIO()):
	'''
	Returns obj as IO and ExecutionError as boolean.
	'''
	print "This is the command:\n%s\n" % cmd

#	try:
	if True:
		c = subprocess.Popen(cmd, bufsize = 1, stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
#	except:
#		return ioObj, True

	while c.returncode == None:
		ioObj.write(c.communicate()[0])
	ioObj.write(c.communicate()[0])
	return ioObj, False

### Git-Specific Request Handlers ###

def basic_checks(dataObj, environ, start_response):
		'''
		This function is shared by GitInfoRefs and SmartHTTPRPCHandler WSGI classes.
		
		It does the same basic steps - figure out working path, git command etc.
		
		Returns non-None object if an error was triggered (and already prepared in start_response).
		Because the dataObj passed is mutable, it's passed as a pointer. Once this function returns,
		this object, as created by calling class, will have the updated data.
		'''
		canned_handlers = environ.get('WSGIHandlerSelector.canned_handlers')

		request_uri_elements = environ.get('WSGIHandlerSelector.matched_groups') or {}

		git_command = request_uri_elements.get('git_command') or ''
		if git_command not in ['git-upload-pack', 'git-receive-pack']: # TODO: this is bad for future compatibility. There may be more commands supported then.
			return canned_handlers('bad_request', environ, start_response)

		repo_path = request_uri_elements.get('working_path') or ''
		repo_path = os.path.abspath(os.path.join(dataObj['path_prefix'], repo_path.decode('utf8').strip('/')))
		try:
			files = set(os.listdir(repo_path))
		except:
			files = set()
		if not set(['config', 'HEAD', 'info','objects', 'refs']).issubset(files):
			return canned_handlers('not_found', environ, start_response)

		if not has_access(
			environ = environ,
			repo_path = repo_path,
			git_command = git_command
			):
			return canned_handlers('access_denied', environ, start_response)

		dataObj['git_command'] = git_command
		dataObj['repo_path'] = repo_path
		return None

class GitInfoRefsHandler(object):
	'''
	Implementation of a WSGI handler (app) specifically capable of responding
	to git-http-backend (Git Smart HTTP) /info/refs call over HTTP GET.

	This is the fist step in the RPC dialog. We have to reply with right content
	to show to Git client that we are an "intelligent" server.

	The "right" content is special header and custom top 2 rows of data in the response.
	'''
	def __init__(self, path_prefix):
		self.path_prefix = path_prefix.decode('utf8')

	def __call__(self, environ, start_response):
		"""WSGI Response producer for HTTP GET Git Smart HTTP /info/refs request."""

		dataObj = {'path_prefix':self.path_prefix}
		answer = basic_checks(dataObj, environ, start_response)
		if answer:
			return answer
		git_command = dataObj['git_command']
		repo_path = dataObj['repo_path']

		# note to self:
		# please, resist the urge to add '\n' everywhere and increment line count by 1.
		# The code in Git client not only does NOT need it, but actually blows up
		# if you sprinkle "flush" (0000) as "0001\n".
		# It reads binary, per number of bytes specified.
		# if you do add '\n' as part of data, count it.

		ioObj = StringIO()
		smart_server_advert = '# service=%s' % git_command
		ioObj.write(hex(len(smart_server_advert)+4)[2:].rjust(4,'0') + smart_server_advert)
 		ioObj.write('0000') 
		ioObj, err = command_output(
				r'git %s --stateless-rpc --advertise-refs "%s"' % (git_command[4:], repo_path)
				, ioObj
				)
		if err:
			return canned_handlers('execution_failed', environ, start_response)

		ioObj.reset()
		start_response("200 OK", [('Content-type', 'application/x-%s-advertisement' % str(git_command))])
		return [ioObj.read()]

class SmartHTTPRPCHandler(object):
	'''
	Implementation of a WSGI handler (app) specifically capable of responding
	to git-http-backend (Git Smart HTTP) RPC calls sent over HTTP POST.

	This is a layer that responds to HTTP POSTs to URIs like:
		/repo_folder_name/git-upload-pack?service=upload-pack (or same for receive-pack)

	This is a second step in the RPC dialog. Another handler for HTTP GETs to
	/repo_folder_name/info/refs (as implemented in a separate WSGI handler below)
	must reply in a specific way in order for the Git client to decide to talk here.
	'''
	def __init__(self, path_prefix):
		self.path_prefix = path_prefix
		self.block_size = 65536

	def __call__(self, environ, start_response):
		"""
		WSGI Response producer for HTTP POST Git Smart HTTP requests.

		Reads commands and data from HTTP POST's body.

		returns an iterator obj with contents of git command's response to stdout
		"""
		# 1. Determine git_command, repo_path
		# 2. Determine IN content (encoding)
		# 3. prepare OUT content (encoding, header)

		dataObj = {'path_prefix':self.path_prefix}
		answer = basic_checks(dataObj, environ, start_response)
		if answer:
			# this is a WSGI thing. basic_checks have already prepared the headers,
			# and a response body (which is the 'answer') is returned here.
			# presense of anythin of truthiness in 'answer' = some ERROR have
			# already prepared a response and all I need to do is let go of the response.
			return answer
		git_command = dataObj['git_command']
		repo_path = dataObj['repo_path']
		headers = [('Content-type', 'text/plain')]
		headersIface = Headers(headers)
		# i have a feeling that WSGI server is doing the un-gziping transparently ang gives the body unpacked.
		# my guess is that the response is gziped transparently as well. Will need to check.
		gzipped_output = False # bool( (environ.get('HTTP_ACCEPT_ENCODING') or '').find('gzip') > -1 )

		_l = int(environ.get('CONTENT_LENGTH') or 0)
		if _l > 327679:
			_max_size = 327679
		else:
			_max_size = _l + 128
		_i = environ.get('wsgi.input')
		_file_in = tempfile.SpooledTemporaryFile(max_size=_max_size, mode='w+b')
		_file_in.write(_i.read(_l))
		_i.close()
		_file_in.seek(0)

		_file_out = tempfile.SpooledTemporaryFile(max_size=327679, mode='w+b')
		if gzipped_output:
			_zfile = gzip.GzipFile(mode = 'wb',  fileobj = _file_out)
			_out = _zfile
		else:
			_out = _file_out

		_file_err = tempfile.SpooledTemporaryFile(max_size=12287, mode='wb')

		_cmd = 'git %s --stateless-rpc "%s"' % (git_command[4:], repo_path)
		_c = subprocess.Popen(_cmd, bufsize = 1, stdin = _file_in, stdout = _out, stderr = _file_err)
		while _c.returncode == None:
			trash = _c.communicate()
		trash = _c.communicate()
		del trash
		_file_in.close()
		del _file_in
		_file_err.close()
		del _file_err

		if gzipped_output:
			_zfile.close()
			headersIface['Content-Encoding'] = 'gzip'
		headersIface['Content-type'] = "application/x-%s-result" % git_command.encode('utf8')

		_file_out.seek(0)

		start_response("200 OK", headers)
		if 'wsgi.file_wrapper' in environ:
			return environ['wsgi.file_wrapper']( _file_out, self.block_size )
		else:
			return iter( lambda: file_like.read(self.block_size), '' )

def assemble_WSGI_git_app(path_prefix = '.', repo_uri_marker = ''):
	'''
	Assembles basic WSGI-compatible application providing functionality of git-http-backend.

	path_prefix (Defaults to '.' = "current" directory)
		The path to the folder that will be the root of served files. Accepts relative paths.

	repo_uri_marker (Defaults to '')
		Acts as a "virtual folder" separator between decorative URI portion and
		the actual (relative to path_prefix) path that will be appended to
		path_prefix and used for pulling an actual file.

		the URI does not have to start with contents of repo_uri_marker. It can
		be preceeded by any number of "virtual" folders. For --repo_uri_marker 'my'
		all of these will take you to the same repo:
			http://localhost/my/HEAD
			http://localhost/admysf/mylar/zxmy/my/HEAD
		This WSGI hanlder will cut and rebase the URI when it's time to read from file system.

		Default of '' means that no cutting marker is used, and whole URI after FQDN is
		used to find file relative to path_prefix.

	returns WSGI application instance.
	'''

	# local modules
	from StaticWSGIServer import StaticWSGIServer
	from WSGIHandlerSelector import WSGIHandlerSelector
	from WSGICannedHTTPHandlers import CannedHTTPHandlers

	canned_handlers = CannedHTTPHandlers()
	selector = WSGIHandlerSelector(canned_handlers = canned_handlers)
	generic_handler = StaticWSGIServer(path_prefix) #TODO Static server MimeTypes db needs to know about Git files.
	git_inforefs_handler = GitInfoRefsHandler(path_prefix)
	git_rpc_handler = SmartHTTPRPCHandler(path_prefix)

	from wsgiref import simple_server

	## TESTING SETTINGS:
#	app = simple_server.demo_app
#	selector.add('/vars/(?P<working_path>.*)$', app)

	if repo_uri_marker:
		marker_regex = r'(?P<decorative_path>.*?)(?:/'+ repo_uri_marker.decode('utf8') + ')'
	else:
		marker_regex = r''

	selector.add(marker_regex + r'(?P<working_path>.*?)/info/refs\?.*?service=(?P<git_command>git-[^&]+).*$', GET = git_inforefs_handler, HEAD = git_inforefs_handler)
	selector.add(marker_regex + r'(?P<working_path>.*)/(?P<git_command>git-[^/]+)$', POST = git_rpc_handler) # this regex is "greedy" it will skip all cases of /git- until it finds last one.
	selector.add(marker_regex + r'(?P<working_path>.*)$', GET = generic_handler, HEAD = generic_handler)

	return selector
