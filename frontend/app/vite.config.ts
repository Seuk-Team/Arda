import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  /* 개발 중 API 를 어디로 보낼지. 로컬 백엔드를 띄웠으면
     .env.local 에 VITE_DEV_API_TARGET=http://localhost:8000 을 넣는다. */
  const target = env.VITE_DEV_API_TARGET || 'https://api.arda.seuk.cloud'

  return {
    plugins: [react()],
    server: {
      /* 브라우저에서 보면 같은 출처(localhost:5173)로 나가므로 CORS 가 아예 안 걸린다.
         배포 API 에 CORS 미들웨어가 없어서(백엔드 이슈) 직접 호출은 preflight 에서 막힌다. */
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
