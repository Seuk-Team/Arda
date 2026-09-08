"""학습한 표정 모델을 브라우저에서 써 본다.

    python serve.py          →  http://localhost:5100

사진을 올리거나 카메라를 켜면 표정 7종의 확률이 막대로 나온다.
**혼자 확인하는 용도다** — 저장도, 로그인도, 바깥으로 나가는 것도 없다.
"""

from __future__ import annotations

import io
from pathlib import Path

import torch
from fastapi import FastAPI, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image
from transformers import ViTForImageClassification

from data import KOREAN, LABELS
from train import EVAL_TF

HERE = Path(__file__).parent
MODEL_DIR = HERE / "runs" / "best"

# 표정마다 실력이 다르다(평가 실측). 화면에 같이 띄워 "이 값을 얼마나 믿을지"를
# 보는 사람이 알게 한다 — 90% 짜리 웃음과 32% 짜리 역겨움이 같은 막대로 보이면 안 된다.
RECALL = {
    "happy": 90.1, "surprise": 82.1, "neutral": 73.5, "angry": 64.4,
    "sad": 55.3, "fear": 47.2, "disgust": 32.4,
}

if not MODEL_DIR.exists():
    raise SystemExit(f"학습된 모델이 없다: {MODEL_DIR}\n먼저 `python train.py`.")

device = "cuda" if torch.cuda.is_available() else "cpu"
model = ViTForImageClassification.from_pretrained(MODEL_DIR).to(device).eval()
print(f"모델 로딩 완료 ({device})")

app = FastAPI(title="표정 분류 (ViT)")


@app.post("/predict")
async def predict(image: UploadFile | None = None):
    if image is None:
        return JSONResponse({"error": "사진 없음"}, status_code=400)
    img = Image.open(io.BytesIO(await image.read())).convert("RGB")
    with torch.no_grad():
        probs = torch.softmax(model(EVAL_TF(img).unsqueeze(0).to(device)).logits, -1)[0]
    return {
        "results": sorted(
            (
                {
                    "label": KOREAN[name],
                    "pct": round(float(probs[i]) * 100, 1),
                    "recall": RECALL[name],
                }
                for i, name in enumerate(LABELS)
            ),
            key=lambda r: -r["pct"],
        )
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "demo.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5100, log_level="warning")
