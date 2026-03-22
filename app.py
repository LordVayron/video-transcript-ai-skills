import re
import os
import json
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
from dotenv import load_dotenv
import yt_dlp

load_dotenv(override=True)

app = Flask(__name__)

APP_PASSWORD    = os.environ.get('APP_PASSWORD', '@Francisco6')
YOUTUBE_COOKIES = os.environ.get('YOUTUBE_COOKIES', '')
OPENAI_API_KEY  = os.environ.get('OPENAI_API_KEY', '')
WHISPER_COST_PER_MINUTE = 0.006  # USD

USAGE_FILE        = os.path.join(os.path.dirname(__file__), 'usage.json')
SKILLS_FILE       = os.path.join(os.path.dirname(__file__), 'skills.json')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')

CATEGORIES = [
    'Document & File Creation',
    'Reading & Extraction',
    'Writing & Content',
    'Strategy & Analysis',
    'Brand & Voice',
    'Platform-Specific',
    'Marketing & Advertising',
    'Development & Code',
    'Design & Visual',
    'Data & Spreadsheets',
    'Workflow & Automation',
    'Product Knowledge',
    'Meta / Skill Tooling',
]

ANALYZE_PROMPT = """\
You are analyzing a video transcript to identify the best skill directions.

Platform: {platform}
Transcript (excerpt):
<transcript>
{transcript}
</transcript>

Identify exactly 2 distinct, concrete directions this transcript could be turned into a Claude Code skill.
Each suggestion should be a short action phrase (10-15 words max) describing WHAT the skill would do.
Focus on practical, reusable capabilities.

Output ONLY a numbered list with exactly 2 items. No explanation, no preamble:
1. [first suggestion]
2. [second suggestion]"""

GENERATE_PROMPT = """\
You are an expert at creating Claude Code skills in Anthropic's official skill format.

A skill is a reusable instruction set that tells Claude when and how to perform a specific task.

Platform: {platform}
User's intent / additional context: {context}

Full transcript to base the skill on:
<transcript>
{transcript}
</transcript>

Generate a complete, production-ready Claude Code skill. Capture the core methodology, framework, or \
technique demonstrated in the transcript. Make it self-contained and actionable.

Use this EXACT format (include the --- delimiters):

---
name: kebab-case-skill-name
description: "One-line description. TRIGGER when: [specific condition]. DO NOT TRIGGER when: [exclusion]."
category: "[pick exactly one from: {categories}]"
---

# [Human Readable Skill Name]

## Purpose
[2-3 sentences explaining what this skill does and the specific value it provides]

## Instructions
[Numbered step-by-step instructions. Be specific and actionable. 5-10 steps.]

## Key Behaviors
- [Concrete behavior or rule 1]
- [Concrete behavior or rule 2]
- [Concrete behavior or rule 3]

## Examples
[1-2 concrete example scenarios showing the skill in action]

Output ONLY the skill markdown. No preamble, no explanation, no commentary."""

