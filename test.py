import sys
import git_http_backend.GitHttpBackend
import wsgiref.simple_server
import threading
import subprocess
import socket
import tempfile
import shutil
try:
    # 3.x style module
    import urllib.request as urlopenlib
except:
    # 2.x style module
    import urllib as urlopenlib
import os

# these are needed only for occasions when server runs in a subthread.
def runner(s, c):
    # endtime = time.time() + 20
    while not c.stop: # and time.time() < endtime:
        s.handle_request()
class Control(object):
    stop = False

def set_up_server(remote_base_path, threaded = True):
    # choosing free port
    s = socket.socket()
    s.bind(('',0))
    ip, port = s.getsockname()
    # this is an override. By default we get address "0.0.0.0" which messes with our heads.
    ip = 'localhost'
    s.close()
    print("Chosen URL is http://%s:%s/" % (ip, port))
    # setting up the server.
    s = wsgiref.simple_server.make_server(
        ip,
        port,
        git_http_backend.GitHttpBackend.assemble_WSGI_git_app(
            remote_base_path,
            '',
            {
                'repo_auto_create':True,
                'gzip_response':False
            }
            )
        # wsgiref.simple_server.demo_app
        )
    if threaded:
        c = Control()
        t = threading.Thread(None, runner, None, (s,c))
        t.daemon = True
        t.start()
        return t, c, ip, port
    else:
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            pass
        return None, None, ip, port

def kill_server(t, c, ip, port):
    print("killing the server")
    c.stop = True
    try:
        urlopenlib.urlopen('http://%s:%s' % (ip, port)).close()
        urlopenlib.urlopen('http://%s:%s' % (ip, port)).close()
    except:
        pass

def test_smarthttp(url, base_path):
    # this tests roundtrip -
    # new repo > push up > clone down > push up > pull to original.
    repo_one_path = os.path.join(base_path, 'repoone')
    repo_two_path = os.path.join(base_path, 'repotwo')
    line_one = 'This is a test\n'
    line_two = 'Another line\n'
    file_name = 'testfile.txt'

    ip = 'localhost'
    # create local repo
    print("== creating first local repo and adding content ==")
    os.mkdir(repo_one_path)
    os.chdir(repo_one_path)
    subprocess.call('git init')
    f = open(file_name, 'w')
    f.write(line_one)
    f.close()
    subprocess.call('git add %s' % file_name)
    subprocess.call('git commit -m "Initial import"')
    subprocess.call('git push http://%s/centralrepo master' % url)
    os.chdir('..')
    # second local repo
    print("== cloning to second local repo and verifying content, adding more ==")
    subprocess.call('git clone http://%s/centralrepo repotwo' % url)
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
    subprocess.call('git add %s' % file_name)
    subprocess.call('git commit -m "Changing the file"')
    subprocess.call('git push origin master')
    os.chdir('..')
    # back to original local repo
    print("== pulling to first local repo and verifying added content ==")
    os.chdir(repo_one_path)
    subprocess.call('git pull http://%s/centralrepo master' % url)
    assert(file_name in os.listdir('.'))
    lines = open(file_name).readlines()
    assert(set([line_one,line_two]).issubset(lines))
    print("=============\n== SUCCESS ==\n=============\n")

def server_and_client(base_path):
    remote_base_path = os.path.join(base_path, 'reporemote')
    server_thread, control, ip, port = set_up_server(remote_base_path)
    test_smarthttp('%s:%s' % (ip, port), base_path)
    shutil.rmtree(base_path, True)
    kill_server(server_thread, control, ip, port)

def server_only(base_path):
    remote_base_path = os.path.join(base_path, 'reporemote')
    try:
        server_thread, control, ip, port = set_up_server(remote_base_path, False)
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(base_path, True)

def client_only(base_path, url):
    try:
        test_smarthttp(url, base_path)
    except KeyboardInterrupt:
        pass
    finally:
        pass
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