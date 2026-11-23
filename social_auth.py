"""Social Auth & Token Vault for NeonClipping:
Manages OAuth 2.0 connections, manual token setups, and token refresh
for YouTube Shorts, TikTok, and Instagram Reels.
"""
import base64
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

STORE_FILE = 'social_accounts.json'

# Platform OAuth Endpoints & Scopes
OAUTH_CONFIG = {
    'youtube': {
        'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token_url': 'https://oauth2.googleapis.com/token',
        'scope': 'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly',
        'prompt': 'consent',
        'access_type': 'offline'
    },
    'tiktok': {
        'auth_url': 'https://www.tiktok.com/v2/auth/authorize/',
        'token_url': 'https://open.tiktokapis.com/v2/oauth/token/',
        'scope': 'user.info.basic,video.upload,video.publish'
    },
    'instagram': {
        'auth_url': 'https://www.facebook.com/v20.0/dialog/oauth',
        'token_url': 'https://graph.facebook.com/v20.0/oauth/access_token',
        'scope': 'instagram_basic,instagram_content_publish,pages_show_list'
    }
}

def _accounts_path(data_dir: Path) -> Path:
    p = data_dir / 'preferences' / STORE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def load_accounts(data_dir: Path) -> list:
    p = _accounts_path(data_dir)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return []

def save_accounts(data_dir: Path, accounts: list):
    p = _accounts_path(data_dir)
    p.write_text(json.dumps(accounts, indent=2), encoding='utf-8')

def get_account_by_id(data_dir: Path, account_id: str) -> dict:
    for acc in load_accounts(data_dir):
        if acc['id'] == account_id:
            return acc
    raise HTTPException(404, 'Social account not found')

def sanitize_account(acc: dict) -> dict:
    copy = dict(acc)
    # Mask tokens for frontend consumption
    if 'access_token' in copy:
        copy['has_access_token'] = bool(copy['access_token'])
        del copy['access_token']
    if 'refresh_token' in copy:
        copy['has_refresh_token'] = bool(copy['refresh_token'])
        del copy['refresh_token']
    if 'client_secret' in copy:
        del copy['client_secret']
    return copy

