import { defineConfig } from 'vite'
export default defineConfig({ root: 'src/renderer', base: './', esbuild: { jsx: 'automatic' }, build: { outDir: '../../ui', emptyOutDir: true } })
