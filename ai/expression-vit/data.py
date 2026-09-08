"""FER2013 — 얼굴 표정 사진 3만 5천 장.

각 사진에 표정 7종 중 하나가 붙어 있다. 이걸 ViT 에 반복해서 보여 주며
"이게 웃는 얼굴이다"를 가르치는 것이 학습이다.

받는 곳은 HuggingFace 미러(`Jeneral/fer-2013`, Apache-2.0)다. 원본은 Kaggle 인데
로그인이 필요해 자동으로 못 받는다. 파일은 pickle 두 개뿐이라 `datasets` 라이브러리
없이 그냥 읽는다 — 의존성 하나를 줄인다.

나중에 RAF-DB 로 갈아탈 때 고칠 곳은 이 파일 하나다. `train.py` 는 라벨 이름과
`(이미지, 정답)` 만 알면 된다.
"""

from __future__ import annotations

import pickle
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset

# 표정 7종. 순서가 곧 정답 번호라 **바꾸면 학습된 모델과 어긋난다.**
LABELS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
INDEX = {name: i for i, name in enumerate(LABELS)}

KOREAN = {
    "angry": "화남",
    "disgust": "역겨움",
    "fear": "무서움",
    "happy": "웃음",
    "neutral": "무표정",
    "sad": "슬픔",
    "surprise": "놀람",
}

_BASE = "https://huggingface.co/datasets/Jeneral/fer-2013/resolve/main/"
DATA_DIR = Path(__file__).parent / "data"


def download(split: str) -> Path:
    """`train` · `test` 파일을 받아 둔다. 이미 있으면 다시 받지 않는다."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{split}.pt"
    if path.exists():
        return path
    print(f"{split} 받는 중…")
    urllib.request.urlretrieve(_BASE + f"{split}.pt", path)
    print(f"  저장: {path} ({path.stat().st_size / 1e6:.1f}MB)")
    return path


class Fer2013(Dataset):
    """사진 한 장과 정답 하나를 돌려주는 목록.

    사진은 48×48 흑백이고 ViT 는 224×224 컬러를 받는다. 그 변환은 `transform`
    이 한다 — 학습용과 평가용이 서로 달라야 해서(학습만 뒤집기·자르기를 한다)
    여기서 고정하지 않는다.
    """

    def __init__(self, split: str, transform=None):
        with open(download(split), "rb") as f:
            self.rows = pickle.load(f)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i):
        row = self.rows[i]
        img = Image.open(BytesIO(row["img_bytes"])).convert("RGB")
        if self.transform:
            img = self.transform(img)
        # 파일에는 정답이 `"angry"` 같은 글자로 들어 있다. 모델은 번호를 받으므로
        # 여기서 바꾼다 — 번호를 정하는 곳이 `LABELS` 하나로 모인다.
        return img, INDEX[row["labels"]]

    def label_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(LABELS, 0)
        for row in self.rows:
            counts[row["labels"]] += 1
        return counts


if __name__ == "__main__":
    for split in ("train", "test"):
        ds = Fer2013(split)
        print(f"\n{split}: {len(ds):,}장")
        for name, n in ds.label_counts().items():
            print(f"  {KOREAN[name]:5s} {n:6,}장  {'█' * (n // 400)}")
