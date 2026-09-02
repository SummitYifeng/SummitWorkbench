import { defineConfig } from 'vite';

// 构建产物打进 Python 包：src/summit_workbench/webapp/static
// 开发模式直连本机 FastAPI（/api 代理到 wb web 的 8787 端口）。
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/' : '/',
  build: {
    outDir: '../src/summit_workbench/webapp/static',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8787',
    },
  },
}));
