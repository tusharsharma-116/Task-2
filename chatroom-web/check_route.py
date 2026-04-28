import urllib.request
try:
    resp = urllib.request.urlopen('http://127.0.0.1:5000/api/upload_audio')
    print('status', resp.status)
    print(resp.read().decode()[:1000])
except Exception as e:
    print('error', repr(e))
