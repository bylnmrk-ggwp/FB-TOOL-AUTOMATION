import { useEffect } from 'react';
import { useUiStore, type Theme } from '../store/uiStore';

/** Mirrors the stored theme onto <html class="dark">, which the tokens key on. */
export const useTheme = (): { theme: Theme; toggle: () => void } => {
  const theme = useUiStore((state) => state.theme);
  const toggle = useUiStore((state) => state.toggleTheme);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.style.colorScheme = theme;
  }, [theme]);

  return { theme, toggle };
};
