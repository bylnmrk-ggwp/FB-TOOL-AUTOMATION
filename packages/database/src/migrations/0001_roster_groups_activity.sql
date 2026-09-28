CREATE TABLE `account_activity` (
	`id` text PRIMARY KEY NOT NULL,
	`account_id` text NOT NULL,
	`kind` text NOT NULL,
	`target_url` text NOT NULL,
	`target_name` text,
	`status` text NOT NULL,
	`message` text,
	`job_id` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `account_activity_unique` ON `account_activity` (`account_id`,`kind`,`target_url`);--> statement-breakpoint
CREATE INDEX `account_activity_account_idx` ON `account_activity` (`account_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `groups` (
	`id` text PRIMARY KEY NOT NULL,
	`account_id` text NOT NULL,
	`name` text NOT NULL,
	`url` text NOT NULL,
	`fetched_at` text NOT NULL,
	FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `groups_account_url_unique` ON `groups` (`account_id`,`url`);--> statement-breakpoint
CREATE INDEX `groups_url_idx` ON `groups` (`url`);--> statement-breakpoint
ALTER TABLE `accounts` ADD `sheet_no` integer;--> statement-breakpoint
ALTER TABLE `accounts` ADD `username` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `password` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `gmail` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `gmail_password` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `phone` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `facebook_name` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `profile_url` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `login_status` text DEFAULT 'unknown' NOT NULL;--> statement-breakpoint
ALTER TABLE `accounts` ADD `login_reason` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `last_login_check_at` text;--> statement-breakpoint
ALTER TABLE `accounts` ADD `share_restricted_until` text;--> statement-breakpoint
CREATE INDEX `accounts_username_idx` ON `accounts` (`username`);--> statement-breakpoint
CREATE INDEX `accounts_login_status_idx` ON `accounts` (`login_status`);