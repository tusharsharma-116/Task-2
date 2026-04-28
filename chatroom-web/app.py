import os
import logging
import shutil
import base64
import io
from datetime import datetime, timezone
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import google.generativeai as genai
from pymongo import MongoClient

from PIL import Image
import numpy as np
import cv2

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chatroom_secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/chatroom')
genai.configure(api_key=GEMINI_API_KEY)
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client['chatroom']
messages_collection = db['messages']

model = genai.GenerativeModel('gemini-2.0-flash')

# ...existing code up to model definition...

# Configure logging
logging.basicConfig(level=logging.INFO)

# Try to locate ffmpeg and set a module-level FFMPEG_BIN and ensure PATH contains its bin
FFMPEG_BIN = shutil.which('ffmpeg')
if not FFMPEG_BIN:
    candidates = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WinGet', 'Packages', 'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe', 'ffmpeg-8.1-full_build', 'bin', 'ffmpeg.exe'),
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\FFmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\Gyan\ffmpeg\bin\ffmpeg.exe'
    ]
    for c in candidates:
        if c and os.path.exists(c):
            FFMPEG_BIN = c
            break

if FFMPEG_BIN:
    ffmpeg_dir = os.path.dirname(FFMPEG_BIN)
    os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
    logging.info(f'Using ffmpeg at: {FFMPEG_BIN}')
else:
    logging.warning('ffmpeg not found in PATH or common locations; pydub may fail to process MP3s')

# Now it's safe to import pydub
from pydub import AudioSegment
if FFMPEG_BIN:
    AudioSegment.converter = FFMPEG_BIN
    ffprobe_path = os.path.join(os.path.dirname(FFMPEG_BIN), 'ffprobe.exe')
    if os.path.exists(ffprobe_path):
        try:
            AudioSegment.ffprobe = ffprobe_path
        except Exception:
            pass

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('status', {'msg': 'Connected to Chatroom Pro!'})

@socketio.on('send_message')
def handle_send_message(data):
    sender = data.get('sender', 'Anonymous')
    message = data['message'].strip()
    timestamp = datetime.now(timezone.utc).isoformat()
    
    if message.startswith('/ai '):
        prompt = message[4:]
        try:
            response = model.generate_content(prompt)
            ai_reply = response.text
            ai_doc = {'sender': 'AI Assistant', 'message': ai_reply, 'timestamp': timestamp}
            emit('receive_message', ai_doc, broadcast=True)
            messages_collection.insert_one(ai_doc)
        except Exception as e:
            emit('receive_message', {'sender': 'AI', 'message': f'AI Error: {str(e)}', 'timestamp': timestamp}, broadcast=True)
    else:
        emit_doc = {'sender': sender, 'message': message, 'timestamp': timestamp}
        emit('receive_message', emit_doc, broadcast=True)
        messages_collection.insert_one(emit_doc)

@socketio.on('get_history')
def handle_get_history():
    history = list(messages_collection.find().sort('timestamp', 1).limit(50))
    emit_history = []
    for msg in history:
        emit_msg = {
            'sender': msg['sender'],
            'message': msg['message'],
            'timestamp': msg['timestamp'].isoformat() if isinstance(msg['timestamp'], datetime) else msg['timestamp']
        }
        emit_history.append(emit_msg)
    emit('chat_history', emit_history)

