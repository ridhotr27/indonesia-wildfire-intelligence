import type { ApiErrorCode, ErrorResponse } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: ApiErrorCode,
    public readonly status: number,
    public readonly requestId?: string,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isErrorResponse(value: unknown): value is ErrorResponse {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ErrorResponse>;
  return typeof candidate.request_id === "string" && typeof candidate.error?.code === "string" && typeof candidate.error.message === "string";
}
