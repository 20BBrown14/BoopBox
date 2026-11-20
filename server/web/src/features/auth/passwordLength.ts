export const PASSWORD_MIN = 12;
export const PASSWORD_MAX = 128;

/**
 * Whether the length is one the server accepts. It counts code points after
 * NFC normalization, so an emoji is one character here too.
 */
export function passwordLengthOk(password: string): boolean {
  const length = [...password.normalize("NFC")].length;
  return length >= PASSWORD_MIN && length <= PASSWORD_MAX;
}
