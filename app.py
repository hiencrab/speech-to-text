try:
    # Verify TLS against the OS trust store instead of certifi's bundle, so HTTPS works
    # behind corporate TLS inspection whose root CA is only installed in Windows.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify
import speech_recognition as sr
import json
import os
import base64
import tempfile
import requests
import wave
import glob
import shutil
import db

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

DEFAULT_CONFIG = {
    'engine': 'speechrecognition',
    'google_api_key': '',
    'language': 'vi-VN'
}

# Formats natively supported by Google Cloud STT REST API
GOOGLE_CLOUD_ENCODINGS = {
    '.wav':  'LINEAR16',
    '.flac': 'FLAC',
    '.mp3':  'MP3',
    '.ogg':  'OGG_OPUS',
    '.opus': 'OGG_OPUS',
    '.webm': 'WEBM_OPUS',
    '.amr':  'AMR',
}

SUPPORTED_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.opus', '.webm', '.m4a', '.amr', '.aac'}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    config.setdefault(k, v)
                config['db'] = {**db.DEFAULT_DB_CONFIG, **config.get('db', {})}
                return config
        except Exception:
            pass
    return {**DEFAULT_CONFIG, 'db': dict(db.DEFAULT_DB_CONFIG)}


def _merge_db_config(saved, incoming):
    """Overlay form values on the saved DB config; an empty password keeps the saved one."""
    merged = dict(saved)
    if not incoming:
        return merged
    merged['saved'] = True
    if incoming.get('mode') in ('localhost', 'remote'):
        merged['mode'] = incoming['mode']
    for field in ('host', 'database', 'user'):
        if field in incoming:
            merged[field] = str(incoming[field] or '').strip()
    if 'port' in incoming:
        try:
            port = int(incoming['port'])
        except (TypeError, ValueError):
            raise ValueError('Port phải là số')
        if not 1 <= port <= 65535:
            raise ValueError('Port phải trong khoảng 1–65535')
        merged['port'] = port
    if incoming.get('password'):
        merged['password'] = incoming['password']
    if 'auto_save' in incoming:
        merged['auto_save'] = bool(incoming['auto_save'])
    return merged


def _public_db_config(db_cfg):
    public = {k: v for k, v in db_cfg.items() if k != 'password'}
    public['has_password'] = bool(db_cfg.get('password'))
    public['configured'] = db.is_configured(db_cfg)
    return public


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _get_audio_ext(filename):
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext:
            return ext
    return '.wav'


def _ensure_ffmpeg_on_path():
    if shutil.which('ffmpeg') and shutil.which('ffprobe'):
        return True
    local = os.environ.get('LOCALAPPDATA', '')
    patterns = [
        os.path.join(local, 'Microsoft', 'WinGet', 'Packages', '*FFmpeg*', '*', 'bin', 'ffmpeg.exe'),
        os.path.join(local, 'Microsoft', 'WinGet', 'Packages', '*FFmpeg*', 'bin', 'ffmpeg.exe'),
        os.path.join(local, 'Microsoft', 'WinGet', 'Links', 'ffmpeg.exe'),
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        os.path.join(os.environ.get('USERPROFILE', ''), 'scoop', 'shims', 'ffmpeg.exe'),
        r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
    ]
    for pattern in patterns:
        for exe in glob.glob(pattern):
            bin_dir = os.path.dirname(exe)
            # pydub resolves both ffmpeg and ffprobe via PATH, so prepend the bin dir
            os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')
            return True
    return False


FFMPEG_AVAILABLE = _ensure_ffmpeg_on_path()


def _convert_to_wav(input_path):
    """Convert audio to mono 16kHz WAV using pydub. Raises RuntimeError if pydub/ffmpeg unavailable."""
    try:
        from pydub import AudioSegment
    except ImportError:
        raise RuntimeError(
            'Cần pydub để chuyển đổi định dạng này.\n'
            'Chạy: pip install pydub\n'
            'Và cài ffmpeg: https://ffmpeg.org/download.html'
        )
    if not _ensure_ffmpeg_on_path():
        raise RuntimeError(
            'Không tìm thấy ffmpeg. Cài bằng: winget install Gyan.FFmpeg, rồi khởi động lại server.'
        )
    try:
        # No format hint: ffmpeg probes the content, so raw ADTS .aac and MP4-based .m4a both work
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        wav_path = input_path + '_converted.wav'
        audio.export(wav_path, format='wav')
        return wav_path
    except Exception as e:
        raise RuntimeError(f'Không đọc được file âm thanh: {_ffmpeg_error_summary(str(e))}')


