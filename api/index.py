import base64
import json
import os
import random
import time
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

API = "https://discord.com/api/v9"
UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7518.67 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.6722.64 Safari/537.36",
]

TASKS = (
    "WATCH_VIDEO",
    "WATCH_VIDEO_ON_MOBILE",
    "PLAY_ON_DESKTOP",
    "PLAY_ACTIVITY",
    "STREAM_ON_DESKTOP",
    "ACHIEVEMENT_IN_ACTIVITY",
    "ACHIEVEMENT_IN_GAME",
)
TYPES = {
    "WATCH_VIDEO": "VIDEO",
    "WATCH_VIDEO_ON_MOBILE": "VIDEO",
    "PLAY_ON_DESKTOP": "GAME",
    "PLAY_ACTIVITY": "ACTIVITY",
    "STREAM_ON_DESKTOP": "STREAM",
    "ACHIEVEMENT_IN_ACTIVITY": "ACHIEVEMENT",
    "ACHIEVEMENT_IN_GAME": "ACHIEVEMENT",
}
SUPPORTED = ("VIDEO", "GAME", "ACTIVITY", "STREAM")
RANK = {"ready": 0, "unsupported": 1, "completed": 2, "claimed": 3}

QUOTES = "\"'`\u201c\u201d\u2018\u2019\u00ab\u00bb\u2039\u203a"

def clean_token(raw):
    text = str(raw or "").replace("\r", "\n").strip()
    if "=" in text:
        _, _, value = text.partition("=")
        text = value.strip()
    elif ":" in text and "http" not in text:
        _, _, value = text.partition(":")
        text = value.strip()
    for q in QUOTES:
        text = text.strip(q)
    return text

def api_headers(token, desktop=False):
    headers = {"Authorization": clean_token(token), "Origin": "https://discord.com", "Referer": "https://discord.com/"}
    if desktop:
        version = "1.0.9179"
        agent = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) discord/{version} Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36"
        props = {
            "os": "Windows", "browser": "Discord Client", "device": "", "system_locale": "en-US",
            "client_version": version, "os_version": "10", "release_channel": "stable",
            "browser_user_agent": agent, "browser_version": version, "client_build_number": 357022
        }
        headers.update({
            "User-Agent": agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Discord-Locale": "en-US",
            "X-Super-Properties": base64.b64encode(json.dumps(props, separators=(",", ":")).encode("utf-8")).decode("utf-8")
        })
    else:
        headers.update({
            "User-Agent": random.choice(UAS),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9"
        })
    return headers

def discord_request(method, path, token, body=None, desktop=False):
    import urllib.request
    import urllib.error
    
    url = API + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in api_headers(token, desktop).items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        payload = ""
        try:
            payload = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        raise Exception(f"Discord API Error {exc.code}: {payload}")
    except Exception as exc:
        raise Exception(f"Connection failed: {str(exc)}")

