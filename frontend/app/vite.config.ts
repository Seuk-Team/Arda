import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  /* 개발 중 API 를 어디로 보낼지. 로컬 백엔드를 띄웠으면
     .env.local 에 VITE_DEV_API_TARGET=http://localhost:8000 을 넣는다. */
  const target = env.VITE_DEV_API_TARGET || 'https://api.seuk.suvisdev.cloud'

  /* WSL 에서 `/mnt/c` 의 파일을 볼 때는 **파일 변경 감지가 안 된다.**
     Windows 쪽 쓰기가 inotify 로 안 올라와서, 고친 파일이 화면에 영영
     반영되지 않고 서버를 켤 때의 코드가 계속 돈다 — 브라우저를 새로고침해도
     같다. 조용히 틀린 것을 오래 보게 되는 함정이라 스위치를 둔다.
     `.env.local` 에 `VITE_DEV_POLL=1`. CPU 를 쓰므로 기본은 꺼 둔다. */
  const poll = env.VITE_DEV_POLL === '1'

  return {
    plugins: [react()],
    server: {
      watch: poll ? { usePolling: true, interval: 300 } : undefined,
      /* 브라우저에서 보면 같은 출처(localhost:5173)로 나가므로 CORS 가 아예 안 걸린다.
         배포 API 에 CORS 미들웨어가 없어서(백엔드 이슈) 직접 호출은 preflight 에서 막힌다. */
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          /* 실시간 면접 시그널링이 WebSocket 이라 프록시가 업그레이드를 넘겨야 한다.
             없으면 로컬에서만 조용히 안 붙는다. */
          ws: true,
        },
      },
    },
  }
})
