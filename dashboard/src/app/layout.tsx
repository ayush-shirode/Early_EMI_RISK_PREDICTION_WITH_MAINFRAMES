import type { Metadata } from 'next';
import './globals.css';
import { CustomerProvider } from '@/context/CustomerContext';

export const metadata: Metadata = {
  title: 'Vigilance AI — EMI Stress Early Warning',
  description: 'Mainframe batch (z/OS, COBOL, DFSORT, REXX via Zowe) + machine-learning early warning for EMI repayment stress.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet" />
      </head>
      <body style={{ fontFamily: "'Outfit', sans-serif" }}>
        <CustomerProvider>
          {children}
        </CustomerProvider>
      </body>
    </html>
  );
}
