# -*- coding: utf8 -*-
#!/usr/bin/env python
'''
Module provides WSGI-based methods for handling HTTP Get and Post requests that
are specific only to git-http-backend's Smart HTTP protocol.

See __version__ statement below for indication of what version of Git's
Smart HTTP server this backend is (designed to be) compatible with.

Copyright (c) 2010  Daniel Dotsenko <dotsa@hotmail.com>
Selected, specifically marked so classes are also
  Copyright (C) 2006 Luke Arno - http://lukearno.com/

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
import os.path

import os
import subprocess
import tempfile
import gzip
from wsgiref.headers import Headers

# needed for WSGI Selector
import re
import urlparse
from collections import defaultdict

# needed for static content server
import time
import email.utils
import mimetypes
mimetypes.add_type('application/x-git-packed-objects-toc','.idx')
mimetypes.add_type('application/x-git-packed-objects','.pack')

__version__=(1,7,0,4) # the number has no significance for this code's functionality.
# The number means "I was looking at sources of that version of Git while coding"

class BaseWSGIClass(object):

	tmp_file_buffer_size = 32767 # bytes. boundary between memory-resident and file-swapped tempfile.
	block_size = 65536
	gzip_response = False
	canned_collection = {
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

	def canned_handlers(self, environ, start_response, code = '200', headers = []):
		'''
		We convert an error code into
		certain action over start_response and return a WSGI-compliant payload.
		'''
		headerbase = [('Content-Type', 'text/plain')]
		if headers:
			hObj = Headers(headerbase)
			for header in headers:
				hObj[header[0]] = '; '.join(header[1:])
		start_response(self.canned_collection[code], headerbase)
		return ['']

	def package_response(self, outIO, environ, start_response, headers = []):

		newheaders = headers
		headers = [('Content-type', 'application/octet-stream')] # my understanding of spec. If unknown = binary
		headersIface = Headers(headers)

		for header in newheaders:
			headersIface[header[0]] = '; '.join(header[1:])

		# Per PEP333:
		# "Similarly, a server may re-encode or transport-encode an application's response,
		#  but the application should use a suitable *CONTENT* encoding on its own,
		#  and must not apply a transport encoding."
		#
		# However, later it says:
		# "(Note: applications and middleware must not apply any kind of Transfer-Encoding
		#  to their output, such as chunking or *GZIPPING*; as "hop-by-hop" operations,
		#  these encodings are the province of the actual web server/gateway."
		#
		# These two statements may be read as "we consider GZIPPING a domain of server,
		#  despite of it being a "Content-Encoding" and not "Transfer-Encoding""
		#
		# i have a feeling that respectible WSGI server will be doing the un-gziping
		# of the incoming request body transparently ang gives the body unpacked.
		#
		# However, depending on WSGI server, response could be gziped transparently as well or not.
		# By default, we will forego compression here... Enable it by flipping the gzip_response to True
		#  For intrAnet deployments, i wouldn't bother with it, as it eats up response and CPU time.

		# also. I would love to feed the gzipIO obj as subprocess input pipe directly so
		# that i would not have to relocate data from tempfile to gzip temp file, but
		# subprocess.Popen(... stdout = gzIO, ...) spills both, compressed and uncompressed
		# command output into gzIO's underlying fileno. Ugh! You just can't do the right thing around here...
		if self.gzip_response and bool( (environ.get('HTTP_ACCEPT_ENCODING') or '').find('gzip') > -1 ):
			outIO.seek(0,2)
			if outIO.tell() > 1024:
				_file_out = tempfile.SpooledTemporaryFile(max_size=self.tmp_file_buffer_size, mode='w+b')
				_zfile = gzip.GzipFile(mode = 'wb',  fileobj = _file_out)
				outIO.seek(0)
				_zfile.writelines(outIO)
				_zfile.close()
				outIO.close()
				outIO = _file_out
				headersIface['Content-Encoding'] = 'gzip'

		outIO.seek(0)

		start_response("200 OK", headers)
		if 'wsgi.file_wrapper' in environ:
			return environ['wsgi.file_wrapper']( outIO, self.block_size )
		else:
			return iter( lambda: outIO.read(self.block_size), '' )

class WSGIHandlerSelector(BaseWSGIClass):
	"""
	WSGI middleware for URL paths and HTTP method based delegation.

	Based on Selector from http://lukearno.com/projects/selector/

	Copyright (c) 2010 Daniel Dotsenko <dotsa@hotmail.com>
	Copyright (C) 2006 Luke Arno - http://lukearno.com/
	"""

	def __init__(self, WSGI_env_key = 'WSGIHandlerSelector'):
		"""
		WSGIHandlerSelector instance initializer.

		WSGIHandlerSelector(WSGI_env_key = 'WSGIHandlerSelector')

		Inputs:
		 WSGI_env_key (optional) (must be named arg)
		  name of the key selector injects into WSGI's environ.
		  The key will be the base for other dicts, like .matches - the key-value pairs of
		  name-matchedtext matched groups. Defaults to 'WSGIHandlerSelector'
		"""
		self.mappings = []
		self.WSGI_env_key = WSGI_env_key

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

			return handler(environ, start_response)
		elif alternate_HTTP_verbs:
			# uugh... narrow miss. Regex matched some path, but the method was off.
			# let's advertize what methods we can do with this URI.
			return self.canned_handlers(
				environ,
				start_response,
				'method_not_allowed',
				headers = [('Allow', ', '.join(alternate_HTTP_verbs))]
				)
		else:
			return self.canned_handlers(environ, start_response, 'not_found')

class StaticWSGIServer(BaseWSGIClass):
	"""
	Copyright (c) 2010  Daniel Dotsenko <dotsa@hotmail.com>
	Copyright (C) 2006 Luke Arno - http://lukearno.com/

	A simple WSGI-based static content server app.

	Relies on WSGIHandlerSelector for prepopulating some needed environ
	variables, cleaning up the URI, setting up default error handlers.
	"""

	def __init__(self, **kw):
		'''
		Inputs:
			path_prefix (mandatory)
				String containing a file-system level path behaving as served root.

			block_size (optional)
				File reader's buffer size. Defaults to 65536.

			gzip_response (optional) (must be named arg)
				Specify if we are to detect if gzip compression is supported
				by client and gzip the output. False by default.
		'''
		self.__dict__.update(kw)

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
		full_path = os.path.abspath(os.path.join(self.path_prefix, path_info.strip('/')))
		_pp = os.path.abspath(self.path_prefix)

		if not full_path.startswith(_pp):
			return self.canned_handlers(environ, start_response, 'forbidden')
		if not os.path.isfile(full_path):
			return self.canned_handlers(environ, start_response, 'not_found')

		mtime = os.stat(full_path).st_mtime
		etag, last_modified =  str(mtime), email.utils.formatdate(mtime)
		headers = [
			('Content-type', 'text/plain'),
			('Date', email.utils.formatdate(time.time())),
			('Last-Modified', last_modified),
			('ETag', etag)
		]
		headersIface = Headers(headers)
		if_modified = environ.get('HTTP_IF_MODIFIED_SINCE')
		if if_modified and (email.utils.parsedate(if_modified) >= email.utils.parsedate(last_modified)):
			return self.canned_handlers(environ, start_response, 'not_modified', headers)
		if_none = environ.get('HTTP_IF_NONE_MATCH')
		if if_none and (if_none == '*' or etag in if_none):
			return self.canned_handlers(environ, start_response, 'not_modified', headers)

		headersIface['Content-Type'] = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
		file_like = open(full_path, 'rb')
		return self.package_response(self, file_like, environ, start_response, headers)

class GitHTTPBackendBase(BaseWSGIClass):
	git_folder_signature = set(['config', 'head', 'info', 'objects', 'refs'])
	repo_auto_create = False

	def has_access(self, **kw):
		'''
		User rights verification code.
		(This is NOT an authentication code. The authentication is handled by
		the server that hosts this WSGI app. We just go by the name of the
		already-authenticated user.
		'''
		return True

	def get_command_output(self, cmd,
			stdin = None,
			stdout = None,
			stderr = None
			):
		'''
		command_output(cmd,stdin,stdout,stderr)

		stdin,stdout,stderr (optional)
		 FileIO-like objects. Default tempfile.SpooledTemporaryFile()

		Returns rewound IO-like object with output, errorOut fileIO-like object
		and a command exit code
		'''

		if not stdin:
			stdin = tempfile.SpooledTemporaryFile(max_size=256, mode='w+b')
			_internal_stdin = True
		else:
			_internal_stdin = False

		if not stdout:
			stdout = tempfile.SpooledTemporaryFile(max_size=self.tmp_file_buffer_size, mode='w+b')

		if not stderr:
			stderr = tempfile.SpooledTemporaryFile(max_size=8192, mode='w+b')

		_c = subprocess.Popen(cmd, bufsize = 1, stdin = stdin, stdout = stdout, stderr = stderr)
		_return_code = _c.wait()
		if _internal_stdin:
			stdin.close()
			del stdin
		return stdout, stderr, _return_code

	def basic_checks(self, dataObj, environ, start_response):
		'''
		This function is shared by GitInfoRefs and SmartHTTPRPCHandler WSGI classes.
		It does the same basic steps - figure out working path, git command etc.

		dataObj - dictionary
		Because the dataObj passed in is mutable, it's a pointer. Once this function returns,
		this object, as created by calling class, will have the free-form updated data.

		Returns non-None object if an error was triggered (and already prepared in start_response).
		'''
		selector_matches = (environ.get('wsgiorg.routing_args') or ([],{}))[1]

		# making sure we have a compatible git command
		git_command = selector_matches.get('git_command') or ''
		if git_command not in ['git-upload-pack', 'git-receive-pack']: # TODO: this is bad for future compatibility. There may be more commands supported then.
			return self.canned_handlers(environ, start_response, 'bad_request')

		# TODO: Add "public" to "dynamic local" path conversion hook ups here.

		#############################################################
		# making sure local path is a valid git repo folder
		#
		repo_path = os.path.abspath(
			os.path.join(
				self.path_prefix,
				(selector_matches.get('working_path') or '').decode('utf8').strip('/').strip('\\')
				)
			)
		_pp = os.path.abspath(self.path_prefix)
		
		# this saves us from "hackers" putting relative paths after repo marker.
		if not repo_path.startswith(_pp):
			return self.canned_handlers(environ, start_response, 'forbidden')

		if not self.has_access(
			environ = environ,
			repo_path = repo_path,
			git_command = git_command
			):
			return self.canned_handlers(environ, start_response, 'forbidden')

		try:
			files = os.listdir(repo_path)
		except:
			files = []
		if not self.git_folder_signature.issubset([i.lower() for i in files]):
			if not ( self.repo_auto_create and git_command == 'git-receive-pack' ):
				return self.canned_handlers(environ, start_response, 'not_found')
			else:
				# 1. traverse entire post-prefix path and check that each segment
				#    If it is ( a git folder OR a non-dir object ) forbid autocreate
				# 2. Create folderS
				# 3. Activate a bare git repo
				_pf = _pp
				_dirs = repo_path[len(_pp):].strip(os.sep).split(os.sep) or ['']
				for _dir in _dirs:
					_pf = os.path.join(_pf,_dir)
					if not os.path.exists(_pf):
						try:
							os.makedirs(repo_path)
						except:
							return self.canned_handlers(environ, start_response, 'not_found')
						break
					elif not os.path.isdir(_pf) or self.git_folder_signature.issubset([i.lower() for i in os.listdir(_pf)]):
						return self.canned_handlers(environ, start_response, 'forbidden')
				if subprocess.call('git init --quiet --bare "%s"' % repo_path):
					return self.canned_handlers(environ, start_response, 'execution_failed')
		#
		#############################################################

		dataObj['git_command'] = git_command
		dataObj['repo_path'] = repo_path
		return None

class GitInfoRefsHandler(GitHTTPBackendBase):
	'''
	Implementation of a WSGI handler (app) specifically capable of responding
	to git-http-backend (Git Smart HTTP) /info/refs call over HTTP GET.

	This is the fist step in the RPC dialog. We have to reply with right content
	to show to Git client that we are an "intelligent" server.

	The "right" content is special header and custom top 2 rows of data in the response.
	'''
	def __init__(self, **kw):
		'''
		inputs:
			path_prefix (Mandatory) - Local file system path = root of served files.
			block_size (Default = 65536) Chunk size for WSGI file feeding
			gzip_response (Default = False) Compress response body
		'''
		self.__dict__.update(kw)

	def __call__(self, environ, start_response):
		"""WSGI Response producer for HTTP GET Git Smart HTTP /info/refs request."""

		dataObj = {}
		answer = self.basic_checks(dataObj, environ, start_response)
		if answer:
			# non-Null answer = there was an issue in basic_checks and it's time to return an HTTP error response
			return answer
		git_command = dataObj['git_command']
		repo_path = dataObj['repo_path']

		# note to self:
		# please, resist the urge to add '\n' to git capture and increment line count by 1.
		# The code in Git client not only does NOT need '\n', but actually blows up
		# if you sprinkle "flush" (0000) as "0001\n".
		# It reads binary, per number of bytes specified.
		# if you do add '\n' as part of data, count it.
		stdout = tempfile.SpooledTemporaryFile(max_size=self.tmp_file_buffer_size, mode='w+b')
		smart_server_advert = '# service=%s' % git_command
		stdout.write(hex(len(smart_server_advert)+4)[2:].rjust(4,'0') + smart_server_advert)
 		stdout.write('0000')

		stdout, stderr, exit_code = self.get_command_output(
				r'git %s --stateless-rpc --advertise-refs "%s"' % (git_command[4:], repo_path)
				, stdin = -1
				, stdout=stdout
				, stderr = -1
				)
		headers = [('Content-type','application/x-%s-advertisement' % str(git_command))]

		if exit_code: # non-zero value = error
			stdout.close()
			return self.canned_handlers(environ, start_response, 'execution_failed')
		return self.package_response(stdout, environ, start_response, headers)

class SmartHTTPRPCHandler(GitHTTPBackendBase):
	'''
	Implementation of a WSGI handler (app) specifically capable of responding
	to git-http-backend (Git Smart HTTP) RPC calls sent over HTTP POST.

	This is a layer that responds to HTTP POSTs to URIs like:
		/repo_folder_name/git-upload-pack?service=upload-pack (or same for receive-pack)

	This is a second step in the RPC dialog. Another handler for HTTP GETs to
	/repo_folder_name/info/refs (as implemented in a separate WSGI handler below)
	must reply in a specific way in order for the Git client to decide to talk here.
	'''
	def __init__(self, **kw):
		'''
		path_prefix
			Local file system path = root of served files.
		optional parameters may be passed as named arguments
			These include
				block_size (Default = 65536) Chunk size for WSGI file feeding
				gzip_response (Default = False) Compress response body
		'''
		self.__dict__.update(kw)

	def __call__(self, environ, start_response):
		"""
		WSGI Response producer for HTTP POST Git Smart HTTP requests.
		Reads commands and data from HTTP POST's body.
		returns an iterator obj with contents of git command's response to stdout
		"""
		# 1. Determine git_command, repo_path
		# 2. Determine IN content (encoding)
		# 3. prepare OUT content (encoding, header)

		dataObj = {}
		answer = self.basic_checks(dataObj, environ, start_response)
		if answer:
			# this is a WSGI "trick". basic_checks have already prepared the headers,
			# and a response body (which is the 'answer') returned here.
			# presense of anything of truthiness in 'answer' = some ERROR have
			# already prepared a response and all I need to do is let go of the response.
			return answer
		git_command = dataObj['git_command']
		repo_path = dataObj['repo_path']

		# transferring the contents of HTML request body into a temp file.
		#  You might be thinking "why not just pass the wsgi.input IO object as stdin?"
		#  All IO objects, except for real STDIN must have filename property for
		#  subprocess.Popen() to work. When / if that's fixed, you could try passing wsgi.input 
		#  direcltly to subprocess.Popen() as stdin
		_l = int(environ.get('CONTENT_LENGTH') or 0)
		if _l > self.tmp_file_buffer_size or _l == -1:
			_max_size = self.tmp_file_buffer_size
		else:
			_max_size = _l + 128
		_i = environ.get('wsgi.input')
		stdin = tempfile.SpooledTemporaryFile(max_size=_max_size, mode='w+b')
		stdin.write(_i.read(_l))
		stdin.seek(0)

		stdout, stderr, exit_code = self.get_command_output(
				r'git %s --stateless-rpc "%s"' % (git_command[4:], repo_path)
				, stdin = stdin
				, stderr = -1
				)
		stdin.close()
		del stdin

		if exit_code: # non-zero value = error
			stdout.close()
			return self.canned_handlers(environ, start_response, 'execution_failed')
		elif git_command in [u'git-receive-pack']:
			# updating refs manually after each push. Needed for pre-1.7.0.4 git clients using regular HTTP mode.
			subprocess.call(u'git --git-dir "%s" update-server-info' % repo_path)

		headers = [('Content-type', 'application/x-%s-result' % git_command.encode('utf8'))]
		return self.package_response(stdout, environ, start_response, headers)

def assemble_WSGI_git_app(path_prefix = '.', repo_uri_marker = '', performance_settings = {}):
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

	repo_uri_marker = repo_uri_marker.decode('utf8')
	path_prefix = path_prefix.decode('utf8')
	settings = {"path_prefix": path_prefix.decode('utf8')}
	settings.update(performance_settings)

	selector = WSGIHandlerSelector()
	generic_handler = StaticWSGIServer(**settings)
	git_inforefs_handler = GitInfoRefsHandler(**settings)
	git_rpc_handler = SmartHTTPRPCHandler(**settings)

	if repo_uri_marker:
		marker_regex = r'(?P<decorative_path>.*?)(?:/'+ repo_uri_marker + ')'
	else:
		marker_regex = ''

	selector.add(
		marker_regex + r'(?P<working_path>.*?)/info/refs\?.*?service=(?P<git_command>git-[^&]+).*$',
		GET = git_inforefs_handler,
		HEAD = git_inforefs_handler
		)
	selector.add(
		marker_regex + r'(?P<working_path>.*)/(?P<git_command>git-[^/]+)$',
		POST = git_rpc_handler
		) # warning: this regex is "greedy" it will skip all cases of /git- until it finds last one.
	selector.add(
		marker_regex + r'(?P<working_path>.*)$',
		GET = generic_handler,
		HEAD = generic_handler)

	return selector

if __name__ == "__main__":
	_help = '''
Options:
--path_prefix (Defaults to '.' - current directory)
	Serving contents of folder path passed in. Accepts relative paths,
	including things like "./../" and resolves them agains current path.

	If you set this to actual .git folder, you don't need to specify the
	folder's name on URI.

--repo_uri_marker (Defaults to '')
	Acts as a "virtual folder" - separator between decorative URI portion
	and the actual (relative to path_prefix) path that will be appended
	to path_prefix and used for pulling an actual file.

	the URI does not have to start with contents of repo_uri_marker. It can
	be preceeded by any number of "virtual" folders.
	For --repo_uri_marker 'my' all of these will take you to the same repo:
		http://localhost/my/HEAD
		http://localhost/admysf/mylar/zxmy/my/HEAD
	If you are using reverse proxy server, pick the virtual, decorative URI
	prefix / path of your choice. This hanlder will cut and rebase the URI.

	Default of '' means that no cutting marker is used, and whole URI after
	FQDN is used to find file relative to path_prefix.

--port (Defaults to 80)

Examples:

./this_file.py --path_prefix ".."
	Will serve the folder above the parent_folder in which this_file.py
	is located. A functional url could be
	 http://localhost/parent_folder/this_file.py

~/myscripts/this_file.py --path_prefix "./.git" --repo_uri_marker "myrepo"
	Will serve chosen .git folder as http://localhost/myrepo/ or
	http://localhost/does/not/matter/what/you/type/here/myrepo/

	'''
	import os
	import sys

	command_options = {
			'path_prefix' : '.',
			'repo_uri_marker' : '',
			'port' : '80'
		}

	lastKey = None
	for item in sys.argv:
		if item.startswith('--'):
			command_options[item[2:]] = True
			lastKey = item[2:]
		elif lastKey:
			command_options[lastKey] = item.strip('"').strip("'")
			lastKey = None

	path_prefix = os.path.abspath( command_options['path_prefix'] )

	app = assemble_WSGI_git_app(
			path_prefix = path_prefix,
			repo_uri_marker = command_options['repo_uri_marker'],
			performance_settings = {
				'repo_auto_create':True,
				'gzip_response':False
				}
		)

	# default Python's WSGI server. Replace with your choice of WSGI server
	from wsgiref import simple_server
	httpd = simple_server.make_server('',int(command_options['port']),app)

	if 'help' in command_options:
		print _help
	else:
		if command_options['repo_uri_marker']:
			_s = 'url fragment "/%s/"' % command_options['repo_uri_marker']
		else:
			_s = 'nothing.'
		print '''
Starting git-http-backend server...
	Port: %s
	Base file system path: %s
	Repo url must be prefixed by %s''' % (command_options['port'], path_prefix, _s)
		try:
			httpd.serve_forever()
		except KeyboardInterrupt:
			pass