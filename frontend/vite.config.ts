import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 服务器经 frp 暴露公网（allowedHosts），公网客户端/扫描器会向 HMR WebSocket
// 发送非法帧，Vite 对此类帧抛未捕获异常直接击穿进程（WS_ERR_INVALID_CLOSE_CODE）。
// 进程级兜底：记录并继续，不让一条脏帧杀掉开发服务器。
process.on("uncaughtException", (err) => {
  console.error("[vite] uncaughtException:", err.message);
});
process.on("unhandledRejection", (err) => {
  console.error("[vite] unhandledRejection:", err instanceof Error ? err.message : err);
});

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    allowedHosts: ['frp-fun.com'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8102',
        changeOrigin: true,
      },
    },
  },
})