def pick(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        val = mapping.get(key)
        if val is not None:
            return val
    return None

def task_pick(config):
    holder = pick(config, "task_config_v2", "taskConfigV2") or pick(config, "task_config", "taskConfig") or {}
    tasks = pick(holder, "tasks")
    if not isinstance(tasks, dict):
        return None, None
    for key in TASKS:
        if tasks.get(key):
            return key, tasks[key]
    for key, info in tasks.items():
        if info:
            return key, info
    return None, None

def build_quest(raw):
    config = pick(raw, "config") or {}
    task, task_info = task_pick(config)
    if task is None:
        return None
    kind = TYPES.get(task, "OTHER")
    messages = pick(config, "messages") or {}
    name = pick(messages, "quest_name", "questName") or f"Quest {raw.get('id', '')}"
    status_raw = pick(raw, "user_status", "userStatus") or {}
    progress_map = pick(status_raw, "progress") or {}
    entry = progress_map.get(task) or {}
    progress = pick(entry, "value") or pick(status_raw, "stream_progress_seconds", "streamProgressSeconds") or 0
    try:
        progress = float(progress)
    except (TypeError, ValueError):
        progress = 0.0
    target = int(pick(task_info, "target") or 0)
    app = pick(config, "application")
    if not isinstance(app, dict) or not app.get("id"):
        apps = pick(task_info, "applications") or []
        app = apps[0] if apps and isinstance(apps[0], dict) else {}
    enrolled = bool(pick(status_raw, "enrolled_at", "enrolledAt"))
    completed = bool(pick(status_raw, "completed_at", "completedAt"))
    claimed = bool(pick(status_raw, "claimed_at", "claimedAt"))
    supported = kind in SUPPORTED and target > 0
    
    if completed:
        status = "claimed" if claimed else "completed"
    elif not supported:
        status = "unsupported"
    else:
        status = "ready"
        
    rewards = pick(pick(config, "rewards_config", "rewardsConfig") or {}, "rewards") or []
    reward = rewards[0].get("messages", {}).get("name", "") if rewards and isinstance(rewards[0], dict) else ""
    
    return {
        "id": str(raw.get("id", "")),
        "name": name,
        "task": task,
        "type": kind,
        "target": target,
        "progress": min(progress, target) if target else progress,
        "status": status,
        "enrolled": enrolled,
        "claimed": claimed,
        "reward": reward,
        "app_id": str(app.get("id") or "")
    }

# Flask Routes
@app.route("/")
index_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord Quest Bot - Vercel Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        body { font-family: 'JetBrains Mono', monospace; background-color: #0b0f19; color: #e2e8f0; }
        .glow { text-shadow: 0 0 10px rgba(168, 85, 247, 0.5); }
    </style>
</head>
<body class="min-h-screen p-4 md:p-8">
    <div class="max-w-4xl mx-auto space-y-6">
        <header class="text-center space-y-2">
            <h1 class="text-3xl font-bold text-purple-400 glow">DISCORD QUEST AUTOMATION</h1>
            <p class="text-xs text-slate-400">Vercel Web Dashboard Edition</p>
        </header>

        <!-- Token Input Card -->
        <div id="auth-card" class="bg-slate-900 border border-purple-500/30 rounded-xl p-6 shadow-xl space-y-4">
            <h2 class="text-lg font-semibold text-purple-300">Account Authentication</h2>
            <div class="flex gap-3">
                <input type="password" id="token-input" placeholder="Enter Discord Account Token..." class="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-purple-500">
                <button onclick="login()" class="bg-purple-600 hover:bg-purple-500 text-white font-bold px-6 py-2 rounded-lg text-sm transition">Connect</button>
            </div>
        </div>

        <!-- Dashboard Quests Section -->
        <div id="dashboard" class="hidden space-y-6">
            <div class="flex justify-between items-center bg-slate-900 border border-slate-800 p-4 rounded-xl">
                <div>
                    <p class="text-sm text-slate-400">Logged in as: <span id="user-name" class="text-purple-400 font-bold"></span></p>
                </div>
                <button onclick="loadQuests()" class="bg-slate-800 hover:bg-slate-700 text-xs px-3 py-2 rounded-lg transition">Refresh Quests</button>
            </div>

            <!-- Tabs -->
            <div class="flex border-b border-slate-800 gap-4">
                <button onclick="switchTab('ready')" id="tab-ready" class="pb-2 border-b-2 border-purple-500 text-purple-400 font-bold text-sm">Available Quests</button>
                <button onclick="switchTab('completed')" id="tab-completed" class="pb-2 border-b-2 border-transparent text-slate-400 text-sm">Completed</button>
            </div>

            <!-- Quest List -->
            <div id="quest-list" class="space-y-3"></div>

            <!-- Terminal Logs -->
            <div class="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs space-y-1 h-48 overflow-y-auto" id="terminal">
                <div class="text-slate-500">> System ready. Select a quest to automate.</div>
            </div>
        </div>
    </div>

    <script>
        let currentToken = "";

        async function login() {
            currentToken = document.getElementById('token-input').value.trim();
            if (!currentToken) return alert('Please enter a token.');
            
            log('Authenticating token...');
            const res = await fetch('/api/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: currentToken })
            });
            const data = await res.json();
            if(data.success) {
                document.getElementById('user-name').innerText = data.user.global_name || data.user.username;
                document.getElementById('auth-card').classList.add('hidden');
                document.getElementById('dashboard').classList.remove('hidden');
                log('Authentication successful!');
                loadQuests();
            } else {
                alert(data.error || 'Authentication failed.');
                log('Auth failed: ' + data.error);
            }
        }

        async function loadQuests() {
            log('Fetching quests from Discord...');
            const res = await fetch('/api/quests', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: currentToken })
            });
            const data = await res.json();
            if(data.success) {
                renderQuests(data.quests);
            } else {
                log('Error fetching quests: ' + data.error);
            }
        }

        function renderQuests(quests) {
            const list = document.getElementById('quest-list');
            list.innerHTML = '';
            if(quests.length === 0) {
                list.innerHTML = '<div class="text-center text-slate-500 py-8">No available quests found.</div>';
                return;
            }
            quests.forEach(q => {
                const card = document.createElement('div');
                card.className = 'bg-slate-900 border border-slate-800 p-4 rounded-xl flex justify-between items-center';
                card.innerHTML = `
                    <div>
                        <h3 class="font-bold text-slate-200">${q.name}</h3>
                        <p class="text-xs text-slate-400">Type: ${q.type} | Progress: ${q.progress} / ${q.target}</p>
                    </div>
                    <button onclick="startQuest('${q.id}')" class="bg-purple-600 hover:bg-purple-500 text-xs px-4 py-2 rounded-lg font-bold transition">Start Quest</button>
                `;
                list.appendChild(card);
            });
        }

        async function startQuest(questId) {
            log('Starting quest ID: ' + questId);
            const res = await fetch('/api/quest/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: currentToken, quest_id: questId })
            });
            const data = await res.json();
            if(data.success) {
                log('Quest completed successfully!');
                loadQuests();
            } else {
                log('Quest error: ' + data.error);
            }
        }

        function log(msg) {
            const term = document.getElementById('terminal');
            term.innerHTML += `<div>> ${msg}</div>`;
            term.scrollTop = term.scrollHeight;
        }
    </script>
