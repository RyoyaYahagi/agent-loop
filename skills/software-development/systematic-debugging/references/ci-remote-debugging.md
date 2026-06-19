# CI Remote Debugging Patterns

## gh run view --log-failed

When CI fails on a PR but local tests pass, the fastest way to get the exact error is to pull the build logs remotely rather than trying to reproduce CI conditions locally.

### Steps

1. List recent runs for the branch:
   ```bash
   gh run list --branch <branch-name> --limit 5
   ```

2. View the failed run summary:
   ```bash
   gh run view <run-id>
   ```

3. Get the detailed failure log for the specific job:
   ```bash
   gh run view <run-id> --log-failed --job <job-id>
   ```

   - `run-id`: from step 1
   - `job-id`: from step 2 (shown next to each job name)

### Why This Beats Local Reproduction

- CI may use different Node versions, environment variables, or build flags
- Local caches can hide issues
- `next build` type-checks the full app; `tsc` or `vitest` may not
- The log output includes the exact file path, line number, and error message

### Common CI-Only Failures

| Failure Type | Why CI Only | Fix Pattern |
|--------------|-------------|-------------|
| `Property 'X' does not exist on type 'Y'` | Service return type missing a field that the route expects | Add the field to the service return value |
| `Argument of type '"..."' is not assignable` | Union type narrowed; existing literal not in union | Add the literal to the union definition |
| Missing import / module resolution | `tsconfig.json` `paths` or `baseUrl` differs in build | Check `next build` vs `tsc` behavior |

## TypeScript Union Type Narrowing Pitfall

When you change a `string` type to a union type (e.g., `ErrorCode`), the TypeScript compiler will catch ALL existing string literals at build time.

### Detection

```
Argument of type '"NOT_IMPLEMENTED"' is not assignable to parameter of type 'ErrorCode'.
```

### Fix

1. Find all call sites:
   ```bash
   grep -rn 'new AppError(' src/
   ```

2. Extract all literal codes used

3. Add missing codes to the union definition:
   ```ts
   export const ERROR_CODES = {
     // ... existing codes ...
     NOT_IMPLEMENTED: "NOT_IMPLEMENTED",
   } as const;
   ```

### Prevention

Before narrowing a `string` to a union:
- Run `grep -rn 'new ClassName(' src/` to find all literal usages
- Or run `npm run build` locally after the type change before pushing

## Cross-Layer Data Flow for Metrics

When tracking metrics (cost, tokens, latency) across layers:

```
API Route  →  Service  →  Provider
    ↑           ↑
  needs    must expose
  metric   in return type
```

If the service doesn't return the metric, the API route can't access it.

### Pattern

```ts
// service.ts
return {
  ...businessData,
  estimatedCostUsd: aiResult.usage?.estimatedCostUsd ?? 0,
};

// route.ts
const result = await runRuleReview({...});
if (result.estimatedCostUsd) {
  await incrementAiCostUsage({...});
}
```
