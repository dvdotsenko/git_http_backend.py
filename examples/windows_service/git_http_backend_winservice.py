"""
The most basic (working) CherryPy 3.2 WSGI Windows service possible.
Requires Mark Hammond's pywin32 package.

Taken from here: http://tools.cherrypy.org/wiki/WindowsService and modified.
License and copyright unknown. No licence or warranty claimed on my behalf. 
Inquire with source mentioned above regarding either.

To see a list of options for installing, removing, starting, and stopping your service.
    python this_file.py
To install your new service type:
    python this_file.py install
Then type:
    python this_file.py start

If you get "Access Denied" you need to be admin to install, remove, start, stop.
    ( To run cmd as admin: Windows Key > "cmd" > CTRL+SHIFT+ENTER )
"""
import os.path
import shutil
import tempfile
import win32serviceutil
import win32service

import sys
import os
# this allows the winservice.py script to see modules in project's root folder.
# if you get "cannot find 'module name'" errors, change "." to actual
# path where git_http_backend.py is located.
sys.path.append(os.path.abspath("."))

import git_http_backend
from cherrypy import wsgiserver

class GitSmartHTTPServer(win32serviceutil.ServiceFramework):
# class GitSmartHTTPServer(object):
    """NT Service."""

    _svc_name_ = "GitSmartHTTPServer"
    # note: we are defining an extended description lower in the class.

    _server_ip = '0.0.0.0' # '0.0.0.0' means "all address on this server"
    '''Ip or name of the server hosting this git smart http service.'''

    _server_port = 8888
    '''The port on which this Git Smart HTTP server will listen on'''

    _path_prefix = "CHANGE ME!"
    '''This is the "start" of the physical path that will be exposed as
    the root folder for all repo folder references.

    If you already have a folder on your drive that has all the repo folders,
    this (or some folder above it) is the the folder you would like to 
    set the _path_prefix to.

    You need to escape backslashes or use Python's "r" marker to declare 
    "read this string liteterally". Examples: "c:\\temp" , r"c:\temp"

    Example:
        if _path_prefix = c:\our_repos_root
        URI http://server:port/userjoe/joes_repo_one.git
        Would mean to reference an actual folder:
            c:\our_repos_root\userjoe\joes_repo_one.git

    Until you change it to something real, we will be creating repos in
    temp folder of our choice and removing all repos when service stops.
    '''

    _repo_uri_marker = "" # Example: "myprojects"
    '''This is a label that server will look for in the URI to determine
    which portion of the URI refers to the start of actual repo folder structures.

    The marker is not a physical file-system path, and is purely a flag that says
    to the git server "after this, the remaining URI is what you have to care about"

    If this arg is not set, server assumes that the name of the physical path
    to repo folder relative to _path_prefix starts immediately after first slash.
    Example:
        if _path_prefix = c:\tmp\our_repos_root
        URI http://server:port/userjoe/joes_repo_one.git
        Would mean to reference an actual phisical folder:
            c:\tmp\our_repos_root\userjoe\joes_repo_one.git

    URI marker is useful in specific cases when it's important to have the git
    server host the app on a non-root folder.
    (Example, _repo_uri_marker was set to "myrepos" vs. "":
        http://server/any/random/pre-path/here/myrepos/repofoler.git
        vs. http://server/repofoler.git)

    This functionality is important for cases when this Git Smart HTTP server
    is hiding behind a reverse proxy (IIS's ApplicationRequestRouting, nginx etc.)
    and you want an easy way to "mount" this git server on top of present site
    structure, while still hosting this server on a separate machine or port.

    One word of caution about reverse proxy, though. This server and the git client
    talk HTTP/1.1, chunked bodies, once the pack size goes up above 1Mb.
    For efficiency of communication, please, try to stick to fully HTTP/1.1
    compliant reverse proxies. NGINX is only HTTP/1.0 on the inside of reverse
    proxy. HTTP/1.0 proxies are not a deal-breaker, but, test and retest them
    before going production.
    '''

    if not _path_prefix or _path_prefix == "CHANGE ME!":
        _path_prefix = tempfile.mkdtemp()
        _using_temporary_folder = ', repo dir will self-destruct'
    else:
        _using_temporary_folder = ''

    if _repo_uri_marker:
        _s = ', URI marker "/%s/"' % _repo_uri_marker
    else:
        _s = ', no URI marker'
    _svc_display_name_ = "Git Smart HTTP Server - port %s%s%s." % (
            _server_port, _s, _using_temporary_folder)

    _server_instance = None

    def SvcDoRun(self):

        app = git_http_backend.assemble_WSGI_git_app(
            path_prefix = self._path_prefix,
            repo_uri_marker = self._repo_uri_marker
            # on push, nonexistent repos are autocreated by default.
            # uncomment 3 lines below to stop that.
#            , performance_settings = {
#                'repo_auto_create':False
#                }
        )
        self._server_instance = wsgiserver.CherryPyWSGIServer(
                (self._server_ip, self._server_port),
                app
            )
        try:
            self._server_instance.start()
        except KeyboardInterrupt:
            # i know this will never happen. That's the point.
            # all other exceptions will bubble up, somewhere... i hope...
            pass
        finally:
            self._server_instance.stop()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._server_instance:
            self._server_instance.stop()
        if self._using_temporary_folder:
            shutil.rmtree(self._path_prefix, True)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)
        # very important for use with py2exe
        # otherwise the Service Controller never knows that it is stopped !

if __name__ == '__main__':
    # s = GitSmartHTTPServer()
    # s.SvcDoRun()
    win32serviceutil.HandleCommandLine(GitSmartHTTPServer)
