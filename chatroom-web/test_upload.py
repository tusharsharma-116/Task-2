import base64
import io
import json
import math
import urllib.request
import urllib.error
import sys
import os

# generate a 1s 440Hz sine wave and write as WAV
try:
    import soundfile as sf
    import numpy as np
except Exception as e:
    print('Missing packages:', e)
    sys.exit(1)

sr = 22050
t = np.linspace(0, 1, int(sr), endpoint=False)
wave = 0.5 * np.sin(2 * math.pi * 440 * t)
buf = io.BytesIO()
sf.write(buf, wave, sr, format='WAV')
buf.seek(0)
raw = buf.read()
encoded = base64.b64encode(raw).decode()

url = 'http://127.0.0.1:5000/api/upload_audio'
data = json.dumps({'audio': 'data:audio/wav;base64,' + encoded}).encode()
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req, timeout=60)
    body = resp.read().decode()
    print('Server response:', body[:1000])
except urllib.error.HTTPError as e:
    print('HTTP error', e.code, e.read().decode())
except Exception as e:
    print('Error contacting server:', e)
 