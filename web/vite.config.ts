import { defineConfig } from 'vite';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/* web/ 根(本文件所在目录) */
const root = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  /* 相对路径:桥接静态服务在任意子路径可用(不做 file:// 直开,见报告 §3) */
  base: './',
  build: {
    outDir: 'dist',
    /* three 是**懒加载**的独立分包(546KB / gzip 136KB),它不进首屏路径,
     * 故 500KB 的默认告警阈值在这里只会制造一次性的噪声。调到 700KB 之后,
     * 这条警告恢复成「真的有东西意外变大了」的信号 —— 留着它比关掉它有用。 */
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      input: {
        index: resolve(root, 'index.html'),
        console: resolve(root, 'console.html'),
        viz: resolve(root, 'viz.html'),
      },
      output: {
        /* three 固定独立包(动态 import,不占首屏;名字供排查用) */
        manualChunks: { three: ['three'] },
      },
    },
  },
  server: {
    /* 仅开发机:把 /api 代理到桥接(127.0.0.1:8642),生产走桥接静态服务 */
    proxy: { '/api': { target: 'http://127.0.0.1:8642', changeOrigin: false } },
  },
});
