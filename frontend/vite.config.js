import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 须写在通用 /api 之前：SSE 专用超时与去缓冲
      '/api/chat/stream': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // 强制设置，防止某些浏览器因为缺少这个头导致不触发 EventSource
            proxyRes.headers['content-type'] = 'text/event-stream'
            proxyRes.headers['cache-control'] = 'no-cache'
            proxyRes.headers['x-accel-buffering'] = 'no'
            // 加上 Connection: keep-alive 确保长连接不被轻易断开
            proxyRes.headers['connection'] = 'keep-alive'
          })
        },
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
