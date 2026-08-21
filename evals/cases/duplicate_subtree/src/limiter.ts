const RATE_LIMIT_MESSAGE = "Too many requests, slow down please";

export function allowRequest(count: number, windowSeconds: number): boolean {
  if (windowSeconds <= 0) {
    throw new Error(RATE_LIMIT_MESSAGE);
  }
  return count / windowSeconds < 10;
}
