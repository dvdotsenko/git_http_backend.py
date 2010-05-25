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
import urlparse
from cStringIO import StringIO
import subprocess

__version__=(1,7,0,4) # the number has no significance for this code's functionality.
# The number means "I was looking at sources of that version of Git while coding"

### Helper functions ###
def has_access(**kw):
	return True

def get_command_subprocess(commandline):
	"""
	 commandline - may be a string, or a list.
	 Returns:
	 Popen object with .communicate(), .stdin, .stdout, .stderr - file-like
	"""

	# CYGWIN likes to complain about non-POSYX paths unless the following is in the enviro:
	#  set CYGWIN=nodosfilewarning
	# Thus, additonal arguments to consider # cwd = workingpath, universal_newlines = True, custom environ.
	
	return subprocess.Popen(commandline, bufsize = 1,
		stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE)


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

		canned_handlers = environ.get('WSGIHandlerSelector.canned_handlers')

		query_string = urlparse.parse_qs(environ.get('QUERY_STRING') or '')
		git_command = ( query_string.get('service') or ['some trash'] )[0]
		# print "git command is %s\n" % git_command
		# if git_command[:4] != 'git-': # this would be better for future, when more commands are introduced.
		# in the mean time, will use this:
		if git_command not in ['git-upload-pack', 'git-receive-pack']:
			return canned_handlers('bad_request', environ, start_response)

		uri_sections = environ.get('WSGIHandlerSelector.matched_groups') or {}
		repo_path = uri_sections.get('working_path') or ''
		repo_path = os.path.abspath(os.path.join(self.path_prefix, repo_path.decode('utf8').strip('/')))

		try:
			files = set(os.listdir(repo_path))
		except:
			files = set()

		if not set(['config', 'HEAD', 'info','objects', 'refs']).issubset(files):
			return canned_handlers('not_found', environ, start_response)

		# print "repo path is determined to be %s\n" % repo_path

		if not has_access(
			environ = environ,
			repo_path = repo_path,
			git_command = git_command
			):
			return canned_handlers('access_denied', environ, start_response)

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
		start_response("200 OK", [('Content-type', 'application/x-%s-advertisement' % git_command)])
		return [ioObj.read()]

class RPCHandler(object):
	'''
	Implementation of a WSGI handler (app) specifically capable of responding
	to git-http-backend (Git Smart HTTP) RPC calls sent over HTTP POST.

	This is a layer that responds to HTTP POSTs to URIs like:
		/repo_folder_name/git-upload-pack?service=upload-pack (or same for receive-pack)

	This is a second step in the RPC dialog. Another handler for HTTP GETs to
	/repo_folder_name/info/refs (as implemented in a separate WSGI handler below)
	must reply in a specific way in order for the Git client to decide to talk here.
	'''
	def __init__(self, repo_fs_path):
		self.path_prefix = repo_fs_path

	def __call__(self, environ, start_response):
		"""
		WSGI Response producer for HTTP POST Git Smart HTTP requests.

		Reads commands and data from HTTP POST's body.

		returns an iterator obj with contents of git command's response to stdout
		"""


		start_response("200 Ok", [('Content-type', 'text/plain')])
		return ['']

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
	generic_handler = StaticWSGIServer(path_prefix, canned_handlers = canned_handlers)
	git_inforefs_handler = GitInfoRefsHandler(path_prefix)
#	git_rpc_handler = GitRPCHandler(path_prefix)

	## TESTING SETTINGS:
	from wsgiref import simple_server
#	app = simple_server.demo_app
#	selector.add('/vars/(?P<working_path>.*)$', app)

	if repo_uri_marker:
		marker_regex = r'(?P<decorative_path>.*?)(?:/'+ repo_uri_marker.decode('utf8') + ')'
	else:
		marker_regex = r''

	selector.add(marker_regex + '(?P<working_path>.*?)/info/refs\?.*?service=git-.*?$', GET = git_inforefs_handler, HEAD = git_inforefs_handler)
#	selector.add(marker_regex + '(?P<working_path>.*)/git-(?P<git_command>.+)$', POST = git_rpc_handler) # regex is "greedy" it will skip all cases of /git- until it finds last one.
	selector.add(marker_regex + '(?P<working_path>.*)$', GET = generic_handler, HEAD = generic_handler)
	# selector.add('^.*$', GET = generic_handler) # if none of the above yield anything, serve everything.

	return selector
