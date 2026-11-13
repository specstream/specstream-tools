import * as z from "zod";

/** What the form sends. The key is never stored in the team configuration. */
export const ConnectSchema = z.object({
  apiKey: z.string().min(1),
});

/** What the extension keeps about the team: enough to show that a key is connected, never the key. */
export const TeamConfigSchema = z.object({
  keyHint: z.string(),
  email: z.string().nullable(),
});

export type TeamConfig = z.output<typeof TeamConfigSchema>;
export type SiteConfig = Record<string, never>;
