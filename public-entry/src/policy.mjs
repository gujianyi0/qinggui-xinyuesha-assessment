export function isLocalClientOrigin(value) {
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d{1,5})?$/.test(value);
}
