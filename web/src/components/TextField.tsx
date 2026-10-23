import { useLayoutEffect, useRef, type ReactElement } from "react";

type Props = {
  value: string;
  onValueChange: (value: string) => void;
  multiline?: boolean;
  rows?: number;
  id?: string;
  type?: "text";
  url?: boolean;
  spellCheck?: boolean;
  "aria-required"?: "true";
  "aria-invalid"?: "true";
  "aria-describedby"?: string;
};

/**
 * Campo di testo che tiene il valore solo nella proprietà del nodo, mai nel markup: l'HTML della
 * pagina non contiene il testo dell'utente come attributo né come figlio (difesa in profondità
 * contro l'XSS memorizzato, THR-070). Lo stato resta nel genitore.
 */
export function TextField({
  value,
  onValueChange,
  multiline,
  rows,
  url,
  ...rest
}: Props): ReactElement {
  const ref = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    if (ref.current && ref.current.value !== value) ref.current.value = value;
  }, [value]);
  const onInput = (event: { currentTarget: { value: string } }): void =>
    onValueChange(event.currentTarget.value);
  return multiline ? (
    <textarea ref={ref} rows={rows} onChange={onInput} {...rest} />
  ) : (
    <input
      ref={ref}
      onChange={onInput}
      inputMode={url ? "url" : undefined}
      autoCapitalize={url ? "off" : undefined}
      {...rest}
    />
  );
}
