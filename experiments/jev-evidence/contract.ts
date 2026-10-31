/** Strict boundary for the pinned, text-only Jev request/response contract. */
export const MODEL = 'jev-1.13.0';
export const ENDPOINT = 'https://api.typesafe.ai/v1/systemone';
export const POLICY = Object.freeze({ yes: 0.7, no: 0.3, choice: 0.7 });
export type JsonObject = Record<string, unknown>;
export type Question = { type: 'noul'; instructions: string; criteria: { true: string; false: string } }
  | { type: 'choice'; instructions: string; criteria: Record<string, string> }
  | { type: 'score'; instructions: string; criteria: string[] };
export type Request = { model: string; state: JsonObject; questions: Record<string, Question> };
export type Noul = { type: 'noul'; noul: number };
export type Choice = { type: 'choice'; choice: string; confidence: number; probabilities: Record<string, number> };
export type Score = { type: 'score'; score: number; confidence: number; legend: Record<string, string>; probabilities: Record<string, number> };
export type Response = { model: string; answers: Record<string, Noul | Choice | Score>; usage: { input_tokens: number; output_tokens: number } };

export function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
export function object(value: unknown): JsonObject {
  assert(value !== null && typeof value === 'object' && !Array.isArray(value), 'Expected object');
  return value as JsonObject;
}
export function string(value: unknown): string {
  assert(typeof value === 'string' && value.trim().length > 0, 'Expected nonempty string');
  return value;
}
export function strings(value: unknown): string[] {
  assert(Array.isArray(value), 'Expected string array');
  const result = value.map(string);
  assert(new Set(result).size === result.length, 'Duplicate array entries');
  return result;
}
export function probability(value: unknown): number {
  assert(typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1, 'Invalid probability');
  return value;
}
export function integer(value: unknown): number {
  assert(typeof value === 'number' && Number.isSafeInteger(value) && value >= 0, 'Invalid nonnegative integer');
  return value;
}
export function keysEqual(actual: object, expected: string[]): boolean {
  const keys = Object.keys(actual);
  return keys.length === expected.length && expected.every(key => Object.hasOwn(actual, key));
}
export function validateRequest(raw: unknown): Request {
  const request = object(raw);
  assert(request.model === MODEL, 'Model must be pinned to jev-1.13.0');
  object(request.state);
  const questions = object(request.questions);
  assert(Object.keys(questions).length > 0, 'Questions are required');
  for (const rawQuestion of Object.values(questions)) {
    const question = object(rawQuestion);
    string(question.instructions);
    if (question.type === 'noul') {
      const criteria = object(question.criteria);
      assert(keysEqual(criteria, ['true', 'false']), 'Invalid noul criteria');
      Object.values(criteria).forEach(string);
    } else if (question.type === 'choice') {
      const criteria = object(question.criteria);
      assert(Object.keys(criteria).length >= 1 && Object.keys(criteria).length <= 255, 'Invalid choice count');
      Object.keys(criteria).forEach(string);
      Object.values(criteria).forEach(string);
    } else if (question.type === 'score') {
      const levels = strings(question.criteria);
      assert(levels.length >= 2 && levels.length <= 10, 'Use 2 to 10 ordered score levels');
    } else throw new Error('Unsupported question type');
  }
  return request as Request;
}

function distribution(raw: unknown, keys: string[]): Record<string, number> {
  const values = object(raw);
  assert(keysEqual(values, keys), 'Probability keys do not match the request');
  Object.values(values).forEach(probability);
  const sum = Object.values(values).reduce<number>((a, b) => a + (b as number), 0);
  assert(Math.abs(sum - 1) <= 0.001, 'Probabilities must sum to approximately 1');
  return values as Record<string, number>;
}

function scoreMatchesRoundedProbabilities(score: number, probabilities: number[]): boolean {
  // Compatibility assumption for observed two-decimal API values, not a provider precision guarantee.
  const halfStep = 0.005;
  const epsilon = 1e-12;
  const lower = probabilities.map(p => Math.max(0, p - halfStep));
  const capacity = probabilities.map((p, i) => Math.min(1, p + halfStep) - lower[i]);
  const extremeMean = (descending: boolean): number => {
    let remaining = 1 - lower.reduce((sum, p) => sum + p, 0);
    let mean = lower.reduce((sum, p, i) => sum + i * p, 0);
    // Allocate rounding uncertainty while keeping the underlying probability total exactly one.
    for (let step = 0; step < lower.length; step++) {
      const i = descending ? lower.length - 1 - step : step;
      const added = Math.min(remaining, capacity[i]);
      mean += i * added;
      remaining -= added;
    }
    assert(Math.abs(remaining) <= epsilon, 'Infeasible rounded score distribution');
    return mean;
  };
  return score + halfStep + epsilon >= extremeMean(false)
    && score - halfStep - epsilon <= extremeMean(true);
}

export function validateResponse(request: Request, raw: unknown): Response {
  validateRequest(request);
  const response = object(raw);
  assert(response.model === request.model, 'Response model differs from pinned model');
  const answers = object(response.answers);
  assert(keysEqual(answers, Object.keys(request.questions)), 'Missing or unexpected answer IDs');
  const usage = object(response.usage);
  integer(usage.input_tokens);
  integer(usage.output_tokens);
  for (const [id, question] of Object.entries(request.questions)) {
    const answer = object(answers[id]);
    assert(answer.type === question.type, 'Answer type mismatch');
    if (question.type === 'noul') {
      probability(answer.noul);
      continue;
    }
    probability(answer.confidence);
    if (question.type === 'choice') {
      const p = distribution(answer.probabilities, Object.keys(question.criteria));
      const choice = string(answer.choice);
      assert(Object.hasOwn(p, choice), 'Unknown selected choice');
      assert(p[choice] + 1e-9 >= Math.max(...Object.values(p)), 'Selected choice is not a probability maximum');
    } else {
      const levels = question.criteria.map((_, i) => String(i));
      const p = distribution(answer.probabilities, levels);
      const legend = object(answer.legend);
      assert(keysEqual(legend, levels), 'Score legend keys mismatch');
      levels.forEach((key, i) => assert(legend[key] === question.criteria[i], 'Score legend differs from request'));
      assert(typeof answer.score === 'number' && Number.isFinite(answer.score)
        && answer.score >= 0 && answer.score <= levels.length - 1
        && scoreMatchesRoundedProbabilities(answer.score, levels.map(key => p[key])), 'Invalid expected score');
    }
  }
  return response as Response;
}

/** Explicit call only. No automatic sends, retries, key discovery, or response-body logging. */
export async function callJev(request: Request, apiKey: string, transport: typeof fetch = fetch): Promise<Response> {
  validateRequest(request);
  assert(apiKey.trim().length > 0, 'API key required');
  let result: globalThis.Response;
  try {
    result = await transport(ENDPOINT, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(30_000),
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
  } catch { throw new Error('Jev transport failed or timed out'); }
  assert(result.ok, `Jev HTTP ${result.status}; no decision produced`);
  let body: unknown;
  try { body = await result.json(); } catch { throw new Error('Jev returned invalid JSON'); }
  return validateResponse(request, body);
}

export function noul(response: Response, id: string): number {
  const answer = response.answers[id];
  assert(answer?.type === 'noul', 'Expected noul answer');
  return answer.noul;
}
export function choice(response: Response, id: string): Choice {
  const answer = response.answers[id];
  assert(answer?.type === 'choice', 'Expected choice answer');
  return answer;
}
