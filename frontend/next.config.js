const { withSentryConfig } = require("@sentry/nextjs");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    serverActions: { allowedOrigins: ['localhost:3000'] },
  },
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.supabase.co' },
      { protocol: 'https', hostname: 'lh3.googleusercontent.com' },
    ],
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              // Scripts: self + Next.js inline scripts (nonce-based would be ideal but
              // requires middleware; unsafe-inline is the pragmatic baseline for Next.js)
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com https://*.posthog.com https://*.sentry.io",
              // Styles: self + inline (Next.js injects styles)
              "style-src 'self' 'unsafe-inline'",
              // Images: self + Supabase storage + Google avatars + data URIs
              "img-src 'self' data: blob: https://*.supabase.co https://lh3.googleusercontent.com",
              // Fonts: self only
              "font-src 'self'",
              // API calls: self + Railway backend + Stripe + PostHog + Sentry
              "connect-src 'self' https://api.onegoalpro.app https://api.stripe.com https://*.posthog.com https://*.sentry.io",
              // Frames: Stripe only (for payment elements)
              "frame-src https://js.stripe.com https://hooks.stripe.com",
              // Objects/embeds: none
              "object-src 'none'",
              // Base URI: self only (prevents base tag injection)
              "base-uri 'self'",
              // Form submissions: self only
              "form-action 'self'",
              // Upgrade insecure requests in production
              "upgrade-insecure-requests",
            ].join('; '),
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
        ],
      },
    ];
  },
};

module.exports = withSentryConfig(nextConfig, {
  silent: true,
  org: "your-org-name",  // From Sentry settings
  project: "onegoal-frontend",
});
