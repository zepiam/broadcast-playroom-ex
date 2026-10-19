import os
import base64

# Try to find the image at the user's path, or fallback to assets/
user_img_path = r"C:\Users\Meng-PC\Desktop\Tachie\test_harmonized.png"
if not os.path.exists(user_img_path):
    user_img_path = os.path.abspath("assets/dock_offline_character.png")

with open(user_img_path, "rb") as f:
    b64_img = base64.b64encode(f.read()).decode("utf-8")

def get_html(is_launcher=False):
    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-select=no">
<title>Broadcast Playroom - Waiting for Program</title>
<style>
  :root {{
    --bg-main: #080d1a;
    --bg-card: #0f172a;
    --border-color: #1e293b;
    --primary-blue: #38bdf8;
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
    --font: -apple-system, BlinkMacSystemFont, "Kanit", "Segoe UI", Roboto, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 100%;
    height: 100%;
    overflow: hidden;
    background-color: var(--bg-main);
    color: var(--text-main);
    font-family: var(--font);
    display: flex;
    align-items: center;
    justify-content: center;
    user-select: none;
  }}
  .offline-card {{
    contain: layout style;
    isolation: isolate;
    width: 90%;
    max-width: 380px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 26px 20px 22px 20px;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.6);
  }}
  .character-wrapper {{
    position: relative;
    width: 130px;
    height: 155px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: radial-gradient(circle, rgba(56, 189, 248, 0.12) 0%, rgba(15, 23, 42, 0) 70%);
  }}
  .character-img {{
    max-width: 120px;
    max-height: 145px;
    object-fit: contain;
    image-rendering: pixelated;
    image-rendering: crisp-edges;
  }}
  .status-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.35);
    color: #fca5a5;
    padding: 3px 12px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 700;
  }}
  .status-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: #ef4444;
  }}
  .title {{
    font-size: 16.5px;
    font-weight: 800;
    color: #f8fafc;
    line-height: 1.35;
    letter-spacing: 0.2px;
  }}
  .description {{
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.55;
    padding: 0 8px;
  }}
  .link-retry {{
    color: var(--primary-blue);
    text-decoration: underline;
    font-weight: 700;
    cursor: pointer;
    transition: color 0.15s ease;
  }}
  .link-retry:hover {{
    color: #7dd3fc;
  }}
  .btn-retry {{
    margin-top: 4px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 13.5px;
    font-weight: 700;
    font-family: inherit;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(2, 132, 199, 0.3);
    transition: transform 0.1s ease, background 0.15s ease, box-shadow 0.15s ease;
  }}
  .btn-retry:hover {{
    background: linear-gradient(135deg, #0369a1 0%, #075985 100%);
    box-shadow: 0 6px 18px rgba(2, 132, 199, 0.4);
  }}
  .btn-retry:active {{
    transform: scale(0.98);
  }}
  .auto-poll-hint {{
    font-size: 11px;
    color: #64748b;
    display: flex;
    align-items: center;
    gap: 5px;
  }}
  .spinner {{
    width: 12px;
    height: 12px;
    border: 2px solid rgba(100, 116, 139, 0.3);
    border-top-color: #38bdf8;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }}
  @keyframes spin {{
    to {{ transform: rotate(360deg); }}
  }}
</style>
</head>
<body>
  <div class="offline-card">
    <div class="character-wrapper">
      <img class="character-img" src="data:image/png;base64,{b64_img}" alt="Broadcast Playroom Chibi" />
    </div>

    <div class="status-badge" id="statusBadge">
      <span class="status-dot" id="statusDot"></span>
      <span id="badgeText">ยังไม่เปิดโปรแกรม</span>
    </div>

    <div class="title">Broadcast Playroom<br>ยังไม่ถูกเปิดขึ้น</div>

    <div class="description">
      กรุณาเปิดโปรแกรม แล้วคลิก <span class="link-retry" onclick="retryConnection()">ที่นี่</span> เพื่อโหลดหน้าใหม่
    </div>

    <button class="btn-retry" onclick="retryConnection()">
      <span>🔄</span> โหลดหน้าใหม่ (Reload)
    </button>

    <div class="auto-poll-hint">
      <div class="spinner"></div>
      <span>กำลังตรวจหาโปรแกรมอัตโนมัติ...</span>
    </div>
  </div>

  <script>
    let isReconnecting = false;
    const DOCK_URL = 'http://localhost:8801/dock';
    const API_URL = 'http://localhost:8801/api/dock/status';

    async function checkServer() {{
      if (isReconnecting) return;
      try {{
        const res = await fetch(API_URL, {{
          method: 'GET',
          cache: 'no-store',
          headers: {{ 'Accept': 'application/json' }}
        }});
        if (res.ok) {{
          isReconnecting = true;
          document.getElementById('badgeText').textContent = 'พบโปรแกรมแล้ว! กำลังเชื่อมต่อ...';
          document.getElementById('statusDot').style.backgroundColor = '#10b981';
          const badge = document.getElementById('statusBadge');
          badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
          badge.style.color = '#34d399';
          badge.style.background = 'rgba(16, 185, 129, 0.15)';
          setTimeout(() => {{
            if (window.location.protocol === 'file:') {{
              window.location.href = DOCK_URL;
            }} else {{
              window.location.href = '/dock';
            }}
          }}, 350);
        }}
      }} catch (e) {{
        // Server still offline, continue polling
      }}
    }}

    function retryConnection() {{
      if (window.location.protocol === 'file:') {{
        window.location.href = DOCK_URL;
      }} else {{
        window.location.href = '/dock';
      }}
    }}

    // Poll every 1.5 seconds
    setInterval(checkServer, 1500);
    checkServer();
  </script>
</body>
</html>
"""

# Write dock-offline.html
with open("dock-offline.html", "w", encoding="utf-8") as f:
    f.write(get_html(is_launcher=False))

# Write dock_launcher.html
with open("dock_launcher.html", "w", encoding="utf-8") as f:
    f.write(get_html(is_launcher=True))

print("Created dock-offline.html and dock_launcher.html successfully!")
