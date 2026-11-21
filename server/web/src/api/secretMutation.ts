import {
  type DefaultError,
  useMutation,
  type UseMutationOptions,
} from "@tanstack/react-query";

/**
 * For a mutation whose result is a secret shown once. TanStack keeps a
 * finished mutation's result for 5 minutes by default; `gcTime: 0` drops it as
 * soon as nothing observes it, which happens when the caller calls `reset()`
 * after the SecretReveal closes.
 */
export function useSecretMutation<
  TData = unknown,
  TError = DefaultError,
  TVariables = void,
  TContext = unknown,
>(
  options: Omit<
    UseMutationOptions<TData, TError, TVariables, TContext>,
    "gcTime"
  >,
) {
  return useMutation({ ...options, gcTime: 0 });
}
