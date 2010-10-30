import os
import sys
import threading
import socket
import tempfile
import shutil
import random
import time
try:
    # 3.x style module
    import urllib.request as urlopenlib
except:
    # 2.x style module
    import urllib as urlopenlib

import git_http_backend
from cherrypy import wsgiserver

if sys.platform == 'cli':
    import subprocessio.subprocessio_ironpython as subprocess
else:
    import subprocess

def set_up_server(remote_base_path):
    # choosing free port
    s = socket.socket()
    s.bind(('',0))
    ip, port = s.getsockname()
    s.close()
    del s
    print("Chosen URL is http://%s:%s/" % (ip, port))
    # setting up the server.
    server = wsgiserver.CherryPyWSGIServer(
        (ip, port),
        git_http_backend.assemble_WSGI_git_app(remote_base_path)
        )
    ip = 'localhost' # the IP the socket yields is '0.0.0.0' which is not useful for testing.
    return ip, port, server

def test_smarthttp(url, base_path):
    # this tests roundtrip -
    # new repo > push up > clone down > push up > pull to original.
    repo_one_path = os.path.join(base_path, 'repoone')
    repo_two_path = os.path.join(base_path, 'repotwo')
    line_one = 'This is a test\n'
    line_two = 'Another line\n'
    file_name = 'testfile.txt'
    reponame = 'name%sname' % int(time.time())
    large_file_name = 'largetestfile.bin'
    # create local repo
    print("== creating first local repo and adding content ==")
    os.mkdir(repo_one_path)
    os.chdir(repo_one_path)
    subprocess.call('git init', shell=True)
    f = open(file_name, 'w')
    f.write(line_one)
    f.close()
    subprocess.call('git add %s' % file_name, shell=True)
    subprocess.call('git commit -m "Initial import"', shell=True)
    subprocess.call('git push http://%s/%s master' % (url, reponame), shell=True)
    os.chdir('..')
    # second local repo
    print("== cloning to second local repo and verifying content, adding more ==")
    subprocess.call('git clone http://%s/%s repotwo' % (url,reponame), shell=True)
    assert(os.path.isdir(repo_two_path))
    os.chdir(repo_two_path)
    assert(file_name in os.listdir('.'))
    lines = open(file_name).readlines()
    print "lines are %s" % lines
    assert(line_one in lines)
    lines.append(line_two)
    f = open(file_name, 'w')
    f.writelines(lines)
    f.close()
    f = open(large_file_name, 'wb')
    size = 1000000
    while size:
        f.write(chr(random.randrange(0,255)))
        size -= 1
    f.close()
    subprocess.call('git add %s %s' % (file_name, large_file_name), shell=True)
    subprocess.call('git commit -m "Changing the file"', shell=True)
    subprocess.call('git push origin master', shell=True)
    os.chdir('..')
    # back to original local repo
    print("== pulling to first local repo and verifying added content ==")
    os.chdir(repo_one_path)
    subprocess.call('git pull http://%s/%s master' % (url,reponame), shell=True)
    assert(set([file_name,large_file_name]).issubset(os.listdir('.')))
    assert(set([line_one,line_two]).issubset(open(file_name).readlines()))
    print("=============\n== SUCCESS ==\n=============\n")

def server_runner(s):
    try:
        s.start()
    except KeyboardInterrupt:
        pass
    finally:
        s.stop()

def server_and_client(base_path):
    remote_base_path = os.path.join(base_path, 'reporemote')
    ip, port, server = set_up_server(remote_base_path)    
    t = threading.Thread(None, server_runner, None, [server])
    t.daemon = True
    t.start()
    try:
        test_smarthttp('%s:%s' % (ip, port), base_path)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        shutil.rmtree(base_path, True)

def server_only(base_path):
    remote_base_path = os.path.join(base_path, 'reporemote')
    ip, port, server = set_up_server(remote_base_path)
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        shutil.rmtree(base_path, True)

def client_only(base_path, url):
    try:
        test_smarthttp(url, base_path)
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(base_path, True)

if __name__ == "__main__":
    base_path = tempfile.mkdtemp()
    print("base path is %s" % base_path)
    if '--client' in sys.argv:
        url = sys.argv[-1]
        client_only(base_path, url)
    elif '--server' in sys.argv:
        server_only(base_path)
    elif '--help' in sys.argv:
        print('Options: "--client url", "--server" Send no options for both server and client.')
    else:
        server_and_client(base_path)