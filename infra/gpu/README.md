# GPU 전환 — 거짓말 탐지(ai/lie-detection) 를 CPU ↔ GPU 로

2026-10-14. 손잡이는 `infra/compute.sh` 하나다. 운영 서버 `~/arda` 에서 친다.

| 하려는 것 | 명령 (운영 서버) |
|---|---|
| GPU 로 켜기 | `bash infra/compute.sh gpu <GPU 사설IP> --ssh ubuntu@<GPU 사설IP>` (두 번째부터는 `bash infra/compute.sh gpu`) |
| CPU 로 되돌리기 | `bash infra/compute.sh cpu` → **그 다음에** GPU 인스턴스 정지 |
| 지금 어디로 가나 | `bash infra/compute.sh status` |

같은 명령을 두 번 쳐도 안전하다. 바뀐 것이 없으면 아무것도 재시작하지 않는다.

> ⚠️ **끌 때는 반드시 `compute.sh cpu` 를 먼저 친다.** Caddy 를 되돌리지 않고 GPU 인스턴스를 끄면
> 진행 중인 면접 소켓은 그 자리에서 끊긴다. 새 연결은 Caddy 헬스 체크가 약 10초 안에 이 서버 CPU 로
> 돌리지만, 그 10초 동안 들어온 연결은 실패한다. 그 안전판은 사고를 줄이는 장치일 뿐이고, 순서를
> 지키는 것이 규칙이다.

## 구조

운영 서버(t3.large)에는 GPU 가 없다. 그래서 GPU 모드는 **다른 기계에서 GPU 판을 돌리고, 운영 Caddy 가
`/ai/*` 를 그 기계로 넘기는 것**이다.

| | 운영 서버 (t3.large) | GPU 호스트 (기본: g4dn.xlarge, 켜고 끄기) |
|---|---|---|
| lie-detection | **늘 CPU 판**(`Dockerfile`)이 떠 있다 | GPU 판(`Dockerfile.gpu`) |
| compose | `docker-compose.prod.yml` | `docker-compose.gpu-host.yml` + `docker-compose.gpu.yml` |
| `/ai/*` (cpu 모드) | → 이 서버 `lie-detection:5000` | 안 씀 |
| `/ai/*` (gpu 모드) | → GPU 호스트, 응답이 없으면 → 이 서버 CPU | 받는다 |

- **모드 기록**: 운영 서버 `~/arda/.compute`(git 밖). 기록이 없으면 cpu다. `compute.sh` 만 이 파일을 쓴다.
- **Caddy**: `Caddyfile` 맨 위의 스니펫 두 개(`lie_local` · `lie_remote`) 중 하나를 환경변수 `LIE_PROXY` 로
  고른다. cpu 모드 설정은 이 작업 전과 JSON 이 한 글자도 다르지 않다(`caddy adapt` 비교).
- **GPU 판에서 바뀌는 것**(`docker-compose.gpu.yml`): `STT_DEVICE=cuda` · `STT_COMPUTE_TYPE=float16` ·
  `VIT_DEVICE=cuda` · `DECEPTION_DEVICE=cuda`, 그리고 **전사를 그 GPU 에서 한다**
  (`STT_BACKEND=faster_whisper`, `STT_MODEL=large-v3-turbo`). backend/.env 가 OpenAI API 전사여도 GPU
  모드에서는 로컬 whisper 다. 그러려고 켜는 GPU 이기 때문이다.
- 코드의 장치 기본값은 전부 `cpu` 이고 `auto` 는 없다. `cuda` 는 이 오버레이에서만 들어간다.

## 배포(main 머지)와의 관계

`deploy-arda.sh` 는 배포할 때마다 `compute.sh on-deploy` 를 부른 뒤 `compute.sh env` 로 기록된 모드를
Caddy 에 다시 넣는다.

- **GPU 모드는 배포 뒤에도 유지된다.** 이 단계가 없으면 compose 기본값(local)으로 caddy 가 다시 만들어져
  CPU 로 돌아간다.
- `ai/lie-detection/` 이 바뀐 배포:
  - `--ssh` 가 있으면 GPU 호스트도 main 으로 올려 다시 띄운다.
  - `--ssh` 가 없으면 옛 코드가 도는 GPU 로 두지 않고 **cpu 로 돌린다**(배포 로그 WARN).
- GPU 호스트가 응답하지 않으면 **cpu 로 돌린다**(배포 로그 WARN). 꺼진 GPU 를 가리킨 채 두지 않는다.
- GPU 판 이미지(13GB)는 운영 서버에서 빌드되지 않는다. `deploy-arda.sh` 는 `Dockerfile.gpu` 를 모른다.

## GPU 호스트 준비 (처음 한 번)

