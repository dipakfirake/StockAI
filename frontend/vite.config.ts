/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    exclude: ['e2e/**', 'node_modules/**'],
  },
  server: {
    host: true, // Listen on all network interfaces (required for Docker)
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: {
      clientPort: process.env.VITE_HMR_PORT ? Number(process.env.VITE_HMR_PORT) : undefined,
    },
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.VITE_WS_URL || 'ws://localhost:8000',
        ws: true,
      },
    },
    watch: {
      usePolling: true,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false, // Omit large sourcemaps in production bundle for optimal performance
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom', 'zustand'],
          'vendor-charts': ['lightweight-charts'],
          'vendor-export': ['jspdf', 'html2canvas'],
          'vendor-icons': ['lucide-react'],
        },
      },
    },
  },
})
