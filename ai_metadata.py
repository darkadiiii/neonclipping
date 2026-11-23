"""AI Metadata Engine for NeonClipping: Generates platform-tailored titles, SEO descriptions,
and viral hashtags for YouTube Shorts, Instagram Reels, and TikTok.

Supports Local Ollama (llama3.2/gemma/qwen), Cloud API (Gemini/OpenAI), and a robust
rule-based offline generator that never fails even without an LLM.
"""
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path

SETTINGS_FILE = 'metadata_settings.json'

DEFAULT_HASHTAGS = {
    'gaming': ['#Gaming', '#GamingClips', '#Gamer', '#Gameplay', '#TwitchClips'],
    'funny': ['#FunnyMoments', '#Lol', '#Comedy', '#EpicFail', '#Hilarious'],
    'viral': ['#Shorts', '#Reels', '#TikTok', '#Viral', '#Trending', '#FYP'],
    'action': ['#EpicMoment', '#Insane', '#Clutch', '#Hype']
}

SYSTEM_PROMPT = """You are a viral social media manager specializing in short-form video (YouTube Shorts, Instagram Reels, TikTok).
Analyze the provided video clip transcript, context, and cues. Generate an engaging, high-CTR metadata package in JSON.

Output JSON structure ONLY:
{
  "title": "Punchy title with max 60 chars and 1 relevant emoji",
  "hook": "Strong 5-8 word opening curiosity statement",
  "descriptions": {
    "youtube": "2-3 engaging sentences explaining the moment, ending with a subscribe CTA",
    "tiktok": "Short, trendy, energetic 1-sentence caption",
    "instagram": "Clean aesthetic caption with linebreaks, ending with a follow CTA"
  },
  "hashtags": {
    "youtube": ["#Shorts", "#Gaming", ...5-8 relevant tags],
    "tiktok": ["#fyp", "#viral", ...5-8 trending tags],
    "instagram": ["#reels", "#explorepage", ...8-12 niche & broad tags]
  }
}
"""

def _get_settings(data_dir: Path) -> dict:
    pref_dir = data_dir / 'preferences'
    pref_file = pref_dir / SETTINGS_FILE
    if pref_file.exists():
        try:
            return json.loads(pref_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'provider': 'auto', 'gemini_api_key': '', 'openai_api_key': '', 'ollama_url': 'http://127.0.0.1:11434'}

def _save_settings(data_dir: Path, settings: dict):
    pref_dir = data_dir / 'preferences'
    pref_dir.mkdir(parents=True, exist_ok=True)
    pref_file = pref_dir / SETTINGS_FILE
    pref_file.write_text(json.dumps(settings, indent=2), encoding='utf-8')

def _fallback_generate(title: str, transcript: str, cues: str, streamer: str = '') -> dict:
    """Fast, reliable template-based generator when no LLM is reachable."""
    clean_title = re.sub(r'[^\w\s-]', '', title or 'Epic Gaming Moment').strip()
    words = (transcript or '').split()
    sample = ' '.join(words[:15]) if words else clean_title

    # Determine vibe from cues and transcript
    lower_text = (transcript + ' ' + cues + ' ' + clean_title).lower()
    is_funny = any(w in lower_text for w in ('fail', 'funny', 'laugh', 'omg', 'bhai', 'yaar', 'arre', 'lol', 'police', 'crash'))
    is_action = any(w in lower_text for w in ('kill', 'shot', 'action', 'fast', 'chase', 'explosion', 'fight', 'win', 'supercar'))

    vibe_tags = []
    if is_funny:
        vibe_tags.extend(DEFAULT_HASHTAGS['funny'])
    if is_action:
        vibe_tags.extend(DEFAULT_HASHTAGS['action'])
    vibe_tags.extend(DEFAULT_HASHTAGS['gaming'])
    vibe_tags.extend(DEFAULT_HASHTAGS['viral'])
    unique_tags = list(dict.fromkeys(vibe_tags))

    hook = "Wait, did that really just happen?!" if is_funny else "You won't believe how this ended!"
    display_title = f"{clean_title[:50]} 🤯" if is_action else f"{clean_title[:50]} 😂"
    
    streamer_credit = f"featuring {streamer}" if streamer else ""

    yt_desc = f"{clean_title} {streamer_credit}!\n\nWatch this crazy moment from the stream. Don't forget to like and subscribe for more daily clips!"
    tiktok_desc = f"Nah this was crazy 😂 {clean_title[:40]}"
    ig_desc = f"{clean_title} 🔥\n.\nDrop a comment if you saw this live!\nFollow for more daily clips."

    return {
        "title": display_title[:65],
        "hook": hook,
        "descriptions": {
            "youtube": yt_desc,
            "tiktok": tiktok_desc,
            "instagram": ig_desc
        },
        "hashtags": {
            "youtube": unique_tags[:8],
            "tiktok": [t.lower() for t in unique_tags[:8]],
            "instagram": unique_tags[:12]
        },
        "engine": "template_fallback"
    }

