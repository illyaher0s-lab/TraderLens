import "./globals.css";

export const metadata = {
  title: "TraderLens",
  description: "A-share strategy research and execution decision workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
