import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merges class names and lets a later Tailwind utility win over an earlier one. */
export const cn = (...inputs: ClassValue[]): string => twMerge(clsx(inputs));
