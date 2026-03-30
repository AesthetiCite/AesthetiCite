CREATE TABLE "conversations" (
        "id" text PRIMARY KEY NOT NULL,
        "created_at" timestamp with time zone DEFAULT now(),
        "user_id" text,
        "title" text
);
--> statement-breakpoint
CREATE TABLE "messages" (
        "id" bigint PRIMARY KEY NOT NULL,
        "conversation_id" text NOT NULL,
        "role" text NOT NULL,
        "content" text NOT NULL,
        "created_at" timestamp with time zone DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "search_history" (
        "id" serial PRIMARY KEY NOT NULL,
        "query" varchar(500) NOT NULL,
        "answer" text,
        "created_at" timestamp with time zone DEFAULT now()
);
