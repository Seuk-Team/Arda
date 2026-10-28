# Arda 노트북 온프레미스 (2026-10-28~)

AWS 는 2026-10-27 발표 뒤 종료했다. 그 뒤 Arda 는 **노트북에서** 돈다 — 노트북이 켜지면 저절로 뜨고, 꺼지면 같이 멈춘다.
프론트(seuk.suvisdev.cloud)는 Vercel 그대로, API 와 파일은 Cloudflare 터널로 노트북에 들어온다.

```
seuk.suvisdev.cloud        → Vercel (변경 없음)
api-seuk.suvisdev.cloud    → 터널 → caddy:8080 → api · /ai(거짓말 탐지) · /n8n
files-seuk.suvisdev.cloud  → 터널 → seaweedfs:8333 (S3 호환, presigned 업로드·다운로드)
```

## 켜기 · 끄기 (WSL, 저장소 루트에서)

```bash
docker compose -f infra/onprem/docker-compose.yml up -d     # 켜기 (1~2분 뒤 응답)
docker compose -f infra/onprem/docker-compose.yml stop      # 끄기 (데이터는 볼륨에 남는다)
docker compose -f infra/onprem/docker-compose.yml ps        # 상태
```

꺼져 있으면 api-seuk 가 530 이라 프론트는 뜨지만 로그인이 안 된다.
`restart: unless-stopped` 라 노트북을 켜면(로그온 작업이 WSL 을 올림) 저절로 뜬다. `stop` 으로 내려 두면 다음 부팅에도 꺼진 채 남는다.

## 거짓말 탐지 GPU · CPU

음성 인식(Whisper large-v3-turbo)·표정·참/거짓 모델을 노트북 GPU(RTX 4060)로 돌린다.

```bash
docker compose -f infra/onprem/docker-compose.yml -f infra/onprem/docker-compose.gpu.yml up -d lie-detection   # GPU
docker compose -f infra/onprem/docker-compose.yml up -d lie-detection                                           # CPU 로
```

관리자 페이지 버튼은 ops-agent(suvisdev `k8s/ops-agent`)가 이 명령을 대신 치고, 고른 모드를 기억해 다음 켜기에도 쓴다.
2026-10-28 실측: 5초 오디오 전사 0.62초(cuda, int8_float16), VRAM 약 1.3GB. CPU 일 때는 답변 하나에 30~100초.
메인 채팅 EXAONE 7.8B(약 5.7GB)와 같은 GPU 를 나눠 쓰므로 Whisper 는 int8_float16 으로 줄였다.

## 처음 한 번

```bash
bash infra/onprem/setup.sh /mnt/c/Users/<사용자>/Desktop/seuk/AWS_백업_20261026   # 시크릿·DB·n8n·파일
bash infra/onprem/tunnel.sh                                                     # 터널·DNS
docker compose -f infra/onprem/docker-compose.yml up -d --build
```

## 운영과 다른 점

| 항목 | 운영(EC2, ~10-27) | 노트북 |
|---|---|---|
| 파일 | S3 `arda-resumes-seuk` | SeaweedFS 같은 이름 버킷(MinIO 공식 이미지는 더 이상 받을 수 없다) |
| 입구 | 공인 IP + Caddy TLS | Cloudflare 터널, Caddy 는 http :8080 |
| 자동 기동 | systemd + `restart: unless-stopped` | 로그온 작업이 WSL 을 켜면 `restart: unless-stopped` 로 |
| 자동 배포·매일 백업·CloudWatch 알람 | 있음 | 없음. 코드가 바뀌면 `up -d --build` |
| AI | Claude API | 같음 — 호출마다 Anthropic 잔액이 줄어든다 |

## 주의

- 데이터는 운영 사본이다(지원자 실제 이메일). `MAIL_DISPATCH=n8n` 이라 단계를 바꾸면 **진짜 메일이 나간다.**
- 시크릿은 `infra/onprem/.env` · `.env.backend` · `s3.json`(커밋 안 함), 터널 자격은 `~/.cloudflared/arda-onprem/`.
- 노트북의 suvisdev k3s 와 같은 docker 를 쓰지만 포트를 하나도 열지 않아 겹치지 않는다.
