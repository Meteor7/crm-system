import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { configDefaults, defineConfig } from 'vitest/config'
import { usesFrappeRuntime } from './src/app/runtime-mode'

export default defineConfig(({ mode }) => {
  // Frappe is the only development and production runtime.
  // Unit tests use isolated fixtures without changing runtime configuration.
  const frappeBuild = usesFrappeRuntime(mode)
  return {
    base: frappeBuild ? '/assets/rayher_crm/crm/' : './',
    plugins: [vue()],
    resolve: {
      alias: [
        {
          find: '@/demo/personnel',
          replacement: fileURLToPath(new URL(
            frappeBuild ? './src/demo/personnel.frappe.ts' : './src/demo/personnel.ts',
            import.meta.url,
          )),
        },
        {
          find: '@/api/identity-switch',
          replacement: fileURLToPath(new URL(
            frappeBuild ? './src/api/identity-switch.ts' : './src/api/mock-identity-switch.ts',
            import.meta.url,
          )),
        },
        {
          find: '@/api/runtime-adapter',
          replacement: fileURLToPath(new URL(
            frappeBuild ? './src/api/runtime-adapter.frappe.ts' : './src/api/runtime-adapter.ts',
            import.meta.url,
          )),
        },
        { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
      ],
    },
    build: {
      chunkSizeWarningLimit: 600,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      css: true,
      pool: 'threads',
      maxWorkers: 2,
      exclude: [...configDefaults.exclude, '.superpowers/**', '.codex-tmp/**', '.codex-test-tmp/**'],
    },
  }
})
