// Decrypts the bundle written by src/dashboard/bundle.py (PBKDF2-SHA256 -> AES-256-GCM over gzip'd JSON).
export const BUNDLE_FORMAT = "trader-dashboard-v1";

const encoder = new TextEncoder();
const fromBase64 = (text) => Uint8Array.from(atob(text), (char) => char.charCodeAt(0));

/** Only an authentication failure means a wrong password; anything else is reported as itself. */
export class WrongPasswordError extends Error {}

export async function decryptBundle(envelopeText, password) {
  if (typeof DecompressionStream === "undefined" || !globalThis.crypto?.subtle) {
    throw new Error("this browser has no Web Crypto or DecompressionStream");
  }
  const envelope = JSON.parse(envelopeText);
  if (envelope.format !== BUNDLE_FORMAT || envelope.compression !== "gzip") {
    throw new Error("unsupported dashboard bundle format");
  }
  const iterations = Number(envelope.kdf.iterations);
  if (!Number.isInteger(iterations) || iterations < 1) throw new Error("invalid key derivation settings");

  const { subtle } = globalThis.crypto;
  const material = await subtle.importKey("raw", encoder.encode(password.normalize("NFC")), "PBKDF2", false, [
    "deriveKey",
  ]);
  const key = await subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: fromBase64(envelope.kdf.salt), iterations },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"],
  );
  // A wrong password fails here: AES-GCM authenticates the data before anything is returned.
  let compressed;
  try {
    compressed = await subtle.decrypt(
      { name: "AES-GCM", iv: fromBase64(envelope.cipher.iv), additionalData: encoder.encode(BUNDLE_FORMAT) },
      key,
      fromBase64(envelope.data),
    );
  } catch {
    throw new WrongPasswordError("the password does not open this bundle");
  }
  const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(stream).text());
}
