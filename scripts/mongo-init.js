/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

// Runs on first container init (as root). Creates indexes on the app DB.
db = db.getSiblingDB("content_scraper");

db.createCollection("posts");
db.createCollection("users");
db.createCollection("interactions");

db.posts.createIndex(
  { source: 1, external_id: 1 },
  { unique: true, name: "uniq_source_external_id" }
);
db.posts.createIndex({ source: 1, scraped_at: -1 }, { name: "source_scraped_at" });
db.posts.createIndex({ categories: 1 }, { name: "categories" });
db.posts.createIndex({ "author.name": 1 }, { name: "author_name" });
db.posts.createIndex({ published_at: -1 }, { name: "published_at" });
db.posts.createIndex({ tags: 1 }, { name: "tags" });
db.posts.createIndex({ embedding_status: 1 }, { name: "embedding_status" });
db.posts.createIndex({ "metadata.subdomain": 1 }, { name: "subdomain" });
db.posts.createIndex({ content_hash: 1 }, { name: "content_hash" });

db.users.createIndex({ user_id: 1 }, { unique: true, name: "uniq_user_id" });
db.interactions.createIndex({ user_id: 1, ts: -1 }, { name: "user_ts" });
db.interactions.createIndex({ user_id: 1, post_id: 1 }, { name: "user_post" });
