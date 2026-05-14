import os
import asyncpg
from config import DATABASE_URL
import logging

logger = logging.getLogger(__name__)

pool: asyncpg.Pool = None

async def init_db():
    global pool
    logger.info("Connecting to PostgreSQL...")
    pool = await asyncpg.create_pool(DATABASE_URL)
    
    async with pool.acquire() as conn:
        # Table for telegram users
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username VARCHAR(255),
                full_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for subscriptions (links user to 3x-ui client)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                client_email VARCHAR(255) UNIQUE NOT NULL,
                client_uuid VARCHAR(255) UNIQUE NOT NULL,
                sub_id VARCHAR(255),
                status VARCHAR(50) DEFAULT 'active', -- active, expired
                expires_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        # In case the table already existed before sub_id was added
        try:
            await conn.execute('ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS sub_id VARCHAR(255)')
        except Exception:
            pass
            
        # Table for payments (manual verification)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount INTEGER NOT NULL,
                months INTEGER NOT NULL,
                status VARCHAR(50) DEFAULT 'pending', -- pending, successful, rejected
                photo_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        ''')
    logger.info("Database initialized.")

async def add_user(telegram_id: int, username: str, full_name: str):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (telegram_id, username, full_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO NOTHING
        ''', telegram_id, username, full_name)

async def get_user(telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE telegram_id = $1', telegram_id)

async def add_subscription(user_id: int, client_email: str, client_uuid: str, sub_id: str, expires_at):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO subscriptions (user_id, client_email, client_uuid, sub_id, expires_at)
            VALUES ($1, $2, $3, $4, $5)
        ''', user_id, client_email, client_uuid, sub_id, expires_at)

async def extend_subscription(user_id: int, new_expires_at):
    async with pool.acquire() as conn:
        await conn.execute('''
            UPDATE subscriptions 
            SET expires_at = $1 
            WHERE user_id = $2 AND status = 'active'
        ''', new_expires_at, user_id)

async def get_active_subscription(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('''
            SELECT * FROM subscriptions 
            WHERE user_id = $1 AND status = 'active'
            ORDER BY id DESC LIMIT 1
        ''', user_id)

async def create_payment(user_id: int, amount: int, months: int, photo_file_id: str):
    async with pool.acquire() as conn:
        return await conn.fetchval('''
            INSERT INTO payments (user_id, amount, months, photo_file_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        ''', user_id, amount, months, photo_file_id)

async def get_payment(payment_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM payments WHERE id = $1', payment_id)

async def update_payment_status(payment_id: int, status: str):
    async with pool.acquire() as conn:
        await conn.execute('UPDATE payments SET status = $1 WHERE id = $2', status, payment_id)

async def import_subscription(telegram_id: int, client_email: str, client_uuid: str, sub_id: str, expires_at):
    async with pool.acquire() as conn:
        # Create user if not exists (we only have their ID for now)
        await conn.execute('''
            INSERT INTO users (telegram_id, username, full_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO NOTHING
        ''', telegram_id, f"user_{telegram_id}", "Imported User")
        
        # Insert subscription, updating if it exists
        await conn.execute('''
            INSERT INTO subscriptions (user_id, client_email, client_uuid, sub_id, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (client_uuid) DO UPDATE 
            SET user_id = EXCLUDED.user_id, 
                client_email = EXCLUDED.client_email,
                sub_id = EXCLUDED.sub_id,
                expires_at = EXCLUDED.expires_at,
                status = 'active'
        ''', telegram_id, client_email, client_uuid, sub_id, expires_at)

async def close_db():
    if pool:
        await pool.close()