def _ffmpeg_error_summary(message):
    # ffmpeg output starts with a long build/config banner; keep only the actual error lines
    lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    errors = [ln for ln in lines if 'error' in ln.lower() or 'invalid' in ln.lower() or 'not found' in ln.lower()]
    summary = ' | '.join((errors or lines)[-3:])
    return summary[:300] + '. File có thể bị hỏng hoặc không phải file âm thanh hợp lệ.'


@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File quá lớn (giới hạn 100MB)'}), 413

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': f'Lỗi server: {str(e)}'}), 500

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/settings', methods=['GET'])
def get_settings():
    config = load_config()
    return jsonify({
        'engine': config['engine'],
        'language': config['language'],
        'has_api_key': bool(config.get('google_api_key')),
        'ffmpeg_available': _ensure_ffmpeg_on_path(),
        'db': _public_db_config(config['db'])
    })


@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.get_json() or {}
    config = load_config()
    for field in ('engine', 'language', 'google_api_key'):
        if field in data:
            config[field] = data[field]
    try:
        config['db'] = _merge_db_config(config['db'], data.get('db'))
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    save_config(config)
    return jsonify({'success': True})


@app.route('/api/db/test', methods=['POST'])
def test_db():
    try:
        db_cfg = _merge_db_config(load_config()['db'], request.get_json() or {})
        version = db.test_connection(db_cfg)
        return jsonify({'success': True, 'message': f'Kết nối thành công ✓ {version}. Bảng "transcripts" đã sẵn sàng.'})
    except Exception as e:
        return jsonify({'success': False, 'message': db.describe_error(e)})


@app.route('/api/transcripts', methods=['POST'])
def save_transcript():
    data = request.get_json() or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Không có nội dung để lưu'}), 400
    db_cfg = load_config()['db']
    if not db.is_configured(db_cfg):
        return jsonify({'error': 'Chưa cấu hình PostgreSQL. Vào Cài đặt để thêm.'}), 400
    try:
        saved = db.save_transcript(db_cfg, {**data, 'text': text})
        return jsonify({'success': True, **saved})
    except Exception as e:
        return jsonify({'error': f'Lỗi lưu PostgreSQL: {db.describe_error(e)}'}), 500


@app.route('/api/transcripts', methods=['GET'])
def list_transcripts():
    db_cfg = load_config()['db']
    if not db.is_configured(db_cfg):
        return jsonify({'error': 'Chưa cấu hình PostgreSQL'}), 400
    limit = min(max(request.args.get('limit', 20, type=int), 1), 100)
    try:
        return jsonify({'items': db.list_transcripts(db_cfg, limit)})
    except Exception as e:
        return jsonify({'error': f'Lỗi đọc PostgreSQL: {db.describe_error(e)}'}), 500


def _auto_save(config, result, language, source, filename):
    db_cfg = config['db']
    if not (db_cfg.get('auto_save') and db.is_configured(db_cfg) and result.get('text')):
        return result
    try:
        saved = db.save_transcript(db_cfg, {
            'text': result['text'],
            'engine': result.get('engine'),
            'language': language,
            'source': source,
            'filename': filename,
            'confidence': result.get('confidence'),
        })
        return {**result, 'saved_id': saved['id']}
    except Exception as e:
        return {**result, 'db_error': f'Đã nhận diện nhưng lưu DB thất bại: {db.describe_error(e)}'}


