import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "ForgeAI",
  description: "AI-native Software Engineering Workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