@socketio.on('upload_image')
def handle_upload_image(data):
    try:
        image_data = base64.b64decode(data['image'].split(',')[1])
        image = Image.open(io.BytesIO(image_data))
        orig_array = np.array(image)
        comp_buffer = io.BytesIO()
        buffer_orig = io.BytesIO()
        image.save(buffer_orig, format='PNG')
        orig_size = buffer_orig.tell()
        image.save(comp_buffer, 'JPEG', quality=90, optimize=True)

        comp_array = np.array(Image.open(comp_buffer))
        mse = np.mean((orig_array.astype(np.float64) - comp_array.astype(np.float64)) ** 2)
        comp_size = len(comp_buffer.getvalue())

        savings = ((orig_size - comp_size) / orig_size * 100) if orig_size > 0 else 0
        psnr = 10 * np.log10((orig_array.max()**2) / mse) if mse > 0 else float('inf')
        gray = cv2.cvtColor(orig_array, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        orb = cv2.ORB_create()
        kp = orb.detect(gray, None)
        kp_img = cv2.drawKeypoints(gray, kp, None)
        _, edges_buf = cv2.imencode('.jpg', edges)
        _, kp_buf = cv2.imencode('.jpg', kp_img)
        edges_b64 = 'data:image/jpeg;base64,' + base64.b64encode(edges_buf).decode()
        kp_b64 = 'data:image/jpeg;base64,' + base64.b64encode(kp_buf).decode()
        comp_b64 = 'data:image/jpeg;base64,' + base64.b64encode(comp_buffer.getvalue()).decode()
        ai_desc = "Image processed OK"
        emit('image_results', {
            'original': data['image'],
            'compressed': comp_b64,
            'edges': edges_b64,
            'keypoints': kp_b64,
            'metrics': f'Orig: {orig_size:,}B | Comp: {comp_size:,}B | Savings: {savings:.1f}% | MSE: {mse:.2f} | PSNR: {psnr:.2f}dB | KPs: {len(kp)}',
            'ai_desc': ai_desc
        })
    except Exception as e:
        emit('image_error', {'error': str(e)})

# --- AUDIO UPLOAD/ANALYSIS LOGIC ---
@socketio.on('upload_audio')
def handle_upload_audio(data):
    try:
        logging.info('Received upload_audio event')
        emit('status', {'msg': 'Processing audio...'}, broadcast=False)
        audio_data = base64.b64decode(data['audio'].split(',')[1])
        logging.info(f'Audio bytes: {len(audio_data)}')
        if len(audio_data) > 5*1024*1024:
            emit('audio_error', {'error': 'Audio >5MB'})
            return
        # Delegate to helper to allow HTTP test calls
        results = process_audio_bytes(audio_data)
        emit('audio_results', results)
        emit('status', {'msg': 'Ready'})
    except Exception as e:
        logging.exception('Error processing uploaded audio')
        emit('audio_error', {'error': str(e)})
        emit('status', {'msg': 'Ready'})

def process_audio_bytes(audio_bytes: bytes) -> dict:
    logging.info('process_audio_bytes: start')
    # Try to read directly with librosa/soundfile (avoids ffmpeg/ffprobe dependency for WAV)
    y_orig = None
    sr = None
    pre_error = None
    try:
        y_orig, sr = librosa.load(io.BytesIO(audio_bytes), sr=None)
        logging.info(f'librosa.load direct OK sr={sr} len={len(y_orig)}')
    except Exception:
        logging.exception('librosa.load direct failed; attempting ffmpeg transcode')
        # try using ffmpeg executable to transcode input to WAV
        ff = FFMPEG_BIN or shutil.which('ffmpeg') or ''
        try:
            import subprocess
            proc = subprocess.run([ff, '-i', 'pipe:0', '-f', 'wav', 'pipe:1', '-hide_banner', '-loglevel', 'error'], input=audio_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            wav_bytes = proc.stdout
            y_orig, sr = librosa.load(io.BytesIO(wav_bytes), sr=None)
            logging.info(f'ffmpeg transcode -> librosa OK sr={sr} len={len(y_orig)}')
        except Exception:
            logging.exception('ffmpeg transcode failed; falling back to pydub')
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
                orig_wav_buffer = io.BytesIO()
                audio.export(orig_wav_buffer, format="wav")
                orig_wav_buffer.seek(0)
                y_orig, sr = librosa.load(orig_wav_buffer, sr=None)
                logging.info(f'pydub fallback -> librosa OK sr={sr} len={len(y_orig)}')
            except Exception as e:
                logging.exception('pydub fallback failed')
                pre_error = str(e)
                # ensure we have defaults to continue
                y_orig = np.array([])
                sr = 22050

    bitrates = [320, 192, 128, 64]  # kbps labels
    table = []
    comp_spec = None
    orig_spec_b64 = None

    # Ensure we have wav_bytes for ffmpeg input
    if 'wav_bytes' not in locals():
        wav_bytes = audio_bytes

    ff = FFMPEG_BIN or shutil.which('ffmpeg') or 'ffmpeg'

    # compute original spectrogram now so we can reuse
    D_orig = None
    try:
        if y_orig is not None and len(y_orig) > 0:
            D_orig = librosa.amplitude_to_db(np.abs(librosa.stft(y_orig)), ref=np.max)
    except Exception:
        logging.exception('Failed to compute original spectrogram')
        D_orig = None

    for bitrate in bitrates:
        try:
            import subprocess
            # transcode wav bytes to mp3 at target bitrate using ffmpeg
            proc = subprocess.run([ff, '-i', 'pipe:0', '-b:a', f'{bitrate}k', '-f', 'mp3', 'pipe:1', '-hide_banner', '-loglevel', 'error'], input=wav_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            comp_bytes = proc.stdout
            size = len(comp_bytes)

            # convert mp3 bytes back to wav (ffmpeg) then load with librosa to avoid mp3-decoder inconsistencies
            try:
                proc2 = subprocess.run([ff, '-i', 'pipe:0', '-f', 'wav', 'pipe:1', '-hide_banner', '-loglevel', 'error'], input=comp_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                wav_comp_bytes = proc2.stdout
                y_comp, _ = librosa.load(io.BytesIO(wav_comp_bytes), sr=sr)
            except Exception:
                # fallback: try loading mp3 directly (older environments)
                try:
                    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tf:
                        tf.write(comp_bytes)
                        temp_name = tf.name
                    y_comp, _ = librosa.load(temp_name, sr=sr)
                finally:
                    try:
                        os.unlink(temp_name)
                    except Exception:
                        pass

            # align lengths before metric computation
            n = min(len(y_orig), len(y_comp)) if (y_orig is not None and y_comp is not None) else 0
            if n == 0:
                mse = float('inf')
                snr = float('inf')
            else:
                mse = np.mean((y_orig[:n] - y_comp[:n])**2)
                snr = 10 * np.log10(np.mean(y_orig[:n]**2) / mse) if mse > 0 else float('inf')

            table.append({'bitrate': f'{bitrate}k', 'size': f'{size:,}B', 'mse': f'{mse:.4f}' if np.isfinite(mse) else 'inf', 'snr': f'{snr:.2f}' if np.isfinite(snr) else 'inf'})
            logging.info(f'bitrate {bitrate}k: size={size} mse={mse} snr={snr}')

            if bitrate == 64 and D_orig is not None:
                try:
                    D_comp = librosa.amplitude_to_db(np.abs(librosa.stft(y_comp[:min(len(y_comp), len(y_orig))])), ref=np.max)

                    plt.figure(figsize=(12, 4))
                    plt.subplot(1,2,1)
                    plt.imshow(D_orig, aspect='auto', origin='lower', cmap='viridis')
                    plt.title('Orig Spec')
                    plt.axis('off')
                    orig_buf = io.BytesIO()
                    plt.savefig(orig_buf, format='png', bbox_inches='tight', pad_inches=0)
                    orig_buf.seek(0)
                    orig_spec_b64 = 'data:image/png;base64,' + base64.b64encode(orig_buf.getvalue()).decode()

                    plt.subplot(1,2,2)
                    plt.imshow(D_comp, aspect='auto', origin='lower', cmap='viridis')
                    plt.title('Comp Spec')
                    plt.axis('off')
                    comp_buf = io.BytesIO()
                    plt.savefig(comp_buf, format='png', bbox_inches='tight', pad_inches=0)
                    comp_buf.seek(0)
                    comp_spec_b64 = 'data:image/png;base64,' + base64.b64encode(comp_buf.getvalue()).decode()
                    comp_spec = comp_spec_b64
                finally:
                    try:
                        plt.close('all')
                    except Exception:
                        pass
        except Exception as e:
            logging.exception('Error during bitrate transcode')
            table.append({'bitrate': f'{bitrate}k', 'size': '-', 'mse': '-', 'snr': '-', 'error': str(e)[:200]})
            continue

    ai_desc = 'Audio analyzed - multi-bitrate compression table + spectrograms (FFmpeg required for pydub MP3).'
    if pre_error:
        ai_desc = f'Pre-decode error: {pre_error} | ' + ai_desc

    result = {
        'orig_spec': orig_spec_b64,
        'comp_spec': comp_spec,
        'table': table,
        'ai_desc': ai_desc
    }
    return result

# HTTP test endpoint to allow programmatic verification
@app.route('/api/upload_audio', methods=['POST'])
def http_upload_audio():
    from flask import request, jsonify
    try:
        body = request.get_json(force=True)
        audio_b64 = body.get('audio')
        if not audio_b64:
            return jsonify({'error': 'missing audio field'}), 400
        # allow data:... base64 or raw base64
        if audio_b64.startswith('data:'):
            audio_bytes = base64.b64decode(audio_b64.split(',')[1])
        else:
            audio_bytes = base64.b64decode(audio_b64)
        logging.info(f'http_upload_audio: received bytes={len(audio_bytes)}')
        results = process_audio_bytes(audio_bytes)
        logging.info(f'http_upload_audio: results table length={len(results.get("table", []))}')
        return jsonify(results)
    except Exception as e:
        logging.exception('HTTP upload_audio error')
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Turn off the reloader to avoid socket issues on Windows
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

