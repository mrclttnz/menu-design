export function Bad({ h }: { h: string }) {
  // ruleid: menu-dangerously-set-inner-html
  const a = <div dangerouslySetInnerHTML={{ __html: h }} />;
  // ruleid: menu-token-in-web-storage
  localStorage.setItem("t", h);
  // ok: menu-token-in-web-storage
  const b = h.length;
  return a + b;
}
