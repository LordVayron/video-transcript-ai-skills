import re
from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

app = Flask(__name__)

VIDEO_ID_PATTERN = re.compile(
    r'(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)


def extract_video_id(url):
    match = VIDEO_ID_PATTERN.search(url)
    return match.group(1) if match else None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/transcript', methods=['POST'])
def transcript():
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'No URL provided.'}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Could not extract a valid YouTube video ID from the URL.'}), 400

    api = YouTubeTranscriptApi()
    try:
        try:
            segments = api.fetch(video_id, languages=['en'])
        except NoTranscriptFound:
            transcript_list = api.list(video_id)
            segments = next(iter(transcript_list)).fetch()

        text = ' '.join(seg.text for seg in segments)
        return jsonify({'transcript': text, 'video_id': video_id})

    except TranscriptsDisabled:
        return jsonify({'error': 'Transcripts are disabled for this video.'}), 422
    except NoTranscriptFound:
        return jsonify({'error': 'No transcript found for this video.'}), 422
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
