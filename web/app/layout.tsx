import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { SITE_NAME, TAGLINE } from "@/lib/site";

export const metadata: Metadata = {
  title: `${SITE_NAME}: ${TAGLINE}`,
  description: "Upload a STEP file, answer a short form, and get a supplier-ready RFQ package with every value traceable.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="nav">
          <div className="wrap">
            <Link href="/" className="brand">
              <span className="brand-mark">{SITE_NAME[0]}</span> {SITE_NAME}
            </Link>
            <div className="nav-links">
              <Link href="/#how">How it works</Link>
              <Link href="/#trust">Trust</Link>
              <Link href="/#samples">Samples</Link>
            </div>
            <div className="spacer" />
            <Link href="/new" className="btn primary">New RFQ</Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
