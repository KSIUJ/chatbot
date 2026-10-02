// Sections of the admin panel, in tab order.
export const ADMIN_TABS = ['limits', 'reports', 'incidents', 'diagnostics'] as const;

export type AdminTab = (typeof ADMIN_TABS)[number];

// Roving focus of a tablist (WAI-ARIA tabs pattern): arrows wrap around,
// Home / End jump to the ends; other keys give null (not handled).
export function tabForKey(current: AdminTab, key: string): AdminTab | null {
  const index = ADMIN_TABS.indexOf(current);
  const last = ADMIN_TABS.length - 1;
  switch (key) {
    case 'ArrowRight':
      return ADMIN_TABS[index === last ? 0 : index + 1];
    case 'ArrowLeft':
      return ADMIN_TABS[index === 0 ? last : index - 1];
    case 'Home':
      return ADMIN_TABS[0];
    case 'End':
      return ADMIN_TABS[last];
    default:
      return null;
  }
}