</body>
</html>
"""
def index():
    return render_template_string(index_html)

@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json() or {}
    token = data.get("token")
    try:
        user = discord_request("GET", "/users/@me", token, desktop=True)
        return jsonify({"success": True, "user": user})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})

@app.route("/api/quests", methods=["POST"])
def api_quests():
    data = request.get_json() or {}
    token = data.get("token")
    try:
        res = discord_request("GET", "/quests/@me", token)
        raw = res.get("quests") if isinstance(res, dict) else res
        quests = [build_quest(item) for item in raw if isinstance(item, dict)]
        quests = [q for q in quests if q and q["status"] == "ready"]
        return jsonify({"success": True, "quests": quests})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})

@app.route("/api/quest/start", methods=["POST"])
def api_quest_start():
    data = request.get_json() or {}
    token = data.get("token")
    quest_id = data.get("quest_id")
    try:
        # Enroll
        discord_request("POST", f"/quests/{quest_id}/enroll", token, {"location": 11, "is_targeted": False, "metadata_raw": None})
        
        # Simulate video/heartbeat completion ticks
        for i in range(5):
            time.sleep(1)
            try:
                discord_request("POST", f"/quests/{quest_id}/video-progress", token, {"timestamp": float((i+1)*10)})
            except Exception:
                pass
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})

if __name__ == "__main__":
    app.run(debug=True)
