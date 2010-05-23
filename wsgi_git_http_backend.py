#!/usr/bin/env python
'''
Basic WSGI-based server designed to act as a replaceement for 
git-http-backend (Git "Smart HTTP") server.

====================================================

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

def get_WSGI_app(path_prefix = '.', repo_uri_marker = ''):
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
	from StaticWSGIServer import StaticContentServer
	from WSGISelector import Selector as WSGISelector
	from GitHttpBackend import RPCHandler as GitRPCHandler, InfoRefsHandler as GitInfoRefsHandler

	git_rpc_handler = GitRPCHandler(path_prefix)
	git_inforefs_handler = GitInfoRefsHandler(path_prefix)
	generic_handler = StaticContentServer(path_prefix)

	# Test code for Selector middleware.
	selector = WSGISelector()
	selector.parser = lambda x: x

	if repo_uri_marker:
		marker_regex = '^(?P<decorative_path>.*?)(?:/'+ repo_uri_marker.decode('utf8') + '/)'
	else:
		marker_regex = ''
	selector.add(marker_regex + '(?P<working_path>.*)/git-(?P<git_command>.+)$', {'POST':git_rpc_handler}) # regex is "greedy" it will skip all cases of /git- until it finds last one.
	selector.add(marker_regex + '(?P<working_path>.*)/info/refs$', {'GET':git_inforefs_handler})
	selector.add(marker_regex + '(?P<working_path>.*)$', {'GET':generic_handler})
	# selector.add('^.*$', {'GET':simple_server.demo_app})
	# selector.add('^.*$', {'GET':generic_handler}) # if none of the above yield anything, serve everything.

	return selector

def get_cmd_options(options = {}):
	'''
	Very basic command-line options parser

	Only supports "--"-prefixed options, either with argument over a space, or
	stand-alone. Example:
	command "this is ignored" --switch1 --key1 "long argument1" --key2 argument2 --switch2
	'''
	import sys
	lastKey = None

	for item in sys.argv:
		if item.startswith('--'):
			options[item[2:]] = True
			lastKey = item[2:]
		elif lastKey:
			options[lastKey] = item.strip('"').strip("'")
			lastKey = None
	return options

if __name__ == "__main__":
	'''
	Options:
	--path_prefix (Defaults to '.' - current directory)
		Serving contents of folder path passed in. Accepts relative paths,
		including things like "./../" and resolves them agains current path.

	--repo_uri_marker (Defaults to '')
		Acts as a "virtual folder" - separator between decorative URI portion and
		the actual (relative to path_prefix) path that will be appended to
		path_prefix and used for pulling an actual file.

		the URI does not have to start with contents of repo_uri_marker. It can
		be preceeded by any number of "virtual" folders. For --repo_uri_marker 'my'
		all of these will take you to the same repo:
			http://localhost/my/HEAD
			http://localhost/admysf/mylar/zxmy/my/HEAD
		If you are using reverse proxy server, pick the visrtual, decorative URI
		prefix / path of your choice. This WSGI hanlder will cut and rebase the URI.

		Default of '' means that no cutting marker is used, and whole URI after FQDN is
		used to find file relative to path_prefix.

	--port (Defaults to 80)

	Examples:
	./this_file.py --path_prefix ".."
		Will serve the folder above the parent_folder in which this_file.py is located.
		A functional url could be http://localhost/parent_folder/this_file.py

	~/myscripts/this_file.py --path_prefix "./.git" --repo_uri_marker "myrepo"
		Will serve chosen .git folder as http://localhost/myrepo/

	'''
	import os

	command_options = get_cmd_options({
			'path_prefix' : r'.',
			'repo_uri_marker' : '',
			'port' : '80'
		}) # this is where defaults are defined.

	path_prefix = os.path.abspath( command_options['path_prefix'] )

	# this is only needed to ensura that we can load local modules.
	exec_path = '.'
	if '__file__' in dir():
		if __file__:
			exec_path = os.path.dirname(__file__)
	os.chdir(os.path.abspath(exec_path))

	# default Python's WSGI server. Replace with your choice of WSGI server
	from wsgiref import simple_server
	#from wsgiref.validate import validator
	## use as wsgiapp = validator(app)

	app = get_WSGI_app(
			path_prefix = path_prefix,
			repo_uri_marker = command_options['repo_uri_marker']
		)
	# app = simple_server.demo_app

	httpd = simple_server.make_server('',int(command_options['port']),app)
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		pass