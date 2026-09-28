import { useEffect } from 'react';
import { useUiStore } from '../store/uiStore';

/** Mirrors the stored theme onto <html data-theme> for the CSS tokens. */
export const useTheme = (): { theme: 'dark' | 'light'; toggle: () => void } => {
  const theme = useUiStore((state) => state.theme);
  const toggle = useUiStore((state) => state.toggleTheme);

  useEffect(() => {
    document.documentElement.dataset['theme'] = theme;
  }, [theme]);

  return { theme, toggle };
};
