export function Bad({ h }: { h: string }) {
  // ruleid: menu-dangerously-set-inner-html
  const a = <div dangerouslySetInnerHTML={{ __html: h }} />;
  // ruleid: menu-token-in-web-storage
  localStorage.setItem("t", h);
  // ok: menu-token-in-web-storage
  const b = h.length;
  return a + b;
}

export function BadSinks(el: HTMLElement, h: string) {
  // ruleid: menu-dom-html-sink
  el.innerHTML = h;
  // ruleid: menu-dom-html-sink
  el.outerHTML = h;
  // ruleid: menu-dom-html-sink
  el.insertAdjacentHTML("beforeend", h);
  // ruleid: menu-dom-html-sink
  document.write(h);
  // ruleid: menu-dom-html-sink
  document.writeln(h);
  // ruleid: menu-dynamic-code-eval
  eval(h);
  // ruleid: menu-dynamic-code-eval
  const f = new Function("a", h);
  // ruleid: menu-dynamic-code-eval
  window.eval(h);
  // ok: menu-dom-html-sink
  el.textContent = h;
  // ok: menu-dynamic-code-eval
  const g = JSON.parse(h);
  return [f, g];
}
