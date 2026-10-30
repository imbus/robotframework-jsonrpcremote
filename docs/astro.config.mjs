// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLinksValidator from 'starlight-links-validator';

// https://astro.build/config
export default defineConfig({
	site: 'https://imbus.github.io',
	base: '/robotframework-jsonrpcremote',
	integrations: [
		starlight({
			title: 'JsonRpcRemote',
			social: [
				{
					icon: 'github',
					label: 'GitHub',
					href: 'https://github.com/imbus/robotframework-jsonrpcremote',
				},
			],
			plugins: [starlightLinksValidator()],
			routeMiddleware: './src/routeData.ts',
			sidebar: [
				{
					label: 'Getting started',
					items: ['getting-started', 'why-jsonrpcremote', 'roadmap'],
				},
				{
					label: 'Guides',
					items: [
						'guides/tcp-and-stdio',
						'guides/sessions',
						'guides/lost-connections',
						'guides/container',
						'guides/several-libraries',
					],
				},
				{
					label: 'Reference',
					items: ['reference/library', 'reference/server', 'reference/protocol'],
				},
			],
		}),
	],
});
