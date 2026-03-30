import type { Metadata, Viewport } from 'next'
import { Playfair_Display, DM_Sans, DM_Mono } from 'next/font/google'
import './globals.css'
import { initPostHog } from "@/lib/posthog"
import CookieBanner from '@/components/CookieBanner'  

const playfair = Playfair_Display({
  subsets: ['latin'],
  variable: '--font-display',
  display: 'swap',
})

const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-sans',
  axes: ['opsz'],
  display: 'swap',
})

const dmMono = DM_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  weight: ['400', '500'],
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'One Goal. One Identity. | OneGoal Pro',
  description: "You don't have a focus problem. You have an identity problem. OneGoal Pro finds your one goal, then coaches you toward the person who achieves it.",
  keywords: ['goal setting', 'personal development', 'AI coaching', 'habit building', 'identity-based goals'],
  openGraph: {
    title: 'One Goal. One Identity. | OneGoal Pro',
    description: 'One goal. Full commitment. No excuses.',
    url: 'https://onegoalpro.app',
    siteName: 'OneGoal Pro',
    images: [
      {
        url: 'https://onegoalpro.app/og-image.png',
        width: 1200,
        height: 630,
        alt: 'OneGoal Pro',
      }
    ],
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'One Goal. One Identity. | OneGoal Pro',
    description: 'One goal. Full commitment. No excuses.',
    images: ['https://onegoalpro.app/og-image.png'],
  },
}

export const viewport: Viewport = {
  themeColor: '#0A0908',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  initPostHog();
  
  return (
    <html
      lang="en"
      className={`${playfair.variable} ${dmSans.variable} ${dmMono.variable}`}
    >
      <body className="antialiased overflow-x-hidden">
        {children}
        <CookieBanner />
      </body>
    </html>
  )
}