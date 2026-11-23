// Social Media Automation & Studio Extension for NeonClipping
(function() {
  'use strict';

  let connectedAccounts = [];
  let currentPublishClip = null;

  // View Navigation Handling
  const views = ['editor', 'library', 'social', 'accounts'];
  
  function switchView(targetView) {
    document.querySelectorAll('.nav').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === targetView);
    });
    views.forEach(v => {
      const el = document.getElementById(v + '-view');
      if (el) el.hidden = (v !== targetView);
    });

    if (targetView === 'accounts') loadAccounts();
    if (targetView === 'social') {
      loadSchedule();
      loadHistory();
    }
  }

  // Setup Nav Listeners
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav[data-view]').forEach(btn => {
      btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    initAccountsUI();
    initPublishModal();
    initSchedulerUI();
    observeClipCards();
  });

  // ACCOUNTS MANAGEMENT
  async function loadAccounts() {
    try {
      const res = await fetch('/api/social/accounts');
      const data = await res.json();
      connectedAccounts = data.accounts || [];
      renderAccountsList();
      loadMetadataSettings();
    } catch (e) {
      console.error('Failed to load accounts', e);
    }
  }

  function renderAccountsList() {
    const list = document.getElementById('accounts-list');
    if (!list) return;

    if (connectedAccounts.length === 0) {
      list.innerHTML = '<p class="muted">No social accounts connected yet. Add one below to start auto-publishing clips.</p>';
      return;
    }

    list.innerHTML = connectedAccounts.map(acc => {
      const icon = acc.platform === 'youtube' ? '▶' : (acc.platform === 'tiktok' ? '🎵' : '📷');
      const name = acc.name || `${acc.platform.toUpperCase()} Account`;
      return `
        <div class="account-card panel" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding:12px 18px">
          <div>
            <b>${icon} ${name}</b> <span class="pill" style="margin-left:8px;font-size:11px">${acc.platform.toUpperCase()}</span>
            <div class="muted" style="font-size:12px;margin-top:4px">Status: ${acc.status || 'Active'} · Connected</div>
          </div>
          <button class="secondary" onclick="window.disconnectAccount('${acc.id}')" style="color:#ff4ba5;border-color:#ff4ba5">Disconnect</button>
        </div>
      `;
    }).join('');
  }

  window.disconnectAccount = async function(id) {
    if (!confirm('Are you sure you want to disconnect this account?')) return;
    try {
      await fetch(`/api/social/accounts/${id}`, { method: 'DELETE' });
      await loadAccounts();
    } catch (e) {
      alert('Error disconnecting: ' + e);
    }
  };

  function initAccountsUI() {
    const addBtn = document.getElementById('btn-add-account');
    const saveAccBtn = document.getElementById('save-manual-acc');
    const dialog = document.getElementById('account-dialog');
    const closeBtn = document.getElementById('acc-close');

    if (addBtn && dialog) {
      addBtn.addEventListener('click', () => dialog.showModal());
    }
    if (closeBtn && dialog) {
      closeBtn.addEventListener('click', () => dialog.close());
    }

    // Google Sign-In button
    const googleLoginBtn = document.getElementById('btn-google-login');
    const saveYtCredsBtn = document.getElementById('save-yt-creds');

    async function checkYtCreds() {
      try {
        const res = await fetch('/api/social/credentials');
        const data = await res.json();
        const yt = data.youtube || {};
        const pill = document.getElementById('yt-keys-pill');
        if (pill) {
          pill.textContent = yt.has_keys ? '✓ Configured' : 'Not Set';
          pill.style.color = yt.has_keys ? 'var(--cyan)' : 'var(--muted)';
        }
        if (document.getElementById('yt-client-id') && yt.client_id) {
          document.getElementById('yt-client-id').value = yt.client_id;
        }
        return yt;
      } catch (e) {
        return {};
      }
    }

    checkYtCreds();

    if (saveYtCredsBtn) {
      saveYtCredsBtn.addEventListener('click', async () => {
        const clientId = document.getElementById('yt-client-id').value.trim();
        const clientSecret = document.getElementById('yt-client-secret').value.trim();
        if (!clientId || !clientSecret) {
          alert('Please enter both Client ID and Client Secret.');
          return;
        }
        await fetch('/api/social/credentials', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({platform: 'youtube', client_id: clientId, client_secret: clientSecret})
        });
        alert('Google Cloud credentials saved! Now click "Sign in with Google / YouTube".');
        checkYtCreds();
      });
    }

    if (googleLoginBtn) {
      googleLoginBtn.addEventListener('click', async () => {
        const yt = await checkYtCreds();
        if (!yt.has_keys) {
          alert('Please enter your Google OAuth Client ID and Secret in the "Google Cloud App Keys Setup" box below first.');
          const det = document.querySelector('#accounts-view details');
          if (det) det.open = true;
          return;
        }
        const port = window.location.port || '8770';
        const redirect = `http://127.0.0.1:${port}/api/social/callback/youtube`;
        const res = await fetch(`/api/social/oauth-url/youtube?client_id=${encodeURIComponent(yt.client_id)}&redirect_uri=${encodeURIComponent(redirect)}`);
        const data = await res.json();
        if (data.url) {
          window.location.href = data.url;
        }
      });
    }

    if (saveAccBtn) {
      saveAccBtn.addEventListener('click', async () => {
        const platform = document.getElementById('acc-platform').value;
        const name = document.getElementById('acc-name').value;
        const token = document.getElementById('acc-token').value;
        const refresh = document.getElementById('acc-refresh').value;
        const igUser = document.getElementById('acc-ig-user').value;

        if (!token) {
          alert('Please enter an Access Token or API Key.');
          return;
        }

        try {
          const res = await fetch('/api/social/accounts/manual', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              platform,
              name,
              access_token: token,
              refresh_token: refresh,
              ig_user_id: igUser
            })
          });
          if (!res.ok) throw new Error(await res.text());
          dialog.close();
          await loadAccounts();
        } catch (e) {
          alert('Failed to save account: ' + e.message);
        }
      });
    }

    // Metadata Settings
    const saveMetaBtn = document.getElementById('save-meta-settings');
    if (saveMetaBtn) {
      saveMetaBtn.addEventListener('click', async () => {
        const provider = document.getElementById('meta-provider').value;
        const geminiKey = document.getElementById('meta-gemini-key').value;
        const openaiKey = document.getElementById('meta-openai-key').value;

        await fetch('/api/metadata/settings', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            provider,
            gemini_api_key: geminiKey,
            openai_api_key: openaiKey
          })
        });
        alert('AI Metadata settings saved!');
      });
    }
  }

  async function loadMetadataSettings() {
    try {
      const res = await fetch('/api/metadata/settings');
      const data = await res.json();
      if (document.getElementById('meta-provider')) {
        document.getElementById('meta-provider').value = data.provider || 'auto';
      }
      if (document.getElementById('meta-gemini-status')) {
        document.getElementById('meta-gemini-status').textContent = data.has_gemini_key ? '● Configured' : '○ Not set';
      }
      if (document.getElementById('meta-openai-status')) {
        document.getElementById('meta-openai-status').textContent = data.has_openai_key ? '● Configured' : '○ Not set';
      }
    } catch (e) {}
  }

  // SCHEDULER & HISTORY
  async function loadSchedule() {
    try {
      const res = await fetch('/api/social/schedule');
      const data = await res.json();
      const list = document.getElementById('schedule-list');
      const countEl = document.getElementById('schedule-count');
      const posts = data.posts || [];

      if (countEl) countEl.textContent = posts.filter(p => p.status === 'pending').length;

      if (!list) return;
      if (posts.length === 0) {
        list.innerHTML = '<p class="muted">No clips scheduled. Click "🚀 Post / Schedule" on any clip to schedule it.</p>';
        return;
      }

      list.innerHTML = posts.map(p => {
        const timeStr = new Date(p.scheduled_time * 1000).toLocaleString();
        const statusClass = p.status === 'published' ? 'color:#58e8f7' : (p.status === 'failed' ? 'color:#ff4ba5' : 'color:#d4fb58');
        const errDesc = p.status === 'failed' && p.result && p.result.error ? `<div style="color:#ff4ba5;font-size:12px;margin-top:4px;background:#2a0b18;padding:6px 10px;border-radius:6px">⚠️ Upload Failed: Google API ko valid OAuth Permission Token chahiye (Channel URL se upload allow nahi karta).</div>` : '';
        return `
          <div class="panel" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding:12px 18px">
            <div>
              <b>${p.platform.toUpperCase()}</b> · <span style="${statusClass}">● ${p.status.toUpperCase()}</span>
              <div class="muted" style="font-size:12px;margin-top:2px">Scheduled: ${timeStr}</div>
              <div style="font-size:13px;margin-top:4px">Title: <i>${p.metadata.title || p.clip_id}</i></div>
              ${errDesc}
            </div>
            <div style="display:flex;gap:8px">
              ${p.status === 'pending' ? `
                <button class="primary" onclick="window.triggerScheduleNow('${p.id}')">Post Now</button>
                <button class="secondary" onclick="window.cancelSchedule('${p.id}')">Cancel</button>
              ` : ''}
              ${p.status === 'failed' ? `
                <button class="secondary" onclick="window.cancelSchedule('${p.id}')">Dismiss</button>
              ` : ''}
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error(e);
    }
  }

  window.triggerScheduleNow = async function(id) {
    await fetch(`/api/social/schedule/${id}/publish-now`, { method: 'POST' });
    loadSchedule();
  };

  window.cancelSchedule = async function(id) {
    await fetch(`/api/social/schedule/${id}`, { method: 'DELETE' });
    loadSchedule();
  };

  async function loadHistory() {
    try {
      const res = await fetch('/api/social/history');
      const data = await res.json();
      const list = document.getElementById('history-list');
      if (!list) return;

      const history = data.history || [];
      if (history.length === 0) {
        list.innerHTML = '<p class="muted">No publish history yet.</p>';
        return;
      }

      list.innerHTML = history.slice(0, 20).map(h => {
        const timeStr = new Date(h.timestamp * 1000).toLocaleTimeString();
        if (h.success) {
          return `
            <div style="padding:8px 0;border-bottom:1px solid var(--line);display:flex;justify-content:space-between">
              <span><b>${h.platform.toUpperCase()}</b>: <a href="${h.post_url}" target="_blank" rel="noopener" style="color:var(--cyan)">${h.title || 'Live Post'} ↗</a></span>
              <span class="muted" style="font-size:12px">${timeStr}</span>
            </div>
          `;
        } else {
          return `
            <div style="padding:8px 0;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;color:#ff4ba5">
              <span><b>${h.platform.toUpperCase()}</b> failed: ${h.error}</span>
              <span class="muted" style="font-size:12px">${timeStr}</span>
            </div>
          `;
        }
      }).join('');
    } catch (e) {}
  }

  function initSchedulerUI() {
    const refreshBtn = document.getElementById('btn-refresh-schedule');
    if (refreshBtn) refreshBtn.addEventListener('click', () => { loadSchedule(); loadHistory(); });
  }

  // PUBLISH & SCHEDULE DIALOG
  function initPublishModal() {
    const dialog = document.getElementById('publish-dialog');
    const closeBtn = document.getElementById('pub-close');
    const genAiBtn = document.getElementById('pub-gen-ai');
    const submitBtn = document.getElementById('pub-submit');

    if (closeBtn && dialog) {
      closeBtn.addEventListener('click', () => dialog.close());
    }

    // Google Sign-In button
    const googleLoginBtn = document.getElementById('btn-google-login');
    const saveYtCredsBtn = document.getElementById('save-yt-creds');

    async function checkYtCreds() {
      try {
        const res = await fetch('/api/social/credentials');
        const data = await res.json();
        const yt = data.youtube || {};
        const pill = document.getElementById('yt-keys-pill');
        if (pill) {
          pill.textContent = yt.has_keys ? '✓ Configured' : 'Not Set';
          pill.style.color = yt.has_keys ? 'var(--cyan)' : 'var(--muted)';
        }
        if (document.getElementById('yt-client-id') && yt.client_id) {
          document.getElementById('yt-client-id').value = yt.client_id;
        }
        return yt;
      } catch (e) {
        return {};
      }
    }

    checkYtCreds();

    if (saveYtCredsBtn) {
      saveYtCredsBtn.addEventListener('click', async () => {
        const clientId = document.getElementById('yt-client-id').value.trim();
        const clientSecret = document.getElementById('yt-client-secret').value.trim();
        if (!clientId || !clientSecret) {
          alert('Please enter both Client ID and Client Secret.');
          return;
        }
        await fetch('/api/social/credentials', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({platform: 'youtube', client_id: clientId, client_secret: clientSecret})
        });
        alert('Google Cloud credentials saved! Now click "Sign in with Google / YouTube".');
        checkYtCreds();
      });
    }

    if (googleLoginBtn) {
      googleLoginBtn.addEventListener('click', async () => {
        const yt = await checkYtCreds();
        if (!yt.has_keys) {
          alert('Please enter your Google OAuth Client ID and Secret in the "Google Cloud App Keys Setup" box below first.');
          const det = document.querySelector('#accounts-view details');
          if (det) det.open = true;
          return;
        }
        const port = window.location.port || '8770';
        const redirect = `http://127.0.0.1:${port}/api/social/callback/youtube`;
        const res = await fetch(`/api/social/oauth-url/youtube?client_id=${encodeURIComponent(yt.client_id)}&redirect_uri=${encodeURIComponent(redirect)}`);
        const data = await res.json();
        if (data.url) {
          window.location.href = data.url;
        }
      });
    }

    if (genAiBtn) {
      genAiBtn.addEventListener('click', async () => {
        if (!currentPublishClip) return;
        genAiBtn.disabled = true;
        genAiBtn.textContent = '✨ Generating with AI...';

        try {
          const res = await fetch('/api/metadata/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              title: currentPublishClip.title || 'Clip',
              transcript: currentPublishClip.transcript || '',
              cues: currentPublishClip.cues || ''
            })
          });
          const meta = await res.json();
          document.getElementById('pub-title').value = meta.title || '';
          
          const platform = document.getElementById('pub-platform').value;
          const desc = meta.descriptions ? meta.descriptions[platform] : '';
          const tags = meta.hashtags ? (meta.hashtags[platform] || []).join(' ') : '';
          document.getElementById('pub-desc').value = `${desc}\n\n${tags}`;
        } catch (e) {
          alert('Error generating metadata: ' + e);
        } finally {
          genAiBtn.disabled = false;
          genAiBtn.textContent = '✨ Re-generate AI Metadata';
        }
      });
    }

    if (submitBtn) {
      submitBtn.addEventListener('click', async () => {
        if (!currentPublishClip) return;
        const platform = document.getElementById('pub-platform').value;
        const accountId = document.getElementById('pub-account').value;
        const title = document.getElementById('pub-title').value.trim();
        const desc = document.getElementById('pub-desc').value.trim();
        const isSchedule = document.getElementById('pub-opt-schedule').checked;
        const schedTime = document.getElementById('pub-sched-time').value;

        if (!accountId) {
          alert('Please select or connect a social account first.');
          return;
        }

        const metadata = {
          title: title || 'New Highlight Clip',
          description: desc,
          tags: (desc.match(/#\w+/g) || []).map(t => t.replace('#', '')),
          privacy: document.getElementById('pub-privacy').value
        };

        submitBtn.disabled = true;
        submitBtn.textContent = 'Processing...';

        try {
          if (isSchedule) {
            if (!schedTime) {
              alert('Please choose a schedule date and time.');
              submitBtn.disabled = false;
              submitBtn.textContent = 'Confirm & Schedule';
              return;
            }
            const epoch = new Date(schedTime).getTime() / 1000;
            const res = await fetch('/api/social/schedule', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                clip_id: currentPublishClip.id,
                platform,
                account_id: accountId,
                metadata,
                scheduled_time: epoch
              })
            });
            if (!res.ok) throw new Error(await res.text());
            alert('Clip scheduled successfully!');
            dialog.close();
            switchView('social');
          } else {
            const res = await fetch('/api/social/publish', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                clip_id: currentPublishClip.id,
                platform,
                account_id: accountId,
                metadata
              })
            });
            const data = await res.json();
            if (data.success) {
              alert(`Published successfully! Live link: ${data.post_url}`);
              dialog.close();
              switchView('social');
            } else {
              throw new Error(data.error || 'Publish failed');
            }
          }
        } catch (e) {
          alert('Error: ' + e.message);
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Confirm & Publish';
        }
      });
    }

    // Toggle schedule time visibility
    const optNow = document.getElementById('pub-opt-now');
    const optSched = document.getElementById('pub-opt-schedule');
    const schedWrap = document.getElementById('pub-sched-wrap');
    if (optNow && optSched && schedWrap) {
      optNow.addEventListener('change', () => { schedWrap.hidden = true; });
      optSched.addEventListener('change', () => { schedWrap.hidden = false; });
    }
  }

  window.openPublishModal = async function(clipId, title, transcript, cues) {
    currentPublishClip = { id: clipId, title, transcript, cues };
    const dialog = document.getElementById('publish-dialog');
    if (!dialog) return;

    // Refresh accounts in select
    await loadAccounts();
    const accSelect = document.getElementById('pub-account');
    if (accSelect) {
      if (connectedAccounts.length === 0) {
        accSelect.innerHTML = '<option value="">No accounts connected (Add in Connected Accounts)</option>';
      } else {
        accSelect.innerHTML = connectedAccounts.map(a => `<option value="${a.id}">${a.platform.toUpperCase()} - ${a.name}</option>`).join('');
      }
    }

    document.getElementById('pub-title').value = title || 'Epic Moment';
    document.getElementById('pub-desc').value = '#Shorts #Gaming #Viral';
    
    // Set default schedule time to tomorrow 18:00
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(18, 0, 0, 0);
    document.getElementById('pub-sched-time').value = tomorrow.toISOString().slice(0, 16);

    dialog.showModal();
  };

  // OBSERVE CLIP CARDS IN UI & INJECT "🚀 Post / Schedule" BUTTON
  function observeClipCards() {
    function injectButtons() {
      // Library view cards
      document.querySelectorAll('#library .clip-card, #make-grid .make-card').forEach(card => {
        if (card.querySelector('.btn-publish-social')) return;
        
        // Find clip id
        let clipId = card.dataset.file || card.dataset.id;
        if (!clipId) {
          const dl = card.querySelector('a[download]');
          if (dl) {
            const m = (dl.getAttribute('href') || '').match(/\/media\/([a-f0-9]+)/);
            if (m) clipId = m[1];
          }
        }
        if (!clipId) return;

        const title = (card.querySelector('b, h3') || {}).textContent || 'Clip';
        
        const btn = document.createElement('button');
        btn.className = 'btn-publish-social primary';
        btn.style.cssText = 'font-size:11px;padding:4px 8px;margin-top:6px;width:100%;background:linear-gradient(90deg,#ff4ba5,#9d4edd);border:none;cursor:pointer;border-radius:6px;font-weight:700';
        btn.textContent = '🚀 Post / Schedule';
        btn.onclick = (e) => {
          e.stopPropagation();
          window.openPublishModal(clipId, title, '', '');
        };

        const actions = card.querySelector('.actions, .card-actions, footer') || card;
        actions.appendChild(btn);
      });
    }

    setInterval(injectButtons, 2000);
  }

})();
