export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_STORAGE_KEY = 'swb:theme-preference';

function readPreference(): ThemePreference {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === 'light' || value === 'dark' || value === 'system' ? value : 'system';
  } catch {
    return 'system';
  }
}

export function getThemePreference(): ThemePreference {
  return readPreference();
}

export function setThemePreference(value: string): ThemePreference {
  const preference: ThemePreference = value === 'light' || value === 'dark' ? value : 'system';
  try { window.localStorage.setItem(THEME_STORAGE_KEY, preference); } catch { /* Page theme still changes. */ }
  applyTheme(preference);
  return preference;
}

function applyTheme(preference: ThemePreference): void {
  const theme = preference === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : preference;
  document.documentElement.dataset.theme = theme;
}

export function initializeTheme(): void {
  let preference = readPreference();
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  applyTheme(preference);
  media.addEventListener('change', () => {
    preference = readPreference();
    if (preference === 'system') applyTheme(preference);
  });
  document.addEventListener('change', (event) => {
    const target = event.target;
    if (target instanceof HTMLSelectElement && target.id === 'theme-preference') {
      preference = setThemePreference(target.value);
    }
  });
}
