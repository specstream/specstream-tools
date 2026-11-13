import { IDLE_MAX_S, IDLE_MIN_S, TIMEOUT_MAX_S, TIMEOUT_MIN_S } from "./client.js";

export const DEFAULT_TIMEOUT_SECONDS = 300;
/** Long enough for a model to think between two steps; the API's own default of 60 is for a connected client. */
export const DEFAULT_IDLE_TIMEOUT_SECONDS = 300;

export const MISSING_KEY_MESSAGE =
  "SpecStream has no API key. Set plugins.entries.specstream-browser.config.apiKey (a SecretRef works) or the SPECSTREAM_API_KEY environment variable. " +
  "Create a key under Agents & API in your SpecStream workspace.";

export type PluginConfig = {
  apiKey?: unknown;
  timeoutSeconds?: number;
  idleTimeoutSeconds?: number;
  allowedDomains?: string[];
  blockMedia?: boolean;
};

export type ResolvedConfig = {
  apiKey: string;
  timeoutSeconds: number;
  idleTimeoutSeconds: number;
  allowedDomains: string[];
  blockMedia: boolean;
};

function within(value: number | undefined, fallback: number, low: number, high: number): number {
  const whole = Math.trunc(Number(value ?? fallback));
  if (!Number.isFinite(whole)) return fallback;
  return Math.min(high, Math.max(low, whole));
}

/** Reads the plugin config, falling back to SPECSTREAM_API_KEY for the key. Throws when no key is set. */
export function resolveConfig(config: PluginConfig | undefined, env: NodeJS.ProcessEnv = process.env): ResolvedConfig {
  const fromConfig = typeof config?.apiKey === "string" ? config.apiKey.trim() : "";
  const apiKey = fromConfig || (env.SPECSTREAM_API_KEY ?? "").trim();
  if (!apiKey) throw new Error(MISSING_KEY_MESSAGE);
  return {
    apiKey,
    timeoutSeconds: within(config?.timeoutSeconds, DEFAULT_TIMEOUT_SECONDS, TIMEOUT_MIN_S, TIMEOUT_MAX_S),
    idleTimeoutSeconds: within(config?.idleTimeoutSeconds, DEFAULT_IDLE_TIMEOUT_SECONDS, IDLE_MIN_S, IDLE_MAX_S),
    allowedDomains: (config?.allowedDomains ?? []).map((host) => String(host).trim().toLowerCase()).filter(Boolean),
    blockMedia: config?.blockMedia === true,
  };
}

/**
 * The length of one session. The model may ask for a shorter session than the configured one and never a longer
 * one, because the configured value bounds what a session can cost.
 */
export function effectiveTimeout(configuredSeconds: number, requestedSeconds: number | undefined): number {
  if (requestedSeconds === undefined || !Number.isFinite(requestedSeconds) || requestedSeconds <= 0) return configuredSeconds;
  return Math.max(TIMEOUT_MIN_S, Math.min(configuredSeconds, Math.trunc(requestedSeconds)));
}

function covers(rule: string, host: string): boolean {
  if (rule === host) return true;
  // "*.example.com" covers every host under example.com, and a narrower wildcard under it.
  return rule.startsWith("*.") && host.endsWith(rule.slice(1));
}

/**
 * The hosts one session may open. With hosts in the config, the model can narrow them and never add one;
 * with none in the config, the model's own list applies.
 */
export function effectiveDomains(configured: string[], requested: string[] | undefined): string[] {
  const asked = (requested ?? []).map((host) => String(host).trim().toLowerCase()).filter(Boolean);
  if (!configured.length) return asked;
  if (!asked.length) return configured;
  const outside = asked.filter((host) => !configured.some((rule) => covers(rule, host)));
  if (outside.length) {
    throw new Error(`Not in plugins.entries.specstream-browser.config.allowedDomains: ${outside.join(", ")}. A person adds a host there; a call cannot.`);
  }
  return asked;
}
