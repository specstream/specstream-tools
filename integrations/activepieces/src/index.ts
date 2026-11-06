import { createPiece } from '@activepieces/pieces-framework';
import { PieceCategory } from '@activepieces/shared';
import { extractPagesAction } from './lib/actions/extract-pages';
import { findListAction } from './lib/actions/find-list';
import { getListResultsAction } from './lib/actions/get-list-results';
import { webSearchAction } from './lib/actions/web-search';
import { specstreamCustomApiCallAction } from './lib/actions/custom-api-call';
import { newRowTrigger, newWatchedRowTrigger } from './lib/triggers/row-triggers';
import { specstreamAuth } from './lib/auth';

export const specstream = createPiece({
  displayName: 'SpecStream',
  description: 'SpecStream is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.',
  auth: specstreamAuth,
  minimumSupportedRelease: '0.88.2',
  logoUrl: 'https://cdn.activepieces.com/pieces/specstream.png',
  categories: [PieceCategory.SALES_AND_CRM, PieceCategory.ARTIFICIAL_INTELLIGENCE],
  authors: ['specstream'],
  actions: [webSearchAction, extractPagesAction, findListAction, getListResultsAction, specstreamCustomApiCallAction],
  triggers: [newRowTrigger, newWatchedRowTrigger],
});
