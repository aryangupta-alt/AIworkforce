import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Wohlig Report Dashboard',
  description: 'View and schedule workforce reports',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