def refresh_token_if_needed(data_dir: Path, account: dict) -> dict:
    """Refreshes access token if expired (currently for YouTube / TikTok)."""
    now = time.time()
    expires_at = account.get('expires_at', 0)
    if expires_at and expires_at > now + 120:
        return account # Still valid

    platform = account.get('platform')
    refresh_tok = account.get('refresh_token')

    if platform == 'youtube' and refresh_tok:
        client_id = account.get('client_id')
        client_secret = account.get('client_secret')
        if not (client_id and client_secret):
            return account
        
        data = urllib.parse.urlencode({
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_tok,
            'grant_type': 'refresh_token'
        }).encode('utf-8')

        req = urllib.request.Request(OAUTH_CONFIG['youtube']['token_url'], data=data, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                payload = json.loads(res.read().decode('utf-8'))
                account['access_token'] = payload['access_token']
                account['expires_at'] = now + payload.get('expires_in', 3600)
                # Save updated token
                all_accs = load_accounts(data_dir)
                for i, a in enumerate(all_accs):
                    if a['id'] == account['id']:
                        all_accs[i] = account
                        break
                save_accounts(data_dir, all_accs)
        except Exception as e:
            account['status'] = f'Refresh failed: {str(e)[:100]}'
            
    return account

def attach(app, data_dir: Path):
    @app.get('/api/social/accounts')
    def list_accounts():
        accs = load_accounts(data_dir)
        return {'accounts': [sanitize_account(a) for a in accs]}

    @app.delete('/api/social/accounts/{account_id}')
    def delete_account(account_id: str):
        accs = load_accounts(data_dir)
        new_accs = [a for a in accs if a['id'] != account_id]
        save_accounts(data_dir, new_accs)
        return {'ok': True, 'count': len(new_accs)}

    @app.post('/api/social/accounts/manual')
    def add_manual_account(body: dict):
        platform = body.get('platform')
        if platform not in ('youtube', 'tiktok', 'instagram'):
            raise HTTPException(400, 'Invalid platform')
        name = body.get('name', '').strip() or f'{platform.title()} Account'
        
        acc_id = uuid.uuid4().hex[:12]
        new_acc = {
            'id': acc_id,
            'platform': platform,
            'name': name,
            'access_token': body.get('access_token', '').strip(),
            'refresh_token': body.get('refresh_token', '').strip(),
            'client_id': body.get('client_id', '').strip(),
            'client_secret': body.get('client_secret', '').strip(),
            'ig_user_id': body.get('ig_user_id', '').strip(),
            'channel_id': body.get('channel_id', '').strip(),
            'status': 'Connected',
            'connected_at': time.time(),
            'expires_at': time.time() + (86400 * 60 if platform == 'instagram' else 3600)
        }
        
        accs = load_accounts(data_dir)
        accs.append(new_acc)
        save_accounts(data_dir, accs)
        return {'ok': True, 'account': sanitize_account(new_acc)}

    @app.get('/api/social/oauth-url/{platform}')
    def get_oauth_url(platform: str, client_id: str, redirect_uri: str):
        if platform not in OAUTH_CONFIG:
            raise HTTPException(400, 'Platform not supported')
        conf = OAUTH_CONFIG[platform]
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': conf['scope']
        }
        if 'access_type' in conf:
            params['access_type'] = conf['access_type']
        if 'prompt' in conf:
            params['prompt'] = conf['prompt']
        
        url = conf['auth_url'] + '?' + urllib.parse.urlencode(params)
        return {'url': url}

    @app.get('/api/social/credentials')
    def get_credentials():
        p = data_dir / 'preferences' / 'oauth_credentials.json'
        if not p.exists():
            return {'youtube': {'has_keys': False, 'client_id': ''}}
        try:
            c = json.loads(p.read_text(encoding='utf-8'))
            yt = c.get('youtube', {})
            return {'youtube': {'has_keys': bool(yt.get('client_id') and yt.get('client_secret')), 'client_id': yt.get('client_id', '')}}
        except Exception:
            return {'youtube': {'has_keys': False, 'client_id': ''}}

    @app.post('/api/social/credentials')
    def save_credentials(body: dict):
        p = data_dir / 'preferences' / 'oauth_credentials.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        current = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        platform = body.get('platform', 'youtube')
        current[platform] = {
            'client_id': body.get('client_id', '').strip(),
            'client_secret': body.get('client_secret', '').strip()
        }
        p.write_text(json.dumps(current, indent=2), encoding='utf-8')
        return {'ok': True}

    @app.get('/api/social/callback/{platform}')
    def oauth_callback(platform: str, code: str = None, error: str = None):
        if error:
            return RedirectResponse(f'/?error={urllib.parse.quote(error)}')
        if not code:
            return RedirectResponse('/?error=No+code+received')
        
        p = data_dir / 'preferences' / 'oauth_credentials.json'
        creds = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        plat_creds = creds.get(platform, {})
        client_id = plat_creds.get('client_id')
        client_secret = plat_creds.get('client_secret')
        port = os.environ.get('NEONCLIPPING_PORT', '8770')
        redirect_uri = f"http://127.0.0.1:{port}/api/social/callback/{platform}"
        
        if not (client_id and client_secret):
            return RedirectResponse('/?error=OAuth+credentials+missing')
        
        token_data = urllib.parse.urlencode({
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }).encode('utf-8')
        
        req = urllib.request.Request(OAUTH_CONFIG[platform]['token_url'], data=token_data, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                payload = json.loads(res.read().decode('utf-8'))
                access_token = payload['access_token']
                refresh_token = payload.get('refresh_token', '')
                expires_in = payload.get('expires_in', 3600)
                
                channel_name = f"{platform.title()} Account"
                if platform == 'youtube':
                    try:
                        ch_req = urllib.request.Request(
                            'https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true',
                            headers={'Authorization': f'Bearer {access_token}'}
                        )
                        with urllib.request.urlopen(ch_req, timeout=10) as ch_res:
                            ch_data = json.loads(ch_res.read().decode('utf-8'))
                            channel_name = ch_data['items'][0]['snippet']['title']
                    except Exception:
                        pass
                
                new_acc = {
                    'id': uuid.uuid4().hex[:12],
                    'platform': platform,
                    'name': channel_name,
                    'access_token': access_token,
                    'refresh_token': refresh_token,
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'status': 'Connected',
                    'connected_at': time.time(),
                    'expires_at': time.time() + expires_in
                }
                accs = load_accounts(data_dir)
                accs.append(new_acc)
                save_accounts(data_dir, accs)
                return RedirectResponse('/?connected=' + platform)
        except Exception as e:
            return RedirectResponse(f'/?error={urllib.parse.quote(str(e))}')
