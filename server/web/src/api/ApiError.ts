export const NETWORK_CODE = "network";
export const UNKNOWN_CODE = "unknown";

export class ApiError extends Error {
  /** HTTP status, or 0 when no response arrived. */
  readonly status: number;
  /** The server's error code, or `network` / `unknown` when there isn't one. */
  readonly code: string;
  /** The form field the server blames, when it names one. */
  readonly field: string | undefined;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    field?: string;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.field = init.field;
  }
}

function isErrorBody(
  body: unknown,
): body is { code: string; message: string; field?: unknown } {
  return (
    typeof body === "object" &&
    body !== null &&
    "code" in body &&
    typeof body.code === "string" &&
    "message" in body &&
    typeof body.message === "string"
  );
}

export async function apiErrorFromResponse(
  response: Response,
): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.clone().json();
  } catch {
    body = undefined;
  }
  if (isErrorBody(body)) {
    return new ApiError({
      status: response.status,
      code: body.code,
      message: body.message,
      field: typeof body.field === "string" ? body.field : undefined,
    });
  }
  return new ApiError({
    status: response.status,
    code: UNKNOWN_CODE,
    message: response.statusText || `HTTP ${response.status}`,
  });
}

export function networkError(cause: unknown): ApiError {
  const error = new ApiError({
    status: 0,
    code: NETWORK_CODE,
    message: cause instanceof Error ? cause.message : "network error",
  });
  error.cause = cause;
  return error;
}
