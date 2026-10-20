/** IBAN normalisation and the ISO 13616 mod-97 check (pure). The server checks again. */
export function normalizeIban(input: string): string {
  return input.replace(/[\s\u00A0-]+/g, '').toUpperCase();
}

export function isValidIban(input: string): boolean {
  const iban = normalizeIban(input);
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/.test(iban)) return false;
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  let remainder = 0;
  for (const ch of rearranged) {
    const code = ch.charCodeAt(0);
    const digits = code >= 65 && code <= 90 ? String(code - 55) : ch;
    for (const d of digits) remainder = (remainder * 10 + Number(d)) % 97;
  }
  return remainder === 1;
}

/** "NL91ABNA0417164300" -> "NL91 ABNA 0417 1643 00" */
export function formatIban(input: string): string {
  return normalizeIban(input).replace(/(.{4})/g, '$1 ').trim();
}
