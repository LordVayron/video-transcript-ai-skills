# Video Transcript + AI Skills Tool

A local web app that extracts transcripts from YouTube, TikTok, and Instagram Reels — and turns them into production-ready Claude AI Skills using OpenRouter.

Runs entirely on your own machine at `http://127.0.0.1:5000`. No hosting required.

---

## What it does

**Transcripts tab**
- Paste any YouTube, TikTok, or Instagram Reels URL
- Instantly extracts the full transcript (no timestamps)
- Falls back to OpenAI Whisper audio transcription if no captions exist
- Shows video thumbnail, displays transcript, download as `.txt`
- Tracks monthly Whisper API spend

**AI Skills tab**
- Paste a video URL and extract its transcript
- Click "Turn into AI Skill" — Claude analyzes the content and suggests 2 skill directions
- Add your own context or pick a suggestion, then generate a full Claude Code skill
- Download the skill as a `.md` file ready to upload to Claude
- Skills are auto-saved to your local Skills Vault

**Skills Vault**
- All your generated skills in one place
- Each skill shows the video thumbnail, name, category, and description
- Filter by category (13 categories available)
- Download any skill as `.md` or delete it
- Hover animations on cards

---

## Requirements

- Python 3.8+
- An [OpenAI API key](https://platform.openai.com/) (for Whisper audio transcription — only used when a video has no captions)
- An [OpenRouter API key](https://openrouter.ai/) (for Claude skill generation)

---

## Setup

**1. Clone or download the repo**
```bash
git clone https://github.com/LordVayron/video-transcript-ai-skills.git
cd video-transcript-ai-skills
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Add your API keys**

Create a `.env` file in the project folder:
```
OPENAI_API_KEY=your-openai-key-here
OPENROUTER_API_KEY=your-openrouter-key-here
```

**4. Run the app**
```bash
python app.py
```

**5. Open in your browser**
```
http://127.0.0.1:5000
```

---

## Auto-start on Windows (optional)

To have the app start silently every time you log into Windows:

1. Open `start_silent.vbs` and replace the path with your actual project folder path
2. Copy `start_silent.vbs` path
3. Create a file called `video_transcript.bat` in your Windows Startup folder:
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`

   Contents:
   ```bat
   @echo off
   wscript "C:\YOUR\PATH\TO\start_silent.vbs"
   ```

The app will now start in the background on every login.

---

## Skill Categories

Skills are automatically assigned to one of these 13 categories:

- Document & File Creation
- Reading & Extraction
- Writing & Content
- Strategy & Analysis
- Brand & Voice
- Platform-Specific
- Marketing & Advertising
- Development & Code
- Design & Visual
- Data & Spreadsheets
- Workflow & Automation
- Product Knowledge
- Meta / Skill Tooling

---

## Notes

- YouTube transcripts are free and instant (no API cost)
- Whisper is only used for TikTok/Instagram videos with no captions (~$0.006/min)
- Skill generation uses Claude via OpenRouter (~$0.01–0.05 per skill depending on length)
- Your skills and usage data are stored locally (`skills.json`, `usage.json`) and never uploaded
