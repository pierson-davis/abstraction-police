const RATE_LIMIT_MESSAGE = "Too many requests, slow down please";

export function describeLimit(limit: number): string {
  return RATE_LIMIT_MESSAGE + " limit=" + String(limit);
}
