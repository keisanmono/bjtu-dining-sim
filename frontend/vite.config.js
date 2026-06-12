// 文件说明：Vite 配置文件：定义前端端口、构建分包和 /api 代理。

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// FastAPI 后端默认监听 8001；如需切换端口，可在启动前端时设置 VITE_API_TARGET。
const apiTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [vue()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts'],
          element: ['element-plus', '@element-plus/icons-vue'],
          vendor: ['vue', 'axios']
        }
      }
    }
  },
  server: {
    // Vite 开发服务默认给浏览器访问的端口。
    port: 5173,
    proxy: {
      // 前端代码统一请求 /api/...，这里转发到后端 8001，避免跨域和硬编码完整地址。
      '/api': {
        target: apiTarget,
        changeOrigin: true
      }
    }
  }
})
