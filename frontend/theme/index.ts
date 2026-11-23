/**
 * NewsSnap AI - Unified Theme Export
 */

import { colors, getCategoryColor } from './colors';
import { typography } from './typography';
import { spacing, borderRadius, shadows } from './spacing';

export const theme = {
  colors,
  typography,
  spacing,
  borderRadius,
  shadows,
  getCategoryColor,
};

export type Theme = typeof theme;
export { colors, typography, spacing, borderRadius, shadows, getCategoryColor };
export default theme;

