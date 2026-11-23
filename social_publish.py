"""Direct Social Publishing Engine for NeonClipping:
Implements video uploading protocols for YouTube Shorts, TikTok, and Instagram Reels.
"""
import json
import mimetypes
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from fastapi import HTTPException
import social_auth

HISTORY_FILE = 'social_history.json'

def _get_history(data_dir: Path) -> list:
    p = data_dir / 'preferences' / HISTORY_FILE
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return []

def _record_history(data_dir: Path, item: dict):
    history = _get_history(data_dir)
    history.insert(0, item)
    p = data_dir / 'preferences' / HISTORY_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(history[:200], indent=2), encoding='utf-8')

def upload_youtube_short(video_path: Path, metadata: dict, account: dict) -> dict:
    """Uploads vertical MP4 to YouTube using YouTube Data API v3 Resumable Upload."""
    token = account.get('access_token')
    if not token:
        raise ValueError('YouTube account has no valid access token')

    title = metadata.get('title', 'NeonClipping Highlight')
    if '#Shorts' not in title and '#shorts' not in title:
        title = f"{title[:90]} #Shorts"

    desc = metadata.get('description', '')
    tags = metadata.get('tags', ['Shorts', 'Gaming'])
    privacy = metadata.get('privacy', 'public')

    snippet = {
        'snippet': {
            'title': title[:100],
            'description': desc,
            'tags': tags,
            'categoryId': '20' # Gaming
        },
        'status': {
            'privacyStatus': privacy,
            'selfDeclaredMadeForKids': False
        }
    }

    # Step 1: Initialize Resumable Upload
    init_url = 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status'
    init_req = urllib.request.Request(
        init_url,
        data=json.dumps(snippet).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Upload-Content-Type': 'video/mp4',
            'X-Upload-Content-Length': str(video_path.stat().st_size)
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(init_req, timeout=30) as res:
            upload_url = res.headers.get('Location')
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        raise RuntimeError(f"YouTube upload init failed: {err_msg}")

    if not upload_url:
        raise RuntimeError("No upload location returned by YouTube")

    # Step 2: Upload Video File Stream
    with open(video_path, 'rb') as f:
        video_data = f.read()

    upload_req = urllib.request.Request(
        upload_url,
        data=video_data,
        headers={
            'Content-Type': 'video/mp4',
            'Content-Length': str(len(video_data))
        },
        method='PUT'
    )

    try:
        with urllib.request.urlopen(upload_req, timeout=120) as res:
            resp_data = json.loads(res.read().decode('utf-8'))
            video_id = resp_data.get('id')
            return {
                'success': True,
                'platform': 'youtube',
                'video_id': video_id,
                'post_url': f"https://youtube.com/shorts/{video_id}",
                'title': title
            }
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        raise RuntimeError(f"YouTube binary upload failed: {err_msg}")

def upload_tiktok_video(video_path: Path, metadata: dict, account: dict) -> dict:
    """Publishes video to TikTok via TikTok Content Posting API."""
    token = account.get('access_token')
    if not token:
        raise ValueError('TikTok account missing access token')

    title = metadata.get('title', 'New Clip')
    file_size = video_path.stat().st_size

    init_url = 'https://open.tiktokapis.com/v2/post/publish/video/init/'
    payload = {
        'post_info': {
            'title': title[:150],
            'privacy_level': metadata.get('privacy', 'PUBLIC_TO_USERS'),
            'disable_duet': False,
            'disable_stitch': False,
            'disable_comment': False,
            'video_cover_timestamp_ms': 1000
        },
        'source_info': {
            'source': 'FILE_UPLOAD',
            'video_size': file_size,
            'chunk_size': file_size,
            'total_chunk_count': 1
        }
    }

    req = urllib.request.Request(
        init_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.loads(res.read().decode('utf-8')).get('data', {})
            upload_url = data.get('upload_url')
            publish_id = data.get('publish_id')
    except Exception as e:
        raise RuntimeError(f"TikTok init failed: {str(e)}")

    if not upload_url:
        raise RuntimeError("No upload URL returned by TikTok")

    with open(video_path, 'rb') as f:
        file_bytes = f.read()

    put_req = urllib.request.Request(
        upload_url,
        data=file_bytes,
        headers={
            'Content-Range': f'bytes 0-{file_size-1}/{file_size}',
            'Content-Type': 'video/mp4'
        },
        method='PUT'
    )
    with urllib.request.urlopen(put_req, timeout=120):
        pass

    return {
        'success': True,
        'platform': 'tiktok',
        'publish_id': publish_id,
        'post_url': f"https://www.tiktok.com/@me (Publish ID: {publish_id})",
        'title': title
    }

def upload_instagram_reel(video_path: Path, metadata: dict, account: dict, server_url: str = 'http://127.0.0.1:8770') -> dict:
    """Uploads Reel via Instagram Graph API. Requires accessible video URL or direct stream."""
    token = account.get('access_token')
    ig_user_id = account.get('ig_user_id')
    if not (token and ig_user_id):
        raise ValueError('Instagram account missing access token or IG User ID')

    caption = f"{metadata.get('title', '')}\n\n{metadata.get('description', '')}\n\n{' '.join(metadata.get('tags', []))}"
    
    # Instagram requires a public video URL to ingest.
    # When running locally, if user provided a public webhook/tunnel, use it, otherwise prepare container.
    public_url = metadata.get('public_video_url') or f"{server_url}/media/{video_path.stem}"

    # Step 1: Create Container
    url = f"https://graph.facebook.com/v20.0/{ig_user_id}/media"
    data = urllib.parse.urlencode({
        'media_type': 'REELS',
        'video_url': public_url,
        'caption': caption[:2200],
        'share_to_feed': 'true',
        'access_token': token
    }).encode('utf-8')

    req = urllib.request.Request(url, data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            container_id = json.loads(res.read().decode('utf-8')).get('id')
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Instagram container creation failed: {e.read().decode('utf-8')}")

    # Step 2: Poll container status
    status_url = f"https://graph.facebook.com/v20.0/{container_id}?fields=status_code&access_token={token}"
    for _ in range(15):
        time.sleep(4)
        try:
            with urllib.request.urlopen(urllib.request.Request(status_url), timeout=10) as s_res:
                s_data = json.loads(s_res.read().decode('utf-8'))
                if s_data.get('status_code') == 'FINISHED':
                    break
        except Exception:
            pass

    # Step 3: Publish Container
    publish_url = f"https://graph.facebook.com/v20.0/{ig_user_id}/media_publish"
    p_data = urllib.parse.urlencode({
        'creation_id': container_id,
        'access_token': token
    }).encode('utf-8')

    with urllib.request.urlopen(urllib.request.Request(publish_url, data=p_data, method='POST'), timeout=30) as p_res:
        published = json.loads(p_res.read().decode('utf-8'))
        media_id = published.get('id')
        return {
            'success': True,
            'platform': 'instagram',
            'media_id': media_id,
            'post_url': f"https://www.instagram.com/reel/{media_id}",
            'title': metadata.get('title')
        }

def publish_clip(data_dir: Path, clip_id: str, platform: str, account_id: str, metadata: dict) -> dict:
    video_path = data_dir / f"{clip_id}.mp4"
    if not video_path.exists():
        raise HTTPException(404, f"Clip file {clip_id}.mp4 not found in data folder")

    account = social_auth.get_account_by_id(data_dir, account_id)
    account = social_auth.refresh_token_if_needed(data_dir, account)

    result = {}
    try:
        if platform == 'youtube':
            result = upload_youtube_short(video_path, metadata, account)
        elif platform == 'tiktok':
            result = upload_tiktok_video(video_path, metadata, account)
        elif platform == 'instagram':
            result = upload_instagram_reel(video_path, metadata, account)
        else:
            raise HTTPException(400, f"Unsupported platform: {platform}")
        
        result['timestamp'] = time.time()
        result['clip_id'] = clip_id
        result['account_name'] = account.get('name')
        _record_history(data_dir, result)
        return result
    except Exception as e:
        err_item = {
            'success': False,
            'error': str(e),
            'platform': platform,
            'clip_id': clip_id,
            'account_name': account.get('name'),
            'timestamp': time.time()
        }
        _record_history(data_dir, err_item)
        raise HTTPException(500, f"Publishing failed: {str(e)}")

def attach(app, data_dir: Path):
    @app.get('/api/social/history')
    def get_history():
        return {'history': _get_history(data_dir)}

    @app.post('/api/social/publish')
    def publish_endpoint(body: dict):
        clip_id = body.get('clip_id')
        platform = body.get('platform')
        account_id = body.get('account_id')
        metadata = body.get('metadata', {})
        if not (clip_id and platform and account_id):
            raise HTTPException(400, 'clip_id, platform, and account_id are required')
        return publish_clip(data_dir, clip_id, platform, account_id, metadata)
