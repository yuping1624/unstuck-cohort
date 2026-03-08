import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { Analytics } from "@vercel/analytics/next";

export const metadata: Metadata = {
    title: "12-Week Job Searching Group Dashboard",
    description: "Dashboard for the job searching group members and admin.",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="zh-TW" suppressHydrationWarning>
            <body className="antialiased font-sans">
                <ThemeProvider>
                    {children}
                </ThemeProvider>
                <Analytics />
            </body>
        </html>
    );
}
