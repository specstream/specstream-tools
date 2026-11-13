import { defineHealthCheck } from 'twenty-sdk/define';

import { HEALTH_CHECK_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { SpecStreamError } from 'src/specstream/api';
import { specstreamFromEnv } from 'src/specstream/runtime';

// Reports a key SpecStream refuses. A missing key is Twenty's own banner (the variable is required),
// and an outage throws, which Twenty shows as nothing rather than as an error.
export default defineHealthCheck({
  universalIdentifier: HEALTH_CHECK_UNIVERSAL_IDENTIFIER,
  name: 'health-check',
  handler: async () => {
    const specstream = specstreamFromEnv();
    if (!specstream) return { status: 'OK' as const };
    try {
      await specstream.account();
    } catch (error) {
      if (error instanceof SpecStreamError && (error.status === 401 || error.status === 403)) {
        return {
          status: 'ERROR' as const,
          title: 'SpecStream refused the API key',
          description: 'Create a key at specstream.ai/workspace and paste it in the app settings.',
        };
      }
      throw error;
    }
    return { status: 'OK' as const };
  },
});
