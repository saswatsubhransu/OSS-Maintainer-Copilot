import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OSS Maintainer Copilot",
  description: "AI-assisted, human-controlled GitHub issue triage.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
