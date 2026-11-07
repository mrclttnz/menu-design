// React Aria inserisce da sé un elemento <style> (regola `touch-action` dei controlli premibili)
// se nel documento non c'è un elemento con questo id. La CSP dell'app (`style-src 'self'`, SR-031)
// lo bloccherebbe e ogni apertura della pagina segnalerebbe una violazione: l'id viene occupato da
// un <meta> vuoto e la stessa regola sta in styles/base.css.
const ARIA_STYLE_ID = "react-aria-pressable-style";

export function reserveAriaStyleId(doc: Document = document): void {
  if (doc.getElementById(ARIA_STYLE_ID)) return;
  const marker = doc.createElement("meta");
  marker.id = ARIA_STYLE_ID;
  doc.head.prepend(marker);
}
