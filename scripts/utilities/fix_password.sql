UPDATE users SET password_hash = '$argon2id$v=19$m=65536,t=3,p=4$B2BM6Z1TqnUO4fy/11qrVQ$gKUQnzu+6WCxIOixWGhV6DLWTLIoyuNm53ZE2KVejcM' WHERE email = 'admin@example.com';
