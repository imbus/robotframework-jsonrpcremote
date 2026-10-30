import { defineRouteMiddleware } from '@astrojs/starlight/route-data';

// Change or remove this banner, and `routeMiddleware` in astro.config.mjs, when the project leaves pre-alpha.
export const onRequest = defineRouteMiddleware((context) => {
	context.locals.starlightRoute.entry.data.banner = {
		content:
			'JsonRpcRemote is in pre-alpha and under active development. This documentation describes the development version on <code>main</code>, which may differ from the latest release, and more features are coming: see <a href="/robotframework-jsonrpcremote/roadmap/">Status and roadmap</a>.',
	};
});
