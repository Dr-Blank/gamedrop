import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import path from 'node:path';

// Standalone config for component/unit tests. Mirrors the SvelteKit `$lib` and
// `$app/*` aliases so route pages and components import cleanly under jsdom.
export default defineConfig({
	plugins: [svelte(), svelteTesting()],
	resolve: {
		alias: {
			$lib: path.resolve('./src/lib'),
			'$app/navigation': path.resolve('./src/tests/mocks/navigation.js'),
			'$app/stores': path.resolve('./src/tests/mocks/stores.js'),
			'$app/environment': path.resolve('./src/tests/mocks/environment.js')
		}
	},
	test: {
		environment: 'jsdom',
		globals: true,
		setupFiles: ['./src/tests/setup.js'],
		include: ['src/tests/**/*.test.js'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'lcov', 'json'],
			include: ['src/lib/**'],
			exclude: ['src/tests/**', 'src/tests/mocks/**']
		}
	}
});