**① 인스턴스.** g4dn.xlarge(T4 16GB, 서울 $0.647/h)를 Ubuntu 22.04 또는 24.04 로 띄운다. 운영 서버와
같은 VPC 에 둔다.
- EBS: 50GB 이상. GPU 이미지 13GB, 모델 캐시 약 3GB, 빌드 캐시가 들어간다.
- 보안 그룹:
  - 5000/tcp 는 **운영 서버의 보안 그룹(또는 사설 IP)에서만** 연다. 인터넷에 열지 않는다.
  - 22/tcp 는 운영 서버와 관리자 IP 에만 연다.
- 사설 IP 는 인스턴스를 stop/start 해도 그대로다. 그래서 한 번 정하면 `compute.sh gpu` 만 쳐도 된다.

**② NVIDIA 드라이버 + Docker + nvidia-container-toolkit.** `ai/serve/setup-g4dn.sh` 의 1~3 단계와 같다
(4단계 Ollama 는 필요 없다).

```bash
sudo apt-get update && sudo apt-get install -y ubuntu-drivers-common && sudo ubuntu-drivers autoinstall && sudo reboot
```

```bash
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker "$USER"
```

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
```

```bash
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

```bash
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
```

확인한다. GPU 이름이 나와야 한다.

```bash
docker run --rm --gpus all ubuntu nvidia-smi -L
```

**③ 저장소와 설정 (GPU 호스트).**

```bash
git clone https://github.com/Seuk-Team/Arda.git ~/arda
```

운영 서버의 `~/arda/backend/.env` 를 GPU 호스트 `~/arda/backend/.env` 로 그대로 복사한다.
`ARDA_SERVICE_TOKEN` 이 같아야 판정을 백엔드로 밀 수 있고, 셀프 테스트도 열린다. 복사는 운영 서버에서
한다(⑤의 키가 있어야 한다).

```bash
scp ~/arda/backend/.env ubuntu@<GPU 사설IP>:arda/backend/.env
```

GPU 판은 판정·답변을 공개 주소 `https://api.seuk.suvisdev.cloud` 로 민다(`docker-compose.gpu-host.yml` 의
`ARDA_BACKEND_URL`). 내부 API 는 서비스 토큰으로 막혀 있다.

**④ GPU 판을 띄운다 (GPU 호스트).** 처음에는 빌드(약 10분)와 모델 내려받기(약 2GB)로 오래 걸린다.
`restart: unless-stopped` 라서 다음부터는 인스턴스를 켜면 저절로 뜬다.

```bash
cd ~/arda && bash infra/compute.sh serve
```

**⑤ (권장) 운영 서버 → GPU 호스트 ssh.** 이게 있으면 `compute.sh gpu --ssh` 가 GPU 호스트를 main 으로
올려 다시 띄운다. 배포 때도 따라 올린다. 키는 **배포 타이머가 도는 계정**(`arda-deploy.service` 의
User)에 만든다.

```bash
ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
```

`~/.ssh/id_ed25519.pub` 한 줄을 GPU 호스트의 `~/.ssh/authorized_keys` 에 붙인다.

**⑥ 운영 서버의 배포 스크립트를 한 번 갱신한다.** 서버 `~/deploy-arda.sh` 는 저장소 사본과 따로 논다
(`deploy-arda.sh` 머리말). 옛 판은 배포 때 모드를 모른다. 그래서 갱신 전에는 `compute.sh gpu` 가
거절한다.

```bash
cp ~/deploy-arda.sh ~/deploy-arda.sh.bak-$(date +%m%d) && cp ~/arda/infra/deploy-arda.sh ~/deploy-arda.sh
```

## 켜기 (매번)

1. 인스턴스를 켠다(콘솔 또는 `aws ec2 start-instances --instance-ids <id>`). 컨테이너는 부팅과 함께 뜬다.
2. 운영 서버에서 한 줄 친다.

```bash
cd ~/arda && bash infra/compute.sh gpu
```

`compute.sh gpu` 가 하는 일은 아래와 같다. 하나라도 실패하면 **바꾸지 않는다**(지금 모드 그대로).

1. (`--ssh`) GPU 호스트를 main 으로 올리고 `serve` 한다.
2. GPU 호스트 `/health` 가 ok 인지, GPU 가 보이는지(`cuda_devices ≥ 1`), GPU 설정으로 떴는지 본다.
3. 모델 4종 셀프 테스트(`POST /selftest`, 서비스 토큰)를 돌린다. STT·ViT 가 **cuda 에서** 돌아야 한다.
4. 새 환경으로 Caddyfile 을 읽어 본다(`caddy adapt`).
5. 기록을 쓰고 caddy 를 다시 만든다. 이때 **사이트 전체가 2~3초 끊긴다.**
6. Caddy 를 거친 `/ai/health` 가 GPU 판에서 오는지 본다. 아니면 cpu 로 되돌리고 실패로 끝낸다.

면접이 진행 중일 때는 전환하지 않는다. 세션 방이 프로세스 안에 있어서, 진행 중인 소켓은 전환 순간 끊긴다.

## 끄기 (매번): 순서를 바꾸지 않는다

