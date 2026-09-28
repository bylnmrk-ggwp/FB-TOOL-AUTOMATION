import { defineConfig } from 'drizzle-kit';

/** Only drizzle-kit reads this; the running server never uses it. */
export default defineConfig({
  dialect: 'sqlite',
  schema: './src/schema/index.ts',
  out: './src/migrations',
  strict: true,
  verbose: true,
});
