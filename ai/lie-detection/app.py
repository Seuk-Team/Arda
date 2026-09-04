import os, pickle, tempfile, warnings
warnings.filterwarnings("ignore")
import numpy as np
from flask import Flask, request, jsonify, render_template_string

from feature_extractor import extract_features, analyze_timeseries

app = Flask(__name__)
model = pickle.load(open("model.pkl", "rb"))

HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>거짓말 탐지기</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', sans-serif; background: #0d0d12; color: #e0e0e0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 32px 16px; }
h1 { font-size: 1.6rem; font-weight: 700; color: #fff; margin-bottom: 4px; }
.sub { color: #555; font-size: 0.85rem; margin-bottom: 28px; }

.main { display: flex; gap: 24px; width: 100%; max-width: 960px; align-items: flex-start; }

/* 왼쪽: 업로드 + 영상 */
.left { flex: 1; display: flex; flex-direction: column; gap: 16px; }

.upload-area {
  border: 2px dashed #2a2a3a;
  border-radius: 12px;
  padding: 28px;
  text-align: center;
  cursor: pointer;
  transition: border-color .2s, background .2s;
}
.upload-area:hover { border-color: #4a4aff; background: #14141e; }
.upload-area input { display: none; }
.upload-area p { color: #555; font-size: 0.88rem; margin-top: 10px; }
.upload-area p span { color: #6666ff; }
.upload-area small { color: #333; }

#video-wrap { display: none; border-radius: 12px; overflow: hidden; background: #000; }
#preview { width: 100%; max-height: 360px; display: block; }

/* 오른쪽: 결과 */
.right { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; gap: 16px; max-height: 90vh; overflow-y: auto; }

#analyze-btn {
  width: 100%; padding: 14px;
  background: #3a3aff; color: #fff;
  border: none; border-radius: 10px;
  font-size: 1rem; cursor: pointer;
  transition: background .2s;
}
#analyze-btn:hover { background: #5555ff; }
#analyze-btn:disabled { background: #222; color: #444; cursor: not-allowed; }

#loading { display: none; text-align: center; color: #555; font-size: 0.88rem; padding: 12px; }
.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #333; border-top-color: #6666ff; border-radius: 50%; animation: spin .8s linear infinite; vertical-align: middle; margin-right: 6px; }
@keyframes spin { to { transform: rotate(360deg); } }

#result { display: none; background: #1a1a24; border-radius: 12px; padding: 24px; }

.verdict {
  font-size: 1.6rem; font-weight: 700;
  text-align: center; padding: 20px 12px;
  border-radius: 10px; margin-bottom: 20px;
}
.verdict.lie   { background: #1e0606; color: #ff5555; border: 1px solid #4a1010; }
.verdict.truth { background: #061e06; color: #44dd44; border: 1px solid #104a10; }

.row { margin-bottom: 14px; }
.row-label { display: flex; justify-content: space-between; font-size: 0.8rem; color: #888; margin-bottom: 6px; }
.row-label strong { font-size: 0.95rem; }
.bar-bg { background: #111; border-radius: 6px; height: 12px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 6px; transition: width .7s ease; }
.bar-lie   { background: linear-gradient(90deg, #aa2222, #ff4444); }
.bar-truth { background: linear-gradient(90deg, #228822, #44cc44); }

#file-label { font-size: 0.78rem; color: #444; text-align: center; min-height: 16px; }
</style>
</head>
<body>

<h1>거짓말 탐지기</h1>
<p class="sub">영상을 올리고 분석을 시작하세요</p>

<div class="main">
  <!-- 왼쪽 -->
  <div class="left">
    <label class="upload-area" for="file-input">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#444" stroke-width="1.5">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
      </svg>
      <p>드래그하거나 <span>클릭해서 선택</span></p>
      <small>mp4 · avi · mov · mkv</small>
      <input type="file" id="file-input" accept="video/*">
    </label>
    <div id="file-label"></div>

    <div id="video-wrap">
      <video id="preview" controls></video>
    </div>
  </div>

  <!-- 오른쪽 -->
  <div class="right">
    <button id="analyze-btn" disabled>분석 시작</button>
    <div id="loading"><span class="spinner"></span>분석 중... (30초~1분)</div>

    <div id="result">
      <div class="verdict" id="verdict-box"></div>

      <div class="row">
        <div class="row-label"><span>거짓 확률</span><strong id="lie-pct">-</strong></div>
        <div class="bar-bg"><div class="bar-fill bar-lie" id="lie-bar" style="width:0%"></div></div>
      </div>
      <div class="row">
        <div class="row-label"><span>진실 확률</span><strong id="truth-pct">-</strong></div>
        <div class="bar-bg"><div class="bar-fill bar-truth" id="truth-bar" style="width:0%"></div></div>
      </div>

      <div id="obs-section" style="margin-top:20px;">
        <div style="font-size:0.78rem;color:#555;margin-bottom:10px;letter-spacing:.05em;">구간별 분석</div>
        <div id="obs-list"></div>
      </div>
    </div>
  </div>
</div>

<script>
const fileInput = document.getElementById('file-input');
const btn       = document.getElementById('analyze-btn');
const preview   = document.getElementById('preview');
const videoWrap = document.getElementById('video-wrap');
const fileLabel = document.getElementById('file-label');
let selectedFile = null;

fileInput.addEventListener('change', () => {
  const f = fileInput.files[0];
  if (!f) return;
  selectedFile = f;
  fileLabel.textContent = f.name;
  preview.src = URL.createObjectURL(f);
  videoWrap.style.display = 'block';
  btn.disabled = false;
  document.getElementById('result').style.display = 'none';
});

// 드래그앤드롭
const uploadArea = document.querySelector('.upload-area');
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.style.borderColor = '#4a4aff'; });
uploadArea.addEventListener('dragleave', () => { uploadArea.style.borderColor = ''; });
uploadArea.addEventListener('drop', e => {
  e.preventDefault(); uploadArea.style.borderColor = '';
  const f = e.dataTransfer.files[0];
  if (f) { fileInput.files; selectedFile = f; fileLabel.textContent = f.name; preview.src = URL.createObjectURL(f); videoWrap.style.display = 'block'; btn.disabled = false; }
});

btn.addEventListener('click', async () => {
  if (!selectedFile) return;
  btn.disabled = true;
  document.getElementById('loading').style.display = 'block';
  document.getElementById('result').style.display = 'none';

  const fd = new FormData();
  fd.append('video', selectedFile);

  try {
    const res  = await fetch('/analyze', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { alert('오류: ' + data.error); return; }

    const box = document.getElementById('verdict-box');
    box.textContent = data.pred === 1 ? '❌  거짓말 가능성' : '✅  진실 가능성';
    box.className   = 'verdict ' + (data.pred === 1 ? 'lie' : 'truth');

    document.getElementById('lie-bar').style.width    = data.lie_pct   + '%';
    document.getElementById('truth-bar').style.width  = data.truth_pct + '%';
    document.getElementById('lie-pct').textContent    = data.lie_pct   + '%';
    document.getElementById('truth-pct').textContent  = data.truth_pct + '%';

    // 구간별 관찰
    const obsList = document.getElementById('obs-list');
    obsList.innerHTML = '';
    const flagColor = { high: '#ff6666', low: '#ffaa44', normal: '#555' };
    const grouped = {};
    (data.observations || []).forEach(o => {
      if (!grouped[o.time]) grouped[o.time] = [];
      grouped[o.time].push(o);
    });
    Object.entries(grouped).forEach(([time, items]) => {
      const block = document.createElement('div');
      block.style = 'margin-bottom:12px;';
      block.innerHTML = `<div style="font-size:0.75rem;color:#666;margin-bottom:4px;">${time}</div>`;
      items.forEach(item => {
        const row = document.createElement('div');
        row.style = `display:flex;justify-content:space-between;font-size:0.8rem;padding:4px 8px;border-radius:6px;margin-bottom:2px;background:#12121a;`;
        row.innerHTML = `<span style="color:#aaa">${item.key}</span><span style="color:${flagColor[item.flag]||'#888'}">${item.value}</span>`;
        block.appendChild(row);
      });
      obsList.appendChild(block);
    });

    document.getElementById('result').style.display = 'block';
  } catch(e) { alert('서버 오류'); }
  finally {
    document.getElementById('loading').style.display = 'none';
    btn.disabled = false;
  }
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/analyze", methods=["POST"])
def analyze():
    f = request.files.get("video")
    if not f:
        return jsonify({"error": "파일 없음"})

    suffix = os.path.splitext(f.filename)[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.save(tmp.name)
    tmp.close()

    try:
        feat          = extract_features(tmp.name)
        observations  = analyze_timeseries(tmp.name)
    finally:
        os.remove(tmp.name)

    if feat is None:
        return jsonify({"error": "얼굴 또는 음성을 감지하지 못했습니다."})

    feat2d = feat.reshape(1, -1)
    pred   = int(model.predict(feat2d)[0])
    proba  = model.predict_proba(feat2d)[0]

    return jsonify({
        "pred":         pred,
        "truth_pct":    round(float(proba[0]) * 100, 1),
        "lie_pct":      round(float(proba[1]) * 100, 1),
        "observations": observations,
    })


if __name__ == "__main__":
    app.run(debug=True, use_reloader=True, port=5000)
