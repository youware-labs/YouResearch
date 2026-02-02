import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'YouResearch - LaTeX IDE with AI',
  description: 'Local-first LaTeX IDE with embedded AI agent',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-aura-bg text-aura-text antialiased">
        {children}
      </body>
    </html>
  );
}
