import type { Metadata, Viewport } from 'next';
import { DM_Sans, DM_Mono } from 'next/font/google';
import Script from 'next/script';
import { AppProvider } from '@/lib/store';
import { AuthProvider } from '@/lib/auth';
import AuthGate from '@/components/AuthGate';
import './globals.css';

const dmSans = DM_Sans({
  subsets: ['latin', 'latin-ext'],
  weight: ['300', '400', '500', '600', '700'],
  style: ['normal', 'italic'],
  variable: '--font-dm-sans',
  display: 'swap',
});

const dmMono = DM_Mono({
  subsets: ['latin', 'latin-ext'],
  weight: ['400', '500'],
  variable: '--font-dm-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  manifest: '/manifest.webmanifest',
  title: 'Opes — inteligentny agregator informacji rynkowej',
  description:
    'Osobisty system filtrowania i streszczania informacji rynkowej pod skład portfela inwestycyjnego. Materiał informacyjny i edukacyjny — nie stanowi porady inwestycyjnej.',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '32x32' },
      { url: '/icon.png', type: 'image/png', sizes: '192x192' },
    ],
    shortcut: '/favicon.ico',
    apple: '/apple-icon.png',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0f1318',
};

const themeInit = `(function(){try{var t=localStorage.getItem('opes-theme')||'dark';document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

const serviceWorkerRegistration = `(function(){if(!('serviceWorker' in navigator)){return;}window.addEventListener('load',function(){navigator.serviceWorker.register('/sw.js').catch(function(error){console.warn('Opes service worker registration failed',error);});});})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pl" data-theme="dark" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="icon" href="/icon.png" type="image/png" />
        <link rel="apple-touch-icon" href="/apple-icon.png" />
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className={`${dmSans.variable} ${dmMono.variable}`}>
        <Script id="opes-service-worker" strategy="afterInteractive">
          {serviceWorkerRegistration}
        </Script>
        <AuthProvider>
          <AppProvider>
            <AuthGate>{children}</AuthGate>
          </AppProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
