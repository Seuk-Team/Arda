"""학습한 표정 모델을 HuggingFace 에 올린다.

**왜 저장소에 안 두고 여기로 올리나**: 모델이 328MB 라 git 에 넣을 것이 아니다.
HuggingFace 에 두면 워커는 `VIT_MODEL=<계정>/arda-expression-vit` 한 줄로 받아 쓴다
(`ai/lie-detection/feature_extractor.py`).

**토큰을 코드·환경변수에 적지 않는다.** 먼저 한 번 로그인해 두면 그 자격이 쓰인다:

    hf auth login          # 또는 huggingface-cli login

그 다음:

    python push_to_hub.py <계정>/arda-expression-vit
    python push_to_hub.py <계정>/arda-expression-vit --private
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

HERE = Path(__file__).parent


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo", help="예: cloverky/arda-expression-vit")
    p.add_argument("--run", default="", help="비우면 가장 최근 회차")
    p.add_argument("--private", action="store_true")
    args = p.parse_args()

    from huggingface_hub import HfApi

    from train import latest_run

    run = Path(args.run) if args.run else latest_run()
    if run is None or not (run / "best").exists():
        raise SystemExit(f"모델이 없다: {run}\n먼저 `python train.py` 를 돌린다.")

    best = run / "best"
    # 받아 쓰는 쪽이 학습 때와 같게 전처리해야 한다. 이게 빠지면 정확도가
    # 조용히 떨어진다 — 에러가 아니라 값이 달라질 뿐이라 눈치채기 어렵다.
    if not (best / "preprocessor_config.json").exists():
        raise SystemExit(f"preprocessor_config.json 이 없다: {best}")

    # 모델 카드는 저장소에 사람이 고쳐 두는 것이라 그대로 실어 보낸다
    card = HERE / "MODEL_CARD.md"
    shutil.copy(card, best / "README.md")

    api = HfApi()
    api.create_repo(args.repo, repo_type="model", private=args.private, exist_ok=True)
    api.upload_folder(folder_path=str(best), repo_id=args.repo, repo_type="model")
    (best / "README.md").unlink()

    print(f"올렸다: https://huggingface.co/{args.repo}")
    print(f"워커 설정: VIT_MODEL={args.repo}")


if __name__ == "__main__":
    main()