def _query_ollama(prompt: str, ollama_url: str) -> dict:
    payload = {
        "model": "llama3.2:3b",
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": 400}
    }
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read().decode('utf-8'))
        return json.loads(data.get('response', '{}'))

def _query_gemini(prompt: str, api_key: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        data = json.loads(res.read().decode('utf-8'))
        text = data['candidates'][0]['content']['parts'][0]['text']
        return json.loads(text)

def _query_openai(prompt: str, api_key: str) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        data = json.loads(res.read().decode('utf-8'))
        text = data['choices'][0]['message']['content']
        return json.loads(text)

def generate_clip_metadata(data_dir: Path, source_title: str, transcript: str, cues: str = '', streamer: str = '') -> dict:
    settings = _get_settings(data_dir)
    user_prompt = f"""{SYSTEM_PROMPT}

Video Title: {source_title}
Streamer/Creator: {streamer or 'Unknown'}
Visual & Audio Cues: {cues or 'High motion and excitement'}
Transcript of the moment:
\"\"\"{transcript[:2000]}\"\"\"

Generate JSON:"""

    provider = settings.get('provider', 'auto')
    gemini_key = settings.get('gemini_api_key') or os.environ.get('GEMINI_API_KEY', '')
    openai_key = settings.get('openai_api_key') or os.environ.get('OPENAI_API_KEY', '')
    ollama_url = settings.get('ollama_url', 'http://127.0.0.1:11434')

    # Try Cloud Gemini if configured
    if (provider in ('auto', 'gemini')) and gemini_key:
        try:
            res = _query_gemini(user_prompt, gemini_key)
            if 'title' in res and 'descriptions' in res:
                res['engine'] = 'cloud_gemini'
                return res
        except Exception:
            pass

    # Try Cloud OpenAI if configured
    if (provider in ('auto', 'openai')) and openai_key:
        try:
            res = _query_openai(user_prompt, openai_key)
            if 'title' in res and 'descriptions' in res:
                res['engine'] = 'cloud_openai'
                return res
        except Exception:
            pass

    # Try Local Ollama
    if provider in ('auto', 'ollama'):
        try:
            res = _query_ollama(user_prompt, ollama_url)
            if 'title' in res and 'descriptions' in res:
                res['engine'] = 'local_ollama'
                return res
        except Exception:
            pass

    # Clean deterministic fallback
    return _fallback_generate(source_title, transcript, cues, streamer)

def attach(app, data_dir: Path):
    @app.get('/api/metadata/settings')
    def get_meta_settings():
        s = _get_settings(data_dir)
        # Mask keys for security
        return {
            'provider': s.get('provider', 'auto'),
            'has_gemini_key': bool(s.get('gemini_api_key')),
            'has_openai_key': bool(s.get('openai_api_key')),
            'ollama_url': s.get('ollama_url', 'http://127.0.0.1:11434')
        }

    @app.post('/api/metadata/settings')
    def update_meta_settings(body: dict):
        current = _get_settings(data_dir)
        if 'provider' in body:
            current['provider'] = body['provider']
        if 'gemini_api_key' in body and body['gemini_api_key']:
            current['gemini_api_key'] = body['gemini_api_key'].strip()
        if 'openai_api_key' in body and body['openai_api_key']:
            current['openai_api_key'] = body['openai_api_key'].strip()
        if 'ollama_url' in body:
            current['ollama_url'] = body['ollama_url'].strip()
        _save_settings(data_dir, current)
        return {'ok': True, 'provider': current.get('provider')}

    @app.post('/api/metadata/generate')
    def generate_endpoint(body: dict):
        title = body.get('title', '')
        transcript = body.get('transcript', '')
        cues = body.get('cues', '')
        streamer = body.get('streamer', '')
        return generate_clip_metadata(data_dir, title, transcript, cues, streamer)
