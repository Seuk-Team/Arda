---
license: apache-2.0
base_model: google/vit-base-patch16-224-in21k
tags:
  - image-classification
  - facial-expression-recognition
  - vit
datasets:
  - microsoft/FERPlus
metrics:
  - accuracy
  - recall
library_name: transformers
pipeline_tag: image-classification
---

# arda-expression-vit

얼굴 사진 한 장 → **표정 7종** 확률. `google/vit-base-patch16-224-in21k` 를
**FERPlus** 로 파인튜닝했습니다.

> A ViT-base fine-tuned on FERPlus for 7-class facial expression recognition.
> Korean-language model card below. **Not a lie detector** — see Limitations.

## ⚠️ 이 모델이 하지 않는 것

**표정으로 거짓말을 판정하지 않습니다.** 법정 영상 실측에서 거짓 진술 영상이
`happy` 55~64%, 진실 진술 영상이 `fear` 71% 로 나왔습니다 — 표정만으로는
갈리지 않습니다. 이 모델은 여러 신호 중 **하나**로만 쓰도록 만들었습니다.

사람을 평가하거나 걸러내는 자동 판정에 단독으로 쓰지 마세요.

## 성능 (FERPlus 테스트 7,048장)

**전체 정확도 74.91% · 표정 평균 재현율 77.90%**

| 표정 | 장수 | 재현율 | 정밀도 |
|---|---:|---:|---:|
| 웃음 `happy` | 1,827 | **91.1%** | 93.6% |
| 놀람 `surprise` | 900 | 83.0% | 85.3% |
| 화남 `angry` | 644 | 81.4% | 78.4% |
| 역겨움 `disgust` | 57 | 80.7% | **5.9%** ⚠️ |
| 무서움 `fear` | 167 | 76.0% | 41.1% |
| 슬픔 `sad` | 856 | 74.1% | 62.9% |
| 무표정 `neutral` | 2,597 | 59.2% | 94.6% |

### ⚠️ `disgust` 는 그대로 믿으면 안 됩니다

**정밀도 5.9%** — "역겨움" 이라고 답한 780장 중 46장만 실제 역겨움이고, 527장은
**무표정**입니다. 적은 표정을 살리려고 클래스 가중치를 크게 준 대가입니다.

`neutral` 도 재현율 59.2% 로 낮습니다. 같은 이유로, 무표정을 다른 표정으로
자주 넘깁니다. 반대로 **정밀도는 94.6%** 라 "무표정" 이라고 답하면 대개 맞습니다.

재현율과 정밀도를 같이 보세요. 어느 한쪽만 보면 정반대 결론이 납니다.

## 왜 FERPlus 인가

FER2013 은 3만 5천 장에 **한 사람이** 라벨을 붙였고 오답이 많습니다. FERPlus 는
**같은 사진**에 10명이 다시 투표한 정답지입니다.

```
FER2013 "무서움"  4,097장
FERPlus "무서움"    652장   ← 10명이 보니 84%는 무서움이 아니었다
```

사진은 한 장도 안 바꾸고 **정답지만** 바꿨을 때:

| 표정 | FER2013 라벨 | 클래스 가중치 | **FERPlus 라벨** |
|---|---:|---:|---:|
| 무서움 | 47% | 49% | **76%** |
| 화남 | 64% | 68% | **81%** |
| 슬픔 | 55% | 56% | **74%** |
| 역겨움 | 32% | 74% | **81%** |
| 무표정 | 74% | 74% | 59% ↓ |

모델을 더 손대기 전에 **정답지를 의심해 볼 값어치가 있었습니다.**

## 쓰는 법

```python
from transformers import ViTForImageClassification, ViTImageProcessor
from PIL import Image

model = ViTForImageClassification.from_pretrained("<계정>/arda-expression-vit")
proc = ViTImageProcessor.from_pretrained("<계정>/arda-expression-vit")

x = proc(Image.open("face.jpg").convert("RGB"), return_tensors="pt")
probs = model(**x).logits.softmax(-1)[0]
```

**얼굴만 잘라서 넣으세요.** 배경이 들어가면 값이 흐려집니다.

## 학습 설정

| | |
|---|---|
| 바탕 모델 | `google/vit-base-patch16-224-in21k` |
| 데이터 | FERPlus (FER2013 이미지 + 10인 투표 라벨), `unknown`·`NF`·`contempt` 제외 |
| 에폭 | 9 (표정 평균 재현율이 가장 높은 회차 선택) |
| 배치 · 학습률 | 32 · 3e-5 |
| 클래스 가중치 | 장수에 반비례 |
| 라벨 스무딩 | 0.1 |
| 증강 | RandomResizedCrop · HorizontalFlip · Affine · ColorJitter · RandomErasing |
| 전처리 | 224×224 · mean/std 0.5 |

**체크포인트는 정확도가 아니라 표정 평균 재현율로 골랐습니다.** 무표정이
테스트셋의 37% 라, 정확도로 고르면 무표정만 잘 맞히는 모델이 뽑힙니다.

## 데이터·개인정보

학습에 쓴 것은 **공개 데이터셋뿐**입니다. 지원자 얼굴이나 면접 영상은 한 장도
들어가지 않았습니다.

- FERPlus 라벨 — MIT (Microsoft)
- FER2013 이미지 — 원 출처의 조건을 따릅니다

## 만든 곳

[Arda](https://github.com/Seuk-Team/Arda) — 채용 보조 AI. 이 모델은 AI 면접
화면에서 표정 신호 하나를 만드는 데 씁니다.
