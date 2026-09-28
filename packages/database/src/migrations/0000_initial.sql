CREATE TABLE `accounts` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`display_name` text NOT NULL,
	`profile_id` text NOT NULL,
	`status` text DEFAULT 'offline' NOT NULL,
	`enabled` integer DEFAULT true NOT NULL,
	`last_error` text,
	`last_active_at` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `accounts_name_unique` ON `accounts` (`name`);--> statement-breakpoint
CREATE INDEX `accounts_status_idx` ON `accounts` (`status`);--> statement-breakpoint
CREATE INDEX `accounts_enabled_idx` ON `accounts` (`enabled`);--> statement-breakpoint
CREATE TABLE `browser_profiles` (
	`id` text PRIMARY KEY NOT NULL,
	`account_id` text NOT NULL,
	`slug` text NOT NULL,
	`directory` text NOT NULL,
	`channel` text DEFAULT 'chromium' NOT NULL,
	`locked_by` text,
	`locked_at` text,
	`last_used_at` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `browser_profiles_account_unique` ON `browser_profiles` (`account_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `browser_profiles_slug_unique` ON `browser_profiles` (`slug`);--> statement-breakpoint
CREATE INDEX `browser_profiles_locked_idx` ON `browser_profiles` (`locked_by`);--> statement-breakpoint
CREATE TABLE `job_events` (
	`id` text PRIMARY KEY NOT NULL,
	`job_id` text NOT NULL,
	`from_status` text,
	`to_status` text NOT NULL,
	`message` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`job_id`) REFERENCES `jobs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `job_events_job_idx` ON `job_events` (`job_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`account_id` text NOT NULL,
	`type` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`payload` text NOT NULL,
	`priority` integer DEFAULT 0 NOT NULL,
	`retry_count` integer DEFAULT 0 NOT NULL,
	`max_retries` integer DEFAULT 2 NOT NULL,
	`progress` real DEFAULT 0 NOT NULL,
	`run_after` text,
	`result` text,
	`last_error` text,
	`locked_by` text,
	`created_at` text NOT NULL,
	`queued_at` text,
	`started_at` text,
	`finished_at` text,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `jobs_claim_idx` ON `jobs` (`status`,`priority`,`created_at`);--> statement-breakpoint
CREATE INDEX `jobs_account_status_idx` ON `jobs` (`account_id`,`status`);--> statement-breakpoint
CREATE INDEX `jobs_run_after_idx` ON `jobs` (`status`,`run_after`);--> statement-breakpoint
CREATE INDEX `jobs_created_idx` ON `jobs` (`created_at`);--> statement-breakpoint
CREATE TABLE `automation_logs` (
	`id` text PRIMARY KEY NOT NULL,
	`level` text NOT NULL,
	`message` text NOT NULL,
	`event` text,
	`account_id` text,
	`job_id` text,
	`session_id` text,
	`request_id` text,
	`context` text,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `automation_logs_created_idx` ON `automation_logs` (`created_at`);--> statement-breakpoint
CREATE INDEX `automation_logs_level_idx` ON `automation_logs` (`level`,`created_at`);--> statement-breakpoint
CREATE INDEX `automation_logs_account_idx` ON `automation_logs` (`account_id`,`created_at`);--> statement-breakpoint
CREATE INDEX `automation_logs_job_idx` ON `automation_logs` (`job_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `settings` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`updated_at` text NOT NULL
);