VIDEO_ID_PATTERN = re.compile(
    r'(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)


# ── Usage tracking ────────────────────────────────────────────────────────────

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_usage(data):
    with open(USAGE_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def record_usage(seconds):
    month_key = datetime.now().strftime('%Y-%m')
    data = load_usage()
    entry = data.get(month_key, {'seconds': 0, 'requests': 0, 'cost': 0.0})
    entry['seconds'] += seconds
    entry['requests'] += 1
    entry['cost'] = round((entry['seconds'] / 60) * WHISPER_COST_PER_MINUTE, 4)
    data[month_key] = entry
    save_usage(data)


def load_skills():
    if os.path.exists(SKILLS_FILE):
        with open(SKILLS_FILE, 'r') as f:
            return json.load(f)
    return {'skills': []}


def save_skills(data):
    with open(SKILLS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_current_month_usage():
    month_key = datetime.now().strftime('%Y-%m')
    data = load_usage()
    return data.get(month_key, {'seconds': 0, 'requests': 0, 'cost': 0.0})


# ── YouTube helpers ───────────────────────────────────────────────────────────

def get_yt_api():
    if YOUTUBE_COOKIES:
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tmp.write(YOUTUBE_COOKIES)
        tmp.flush()
        tmp.close()
        return YouTubeTranscriptApi(cookies=tmp.name)
    return YouTubeTranscriptApi()


def extract_video_id(url):
    match = VIDEO_ID_PATTERN.search(url)
    return match.group(1) if match else None


# ── TikTok / Instagram helpers ────────────────────────────────────────────────

def detect_platform(url):
    if 'tiktok.com' in url:
        return 'tiktok'
    if 'instagram.com' in url:
        return 'instagram'
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    return 'unknown'


def parse_vtt(vtt_content):
    text_lines, seen = [], set()
    for line in vtt_content.split('\n'):
        line = line.strip()
        if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or '-->' in line:
            continue
        if line.isdigit():
            continue
        line = re.sub(r'<[^>]+>', '', line)
        line = re.sub(r'\{.*?\}', '', line).strip()
        if line and line not in seen:
            text_lines.append(line)
            seen.add(line)
    return ' '.join(text_lines)


def try_captions(url):
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'skip_download': True,
            'writeautomaticsub': True,
            'writesubtitles': True,
            'subtitlesformat': 'vtt',
            'outtmpl': os.path.join(tmpdir, 'video'),
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get('id', 'video')
            thumbnail = info.get('thumbnail', '')

        vtt_files = [f for f in os.listdir(tmpdir) if f.endswith('.vtt')]
        if not vtt_files:
            return None, video_id, thumbnail

        with open(os.path.join(tmpdir, vtt_files[0]), 'r', encoding='utf-8') as f:
            text = parse_vtt(f.read())

        return (text or None), video_id, thumbnail


def transcribe_with_whisper(url):
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/best',
            'outtmpl': os.path.join(tmpdir, 'audio.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id  = info.get('id', 'video')
            thumbnail = info.get('thumbnail', '')
            duration  = float(info.get('duration') or 0)

        files = os.listdir(tmpdir)
        if not files:
            return None, video_id, thumbnail, 'Could not download audio.'

        audio_path = os.path.join(tmpdir, files[0])
        if os.path.getsize(audio_path) > 25 * 1024 * 1024:
            return None, video_id, thumbnail, 'Video audio exceeds the 25 MB Whisper limit.'

        with open(audio_path, 'rb') as f:
            response = client.audio.transcriptions.create(model='whisper-1', file=f)

        record_usage(duration)
        return response.text, video_id, thumbnail, None


def get_transcript_ytdlp(url):
    text, video_id, thumbnail = try_captions(url)
    if text:
        return text, video_id, thumbnail, None
    if OPENAI_API_KEY:
        return transcribe_with_whisper(url)
    return None, video_id, thumbnail, 'No captions found. Add an OpenAI API key to enable audio transcription.'


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/usage', methods=['GET'])
def usage():
    if request.headers.get('X-App-Password') != APP_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    u = get_current_month_usage()
    u['month'] = datetime.now().strftime('%B %Y')
    return jsonify(u)


@app.route('/transcript', methods=['POST'])
def transcript():
    if request.headers.get('X-App-Password') != APP_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided.'}), 400

    platform = detect_platform(url)

    if platform == 'youtube':
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'error': 'Could not extract a valid YouTube video ID.'}), 400
        try:
            api = get_yt_api()
            try:
                segments = api.fetch(video_id, languages=['en'])
            except NoTranscriptFound:
                segments = next(iter(api.list(video_id))).fetch()
            text = ' '.join(seg.text for seg in segments)
            return jsonify({'transcript': text, 'video_id': video_id, 'platform': 'youtube'})
        except TranscriptsDisabled:
            return jsonify({'error': 'Transcripts are disabled for this video.'}), 422
        except NoTranscriptFound:
            return jsonify({'error': 'No transcript found for this video.'}), 422
        except Exception as e:
            return jsonify({'error': f'An error occurred: {str(e)}'}), 500

    elif platform in ('tiktok', 'instagram'):
        try:
            text, video_id, thumbnail, err = get_transcript_ytdlp(url)
            if err:
                return jsonify({'error': err}), 422
            return jsonify({'transcript': text, 'video_id': video_id, 'thumbnail': thumbnail, 'platform': platform})
        except Exception as e:
            return jsonify({'error': f'An error occurred: {str(e)}'}), 500

    else:
        return jsonify({'error': 'Unsupported URL. Paste a YouTube, TikTok, or Instagram Reels link.'}), 400


@app.route('/analyze-transcript', methods=['POST'])
def analyze_transcript():
    if request.headers.get('X-App-Password') != APP_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    data       = request.get_json(silent=True) or {}
    transcript = data.get('transcript', '').strip()
    platform   = data.get('platform', 'unknown')
    if not transcript:
        return jsonify({'error': 'No transcript provided.'}), 400
    if not OPENROUTER_API_KEY:
        return jsonify({'error': 'OpenRouter API key not configured.'}), 500
    try:
        from openai import OpenAI
        client   = OpenAI(api_key=OPENROUTER_API_KEY, base_url='https://openrouter.ai/api/v1')
        message  = client.chat.completions.create(
            model='anthropic/claude-haiku-4-5',
            max_tokens=256,
            messages=[{'role': 'user', 'content': ANALYZE_PROMPT.format(
                transcript=transcript[:6000], platform=platform)}]
        )
        raw         = message.choices[0].message.content.strip()
        suggestions = []
        for line in raw.split('\n'):
            line = line.strip()
            line = re.sub(r'^[\d]+[.)]\s*', '', line).strip()
            line = re.sub(r'^[-*]\s*', '', line).strip()
            if line:
                suggestions.append(line)
            if len(suggestions) == 2:
                break
        while len(suggestions) < 2:
            suggestions.append('Turn this content into a reusable Claude skill')
        return jsonify({'suggestions': suggestions[:2]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/generate-skill', methods=['POST'])
def generate_skill():
    if request.headers.get('X-App-Password') != APP_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    data       = request.get_json(silent=True) or {}
    transcript = data.get('transcript', '').strip()
    context    = data.get('context', '').strip() or 'No additional context provided.'
    video_id   = data.get('video_id', '')
    thumbnail  = data.get('thumbnail', '')
    video_url  = data.get('video_url', '')
    platform   = data.get('platform', 'unknown')
    if not transcript:
        return jsonify({'error': 'No transcript provided.'}), 400
    if not OPENROUTER_API_KEY:
        return jsonify({'error': 'OpenRouter API key not configured.'}), 500
    try:
        from openai import OpenAI
        import uuid
        client   = OpenAI(api_key=OPENROUTER_API_KEY, base_url='https://openrouter.ai/api/v1')
        message  = client.chat.completions.create(
            model='anthropic/claude-sonnet-4-5',
            max_tokens=2048,
            messages=[{'role': 'user', 'content': GENERATE_PROMPT.format(
                transcript=transcript[:12000], context=context, platform=platform,
                categories=', '.join(CATEGORIES))}]
        )
        skill_markdown = message.choices[0].message.content.strip()
        name        = 'untitled-skill'
        description = ''
        category    = 'Uncategorized'
        for line in skill_markdown.split('\n'):
            if line.startswith('name:'):
                name = line.split(':', 1)[1].strip()
            elif line.startswith('description:'):
                description = line.split(':', 1)[1].strip()
            elif line.startswith('category:'):
                category = line.split(':', 1)[1].strip()
        skill_id    = str(uuid.uuid4())
        skills_data = load_skills()
        skills_data['skills'].append({
            'id':             skill_id,
            'name':           name,
            'description':    description,
            'category':       category,
            'video_url':      video_url,
            'video_id':       video_id,
            'platform':       platform,
            'thumbnail':      thumbnail,
            'skill_markdown': skill_markdown,
            'created_at':     datetime.now().isoformat()
        })
        save_skills(skills_data)
        return jsonify({'skill_markdown': skill_markdown, 'name': name,
                        'description': description, 'category': category, 'id': skill_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/skills', methods=['GET'])
def get_skills():
    if request.headers.get('X-App-Password') != APP_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(load_skills())


@app.route('/skills/<skill_id>', methods=['DELETE'])
def delete_skill(skill_id):
    if request.headers.get('X-App-Password') != APP_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    data   = load_skills()
    before = len(data['skills'])
    data['skills'] = [s for s in data['skills'] if s['id'] != skill_id]
    if len(data['skills']) == before:
        return jsonify({'error': 'Skill not found.'}), 404
    save_skills(data)
    return jsonify({'ok': True})


@app.route('/skills/<skill_id>/download', methods=['GET'])
def download_skill(skill_id):
    if request.headers.get('X-App-Password') != APP_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    from flask import Response
    data  = load_skills()
    skill = next((s for s in data['skills'] if s['id'] == skill_id), None)
    if not skill:
        return jsonify({'error': 'Skill not found.'}), 404
    filename = (skill['name'] or 'skill') + '.md'
    return Response(skill['skill_markdown'], mimetype='text/markdown',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
