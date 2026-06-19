# Vitest Mocking Patterns — Reference

Session-tested recipes for mocking constructor-based dependencies and environment-variable-driven modules in Vitest.

## 1. Mocking a Class Constructor (e.g., `new OpenAI()`)

**Problem:** Source code does `new OpenAI({ apiKey })`. `vi.fn().mockImplementation(() => ({...}))` fails with "is not a constructor".

**Solution:** Return a real class from `vi.mock`:

```typescript
const mockCreate = vi.fn();

vi.mock("openai", () => {
  return {
    default: class {
      constructor() {
        return {
          chat: {
            completions: {
              create: mockCreate,
            },
          },
        };
      }
    },
  };
});
```

**Why:** Vitest's `vi.mock` hoisting replaces the module at import time. The source does `new OpenAI(...)`, so the mock must be constructible.

---

## 2. Stubbing Environment Variables Alongside `global.fetch`

**Problem:** You mock `global.fetch` for a provider that internally calls `process.env.AI_PROVIDER` or `getConfiguredAIProvider()`. The test still instantiates the wrong provider or uses the wrong model.

**Solution:** Stub both the env var AND the fetch mock, and reset between tests:

```typescript
describe("provider-gateway", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    global.fetch = mockFetch;
    vi.stubEnv("GEMINI_API_KEY", "test-key");
    vi.stubEnv("AI_PROVIDER", "gemini");   // <-- critical
    vi.stubEnv("AI_TIMEOUT_MS", "30000");
    mockFetch.mockReset();                  // <-- prevents call count leakage
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });
});
```

**Why:** `vi.stubEnv` affects `process.env` reads that happen at module load time or inside the function under test. Without it, the provider factory may fall back to a default (e.g., "mock") and bypass your `global.fetch` mock entirely.

---

## 3. Mock Provider Returns Empty Object — Schema Validation Fails

**Problem:** A `MockProvider` returns `{}` for unknown schemas. Your test expects `z.object({ result: z.unknown() })` to pass with `{}`, but Zod rejects it because `unknown()` does not allow undefined fields.

**Solution:** Match the mock output to what the mock actually returns:

```typescript
// MockProvider returns {} for unrecognized task types
// So the schema must accept an empty object:
const outputSchema = z.object({});  // <-- {} passes

// NOT this — { result: undefined } fails validation:
// const outputSchema = z.object({ result: z.unknown() });
```

**Why:** `z.object({ result: z.unknown() })` requires the key `result` to exist (even if its value is `undefined` is debatable). An empty object `{}` is missing the key entirely, so `safeParse` returns `success: false`.

---

## 4. Preventing Mock Call Leakage Between Tests

**Always reset mocks in `beforeEach`:**

```typescript
beforeEach(() => {
  mockFetch.mockReset();
  mockCreate.mockReset();
});
```

Without `mockReset()`, `toHaveBeenCalledTimes(1)` in test N may count calls from test N-1, causing flaky failures.

---

## 5. Import Name Collision After Rename Refactoring

**Problem:** You rename `createClient` → `createBrowserClient` in both the source and the test. The test also mocks `@supabase/ssr`'s `createBrowserClient`, causing a name collision.

**Solution:** Use an alias for the SUT import:

```typescript
// Source module exports createBrowserClient
// We also mock @supabase/ssr which exports createBrowserClient
import { createBrowserClient as sut } from "@/lib/db/supabase-browser";
import { createBrowserClient } from "@supabase/ssr";

describe("supabase-browser", () => {
  it("creates browser client with public env", () => {
    const client = sut();  // <-- calls the source module
    expect(createBrowserClient).toHaveBeenCalledWith(...);  // <-- checks the mock
  });
});
```

**Why:** After renaming, both the SUT and the mocked dependency may export the same name. TypeScript/JavaScript imports are lexically scoped — using `as sut` (or `as mockCreateBrowserClient`) disambiguates without changing the test logic.

---

## 6. Error Message Synchronization After Code Changes

**Problem:** You change an error message in production code (e.g., `"Gemini request failed"` → `"Gemini API request failed"`). Existing tests with `.rejects.toThrow("Gemini request failed")` now fail.

**Solution:** Update the test expectation to match the new error message:

```typescript
// Before (fails after rename):
await expect(geminiProvider.generateObject({...}))
  .rejects.toThrow("Gemini request failed");

// After (passes):
await expect(geminiProvider.generateObject({...}))
  .rejects.toThrow("Gemini API request failed");
```

**Why:** Tests should verify the *actual* behavior, not a cached copy of it. When refactoring error messages or validation logic, grep for the old string in tests and update them in the same commit.

---

## Checklist for AI Provider Tests

- [ ] `vi.mock` returns a constructible class if the source uses `new`
- [ ] `vi.stubEnv` sets `AI_PROVIDER`, `*_API_KEY`, and `AI_TIMEOUT_MS`
- [ ] `mockReset()` in `beforeEach` for every mock function
- [ ] `vi.unstubAllEnvs()` in `afterEach`
- [ ] Schema expectations match what the mock provider actually returns
- [ ] Model name expectations match the stubbed provider's default (e.g., `gemini-2.5-flash` for Gemini, `gpt-4.1-mini` for OpenAI)