1. 운영 서버에서 `bash infra/compute.sh cpu` 를 친다. 이 서버 CPU 판이 헬스·셀프 테스트(cpu)를 통과하는지
   먼저 본다. CPU 가 응답하지 않으면 바꾸지 않고 멈춘다. 그때는 **GPU 를 끄지 않는다.**
2. 그 다음에 인스턴스를 정지한다. 켜 둔 채 잊으면 하루 $15.8 이다. AWS 크레딧은 2026-10-27 에 끝난다.

## 노트북을 GPU 호스트로 쓰려면

구조는 같다. 다만 운영 서버가 노트북의 5000번에 닿아야 한다. 운영 서버에도 Tailscale 을 깔고
`bash infra/compute.sh gpu <노트북 tailscale 주소>:5000` 으로 켠다. Windows 노트북이면 WSL2 Ubuntu
안의 docker(nvidia-container-toolkit)에서 `serve` 한다. 아래 실측이 그 환경이다. 노트북이 잠들면 Caddy 가
CPU 로 돌리고, 다음 배포 때 기록도 cpu 가 된다.

## 실측 (2026-10-14, 노트북 RTX 4060 · 운영 서버 흉내)

시험 구성은 이렇다.
- 운영 서버 역할: 리눅스 컨테이너에서 이 스크립트와 `docker-compose.prod.yml` 을 그대로 돌렸다.
  Caddyfile 은 사이트 주소만 `:8099`(TLS 없음)로 바꿨다.
- GPU 호스트 역할: Docker Desktop(nvidia 런타임)에서 `compute.sh serve`.

모델 1건 시간은 처음 받기·예열을 뺀 값이다. 입력은 음성 1초, 사진 1장.

| 모델 | CPU 판 | GPU 판 | 비고 |
|---|---|---|---|
| STT large-v3-turbo | 4.0초 (int8) | 0.26~0.53초 (float16) | |
| 표정 ViT | 120~170ms | 16~40ms | |
| 참/거짓 ViT | 122ms | 16ms | 아래 "이미 알려진 것"의 우회로 띄움. 두 판 결과값이 같다 |
| 참/거짓 Whisper | 971ms | 94ms | 같음 |

전환 동작은 다음과 같았다.
- `gpu`: 셀프 테스트(cuda) → caddy 재생성 → Caddy 경유 `/ai/health` 가 cuda. 다시 쳐도 caddy 는 재시작하지 않았다.
- `cpu`: 셀프 테스트(cpu) → caddy 재생성 → Caddy 경유 cpu. 약 16초 걸렸고, 다시 쳐도 caddy 는 재시작하지 않았다.
- GPU 모드에서 배포:
  - lie-detection 이 안 바뀌면 GPU 를 유지했다(caddy 재시작 없음).
  - lie-detection 이 바뀌었는데 `--ssh` 가 없으면 cpu 로 갔다.
  - GPU 가 꺼져 있으면 cpu 로 갔다.
- GPU 를 `cpu` 없이 꺼 보았다. 3.7~9.6초 사이에 요청 3건이 실패했고, 9.6초부터 Caddy 가 CPU 로 받았다.
- 거절해야 할 때 거절했다. 옛 `deploy-arda.sh`, 형식이 틀린 호스트, 응답 없는 호스트에서 모드가 그대로였다.

이미지는 이렇다.
- GPU 판: torch 2.14.1+cu126 · ctranslate2 4.8.3, 둘 다 GPU 를 본다. 13.3GB.
- CPU 판: 4.0GB, GPU 는 0개로 본다.

## 문제가 생기면

- 지금 상태: `bash infra/compute.sh status`. 기록 · Caddy 환경 · 양쪽 헬스 · `/ai/*` 가 실제로 가는 곳이 나온다.
- 이 서버 CPU 판 로그: `docker compose -p arda -f infra/docker-compose.prod.yml logs --tail 50 lie-detection`
- GPU 판 로그 (GPU 호스트): `docker compose -p arda-gpu logs --tail 50 lie-detection`
- 배포가 모드를 어떻게 처리했나: `grep compute ~/deploy.log | tail`

## 이미 알려진 것

- **참/거짓 두 모델은 CPU 에서도 GPU 에서도 안 올라온다**(2026-10-14 확인, 이 작업 전부터 그랬다).
  - ViT: HF `cloverky/arda-deception-vit` 에 `preprocessor_config.json` 이 없다.
  - Whisper: 이미지에 `openai-whisper` 패키지가 없다.
  - 둘 다 실패하면 건너뛰게 되어 있어서 면접은 그대로 돈다. 장치 스위치(`DECEPTION_DEVICE`)는 넣어 두었다.
  - 시험에서만 우회로 띄워(ViT 는 기반 모델 google/vit-base-patch16-224 의 전처리기,
    Whisper 는 일회용 컨테이너에 패키지 설치) cuda 에서 도는 것과 CPU 와 값이 같은 것을 확인했다.

## `results/`

이 폴더의 `results/*.json` 은 별개의 기록이다. Qwen 학습·벤치 결과 요약이고, `.gitignore` 는 그쪽 가중치
산출물을 막는다.
