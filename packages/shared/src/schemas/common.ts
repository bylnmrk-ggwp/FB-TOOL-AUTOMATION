import { z } from 'zod';

/** Every identifier in the system is an opaque, URL-safe string. */
export const IdSchema = z.string().min(1).max(64);

export const IsoDateTimeSchema = z.string().datetime({ offset: true });

/** Accepts what SQLite/Date/JSON round-trips hand us and normalises to ISO-8601. */
export const CoercedDateTimeSchema = z
  .union([z.string(), z.number(), z.date()])
  .transform((value, ctx) => {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Invalid date' });
      return z.NEVER;
    }
    return date.toISOString();
  });

export const PaginationSchema = z.object({
  limit: z.coerce.number().int().min(1).max(500).default(50),
  offset: z.coerce.number().int().min(0).default(0),
});
export type Pagination = z.infer<typeof PaginationSchema>;

export const paginatedSchema = <T extends z.ZodTypeAny>(item: T) =>
  z.object({
    items: z.array(item),
    total: z.number().int().min(0),
    limit: z.number().int().min(1),
    offset: z.number().int().min(0),
  });

export type Paginated<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export const IdParamSchema = z.object({ id: IdSchema });
export type IdParam = z.infer<typeof IdParamSchema>;

/** Shape of every non-2xx API response. */
export const ApiErrorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().optional(),
  }),
});
export type ApiError = z.infer<typeof ApiErrorSchema>;

export const HealthSchema = z.object({
  status: z.enum(['ok', 'degraded']),
  version: z.string(),
  uptimeSeconds: z.number().nonnegative(),
  timestamp: IsoDateTimeSchema,
  checks: z.object({
    database: z.enum(['up', 'down']),
    queue: z.enum(['up', 'down']),
  }),
});
export type Health = z.infer<typeof HealthSchema>;
