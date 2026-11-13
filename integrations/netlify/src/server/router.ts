import { TRPCError } from "@trpc/server";
import { procedure, router } from "./trpc.js";
import { ConnectSchema, TeamConfigSchema } from "../schema/team-config.js";
import { KEY_VARIABLE, checkKey, keyHint } from "../lib/specstream.js";

const needTeam = (teamId: string | null | undefined): string => {
  if (!teamId) {
    throw new TRPCError({ code: "BAD_REQUEST", message: "teamId is required" });
  }
  return teamId;
};

export const appRouter = router({
  connection: {
    /** Whether the team has a key, with its last four characters. The key itself is never returned. */
    status: procedure.query(async ({ ctx: { teamId, client } }) => {
      const team = needTeam(teamId);
      const saved = await client.getTeamConfiguration(team);
      const parsed = TeamConfigSchema.safeParse(saved?.config);
      if (!parsed.success) {
        return { connected: false as const };
      }
      return { connected: true as const, keyHint: parsed.data.keyHint, email: parsed.data.email };
    }),

    /** Check the key with SpecStream, then keep it as a secret team environment variable. */
    connect: procedure.input(ConnectSchema).mutation(async ({ ctx: { teamId, client }, input }) => {
      const team = needTeam(teamId);
      const key = input.apiKey.trim();
      const check = await checkKey(key);
      if (!check.ok) {
        throw new TRPCError({ code: "BAD_REQUEST", message: check.message });
      }
      try {
        await client.createOrUpdateVariable({
          accountId: team,
          key: KEY_VARIABLE,
          value: key,
          isSecret: true,
          scopes: ["builds", "functions", "runtime"],
        });
        await client.upsertTeamConfiguration(team, { keyHint: keyHint(key), email: check.email });
      } catch (cause) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: "Netlify did not save the key. Try again.",
          cause,
        });
      }
    }),

    /** Remove the variable and forget the team. */
    disconnect: procedure.mutation(async ({ ctx: { teamId, client } }) => {
      const team = needTeam(teamId);
      try {
        await client.deleteEnvironmentVariable({ accountId: team, key: KEY_VARIABLE });
        await client.deleteTeamConfiguration(team);
      } catch (cause) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: `Netlify did not remove the key. Delete ${KEY_VARIABLE} under Team settings > Environment variables.`,
          cause,
        });
      }
    }),
  },
});

export type AppRouter = typeof appRouter;