@app.route('/api/test-api-key', methods=['POST'])
def test_api_key():
    data = request.get_json() or {}
    api_key = data.get('api_key') or load_config().get('google_api_key', '')

    if not api_key:
        return jsonify({'success': False, 'message': 'Chưa có API Key'})

    url = f'https://speech.googleapis.com/v1/speech:recognize?key={api_key}'
    payload = {
        "config": {"encoding": "LINEAR16", "sampleRateHertz": 16000, "languageCode": "vi-VN"},
        "audio": {"content": ""}
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        try:
            err = resp.json().get('error', {})
        except ValueError:
            err = {}
        msg = err.get('message', '')
        reasons = {d.get('reason') for d in err.get('details', []) if isinstance(d, dict)}
        # An invalid key also returns 400, so a 400 only proves the key works when it's
        # about the (intentionally empty) audio rather than the key itself.
        key_invalid = 'API_KEY_INVALID' in reasons or 'api key not valid' in msg.lower()
        if resp.status_code == 200 or (resp.status_code == 400 and not key_invalid):
            return jsonify({'success': True, 'message': 'API Key hợp lệ ✓'})
        elif key_invalid:
            return jsonify({'success': False, 'message': 'API Key không hợp lệ'})
        elif resp.status_code == 403:
            return jsonify({'success': False, 'message': f'API Key bị từ chối (chưa bật Cloud Speech-to-Text API hoặc key bị giới hạn): {msg}'})
        else:
            return jsonify({'success': False, 'message': f'HTTP {resp.status_code}: {msg}'})
    except requests.Timeout:
        return jsonify({'success': False, 'message': 'Timeout — kiểm tra kết nối'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/transcribe', methods=['POST'])
def transcribe():
    if 'audio' not in request.files:
        return jsonify({'error': 'Không có audio'}), 400

    tmp_path = None
    converted_path = None
    try:
        config = load_config()
        audio_file = request.files['audio']
        engine = request.form.get('engine', config['engine'])
        language = request.form.get('language', config['language'])

        filename = audio_file.filename or 'audio.wav'
        ext = _get_audio_ext(filename)

        if ext not in SUPPORTED_EXTENSIONS:
            return jsonify({'error': f'Định dạng "{ext}" không hỗ trợ. Dùng: WAV, MP3, FLAC, OGG, M4A, WEBM'}), 400

        # On Windows, NamedTemporaryFile holds an exclusive lock while open — close before saving
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
        audio_file.save(tmp_path)

        if engine == 'google_cloud':
            result = _transcribe_google_cloud(tmp_path, language, config)
        else:
            if ext != '.wav':
                converted_path = _convert_to_wav(tmp_path)
                result = _transcribe_speech_recognition(converted_path, language)
            else:
                result = _transcribe_speech_recognition(tmp_path, language)

        source = 'upload' if request.form.get('source') == 'upload' else 'record'
        return jsonify(_auto_save(config, result, language, source, filename))
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'error': f'Lỗi xử lý: {type(e).__name__}: {e}'}), 500
    finally:
        for p in filter(None, [tmp_path, converted_path]):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


# Google's free Web Speech API silently truncates long requests, and Cloud STT's
# synchronous API rejects audio over 60 s, so long audio is sent in chunks.
SR_CHUNK_MS = 20_000
GC_CHUNK_MS = 50_000


def _split_wav(wav_path, max_ms):
    """Split a WAV into chunks of at most max_ms, cutting at a pause near each boundary."""
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_silence
    except ImportError:
        return [wav_path]
    audio = AudioSegment.from_wav(wav_path)
    if len(audio) <= max_ms:
        return [wav_path]
    thresh = audio.dBFS - 16
    paths, start = [], 0
    while start < len(audio):
        end = min(start + max_ms, len(audio))
        if end < len(audio):
            window_start = max(start, end - 5000)
            pauses = detect_silence(audio[window_start:end], min_silence_len=300, silence_thresh=thresh)
            if pauses:
                s, e = pauses[-1]
                end = window_start + (s + e) // 2
        chunk_path = f'{wav_path}_part{len(paths)}.wav'
        audio[start:end].export(chunk_path, format='wav')
        paths.append(chunk_path)
        start = end
    return paths


def _remove_files(paths, keep=None):
    for p in paths:
        if p and p != keep and os.path.exists(p):
            try:
                os.unlink(p)
            except Exception:
                pass


def _transcribe_speech_recognition(path, language):
    r = sr.Recognizer()
    chunks = _split_wav(path, SR_CHUNK_MS)
    try:
        texts = []
        for chunk in chunks:
            with sr.AudioFile(chunk) as source:
                audio = r.record(source)
            try:
                texts.append(r.recognize_google(audio, language=language))
            except sr.UnknownValueError:
                continue  # a chunk with no speech (e.g. silence) is not an error
        if not texts:
            return {'error': 'Không nhận diện được. Hãy nói to và rõ hơn.'}
        return {'text': ' '.join(texts), 'engine': 'SpeechRecognition', 'chunks': len(chunks)}
    except sr.RequestError as e:
        return {'error': f'Lỗi dịch vụ: {e}'}
    finally:
        _remove_files(chunks, keep=path)


class _GoogleCloudError(Exception):
    pass


def _google_cloud_recognize(file_path, encoding, language, api_key):
    cfg = {
        "encoding": encoding,
        "languageCode": language,
        "enableAutomaticPunctuation": True,
        "model": "latest_long"
    }
    if encoding == 'LINEAR16':
        with wave.open(file_path, 'rb') as w:
            cfg["sampleRateHertz"] = w.getframerate()
    with open(file_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode()

    url = f'https://speech.googleapis.com/v1/speech:recognize?key={api_key}'
    resp = requests.post(url, json={"config": cfg, "audio": {"content": content}}, timeout=60)
    data = resp.json()
    if resp.status_code != 200:
        raise _GoogleCloudError(data.get('error', {}).get('message', 'Lỗi không xác định'))
    return [r['alternatives'][0] for r in data.get('results', []) if r.get('alternatives')]


def _transcribe_google_cloud(path, language, config):
    api_key = config.get('google_api_key', '')
    if not api_key:
        return {'error': 'Chưa cấu hình Google API Key. Vào Cài đặt để thêm.'}

    ext = os.path.splitext(path)[1].lower()
    converted_path = None
    chunks = []
    try:
        # Converting to WAV (when ffmpeg exists) lets long files be chunked; formats Google
        # can't read (.m4a/.aac) must be converted regardless.
        if ext != '.wav' and (ext not in GOOGLE_CLOUD_ENCODINGS or _ensure_ffmpeg_on_path()):
            converted_path = _convert_to_wav(path)
            path, ext = converted_path, '.wav'

        if ext == '.wav':
            chunks = _split_wav(path, GC_CHUNK_MS)
            alternatives = []
            for chunk in chunks:
                alternatives += _google_cloud_recognize(chunk, 'LINEAR16', language, api_key)
        else:
            alternatives = _google_cloud_recognize(path, GOOGLE_CLOUD_ENCODINGS[ext], language, api_key)

        texts = [a['transcript'].strip() for a in alternatives if a.get('transcript', '').strip()]
        if not texts:
            return {'error': 'Không nhận diện được giọng nói'}
        confidences = [a['confidence'] for a in alternatives if 'confidence' in a]
        result = {'text': ' '.join(texts), 'engine': 'Google Cloud STT', 'chunks': max(len(chunks), 1)}
        if confidences:
            result['confidence'] = round(sum(confidences) / len(confidences) * 100, 1)
        return result
    except RuntimeError as e:
        return {'error': str(e)}
    except _GoogleCloudError as e:
        return {'error': f'Google API: {e}'}
    except requests.Timeout:
        return {'error': 'Timeout — kết nối tới Google chậm, thử lại sau'}
    except Exception as e:
        return {'error': str(e)}
    finally:
        _remove_files(chunks + [converted_path], keep=None if converted_path else path)


def _port_in_use(port):
    import socket
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


if __name__ == '__main__':
    PORT = 5000
    # On Windows a second server can bind the same port and silently share traffic with the
    # first; the reloader's child process (WERKZEUG_RUN_MAIN) is expected to rebind, so skip it.
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' and _port_in_use(PORT):
        print(f'Cổng {PORT} đang được dùng — có thể server cũ vẫn đang chạy. Tắt nó (Ctrl+C) rồi chạy lại.')
        raise SystemExit(1)
    # use_debugger=False: disable Werkzeug HTML debugger so errors return JSON, not HTML
    app.run(debug=True, use_debugger=False, port=PORT)
